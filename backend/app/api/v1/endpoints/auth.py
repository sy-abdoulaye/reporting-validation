from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field, validator
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from uuid import UUID
import re

from app.core.database import get_db
from app.core.security import SecurityService
from app.core.auth import AuthDependencies
from app.core.config import settings
from app.models.user import User, ApiKey
from app.services.audit_service import AuditService
from app.services.email_service import EmailService
import os


def _client_ip(request: Optional[Request]) -> Optional[str]:
    """IP du client en tenant compte d'un éventuel reverse-proxy (X-Forwarded-For)."""
    if request is None:
        return None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None

router = APIRouter(prefix="/auth", tags=["authentication"])

# Schémas Pydantic
class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=100)
    full_name: Optional[str] = None
    department: Optional[str] = None
    job_title: Optional[str] = None

    @validator('username')
    def validate_username(cls, v):
        if not re.match("^[a-zA-Z0-9_]+$", v):
            raise ValueError("Nom d'utilisateur invalide (lettres, chiffres, _ uniquement)")
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Mot de passe trop court (minimum 8 caractères)")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r"[0-9]", v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v

class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    department: Optional[str]
    job_title: Optional[str]
    is_superuser: bool
    created_at: datetime

    class Config:
        from_attributes = True

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse

class TokenRefreshRequest(BaseModel):
    refresh_token: str

class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=100)

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    # URL de base de la page de réinitialisation (envoyée par le frontend)
    reset_base_url: Optional[str] = None

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=100)

    @validator('new_password')
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Mot de passe trop court (minimum 8 caractères)")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Le mot de passe doit contenir au moins une majuscule")
        if not re.search(r"[0-9]", v):
            raise ValueError("Le mot de passe doit contenir au moins un chiffre")
        return v

class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key: str
    permissions: list
    rate_limit: int
    daily_limit: int
    expires_at: Optional[str]
    created_at: str
    is_active: bool

class ApiKeyCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=50)
    permissions: Optional[list] = ["upload", "analyze", "generate", "email"]
    expires_in_days: Optional[int] = Field(30, ge=1, le=365)

# Endpoints
@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """Inscription d'un nouvel utilisateur"""

    # Vérifier si l'email existe déjà
    existing_email = db.query(User).filter(User.email == user_data.email).first()
    if existing_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cet email est déjà utilisé"
        )

    # Vérifier si le nom d'utilisateur existe déjà
    existing_username = db.query(User).filter(User.username == user_data.username).first()
    if existing_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce nom d'utilisateur est déjà pris"
        )

    # Créer l'utilisateur
    user = User(
        email=user_data.email,
        username=user_data.username,
        full_name=user_data.full_name,
        department=user_data.department,
        job_title=user_data.job_title,
        is_superuser=False  # Premier utilisateur? À adapter
    )
    user.set_password(user_data.password)

    db.add(user)
    db.commit()
    db.refresh(user)

    # Journal d'audit
    AuditService(db).log(
        action="register",
        category="auth",
        status="success",
        user=user,
        target_type="user",
        target_id=user.id,
        target_label=user.username,
        description=f"Inscription de l'utilisateur {user.username}",
        details={"username": user.username, "email": user.email},
        ip_address=_client_ip(request),
    )

    return user

@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Connexion utilisateur"""

    audit = AuditService(db)
    ip = _client_ip(request)

    # Chercher l'utilisateur par email ou username
    user = db.query(User).filter(
        (User.email == form_data.username) | (User.username == form_data.username)
    ).first()

    if not user:
        audit.log(
            action="login_failed", category="auth", status="failed",
            username=form_data.username,
            description=f"Échec de connexion : identifiant inconnu ({form_data.username})",
            details={"reason": "unknown_user", "attempted": form_data.username},
            ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email/Utilisateur ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # Vérifier si le compte est verrouillé
    if user.locked_until and user.locked_until > datetime.utcnow():
        remaining = (user.locked_until - datetime.utcnow()).seconds // 60
        audit.log(
            action="login_failed", category="auth", status="failed",
            user=user, description=f"Échec de connexion : compte verrouillé ({user.username})",
            details={"reason": "locked", "remaining_minutes": remaining}, ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Compte verrouillé pour {remaining} minutes"
        )

    # Vérifier le mot de passe
    if not user.verify_password(form_data.password):
        user.increment_failed_attempts()
        db.commit()

        remaining = 5 - user.failed_login_attempts
        audit.log(
            action="login_failed", category="auth", status="failed",
            user=user, description=f"Échec de connexion : mot de passe incorrect ({user.username})",
            details={"reason": "bad_password", "remaining_attempts": remaining}, ip_address=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Mot de passe incorrect. {remaining} tentative(s) restante(s)"
        )

    # Réinitialiser les tentatives échouées
    user.reset_failed_attempts()
    user.last_login = datetime.utcnow()
    db.commit()

    # Créer les tokens
    access_token = SecurityService.create_access_token(
        data={"sub": str(user.id), "username": user.username}
    )
    refresh_token = SecurityService.create_refresh_token(
        data={"sub": str(user.id)}
    )

    # Journal d'audit
    audit.log(
        action="login", category="auth", status="success", user=user,
        description=f"Connexion de {user.username}",
        details={"username": user.username}, ip_address=ip,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user
    }

@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(
    request: TokenRefreshRequest,
    db: Session = Depends(get_db)
):
    """Rafraîchit le token d'accès"""

    try:
        payload = SecurityService.decode_token(request.refresh_token)

        # Vérifier le type
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de rafraîchissement invalide"
            )

        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()

        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Utilisateur non trouvé ou désactivé"
            )

        # Créer un nouveau token d'accès
        access_token = SecurityService.create_access_token(
            data={"sub": str(user.id), "username": user.username}
        )

        # Nouveau refresh token
        refresh_token = SecurityService.create_refresh_token(
            data={"sub": str(user.id)}
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )

@router.post("/logout")
async def logout(
    request: Request,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Déconnexion (invalide le token côté client)"""
    # Le token JWT est stateless, on ne fait rien côté serveur — on journalise l'action
    AuditService(db).log(
        action="logout", category="auth", status="success", user=current_user,
        description=f"Déconnexion de {current_user.username}",
        details={"username": current_user.username}, ip_address=_client_ip(request),
    )

    return {"message": "Déconnexion réussie"}

@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Change le mot de passe de l'utilisateur"""

    # Vérifier l'ancien mot de passe
    if not current_user.verify_password(request.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mot de passe actuel incorrect"
        )

    # Vérifier que le nouveau mot de passe est différent
    if request.current_password == request.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Le nouveau mot de passe doit être différent"
        )

    # Mettre à jour
    current_user.set_password(request.new_password)
    current_user.password_changed_at = datetime.utcnow()
    db.commit()

    return {"message": "Mot de passe modifié avec succès"}

@router.post("/forgot-password")
async def forgot_password(
    request: ForgotPasswordRequest,
    db: Session = Depends(get_db)
):
    """Demande de réinitialisation : envoie un lien par email si le compte existe.

    Pour ne pas divulguer quels emails existent, la réponse est toujours identique.
    """
    user = db.query(User).filter(User.email == request.email).first()

    if user and user.is_active:
        # Empreinte = extrait du hash actuel → invalide le token après changement
        fingerprint = (user.password_hash or "")[-12:]
        token = SecurityService.create_password_reset_token(str(user.id), fingerprint)

        base = request.reset_base_url or os.getenv("FRONTEND_URL", "http://localhost:8080") + "/reset-password.html"
        sep = "&" if "?" in base else "?"
        reset_link = f"{base}{sep}token={token}"

        email_service = EmailService()
        body = (
            f"Bonjour {user.full_name or user.username},\n\n"
            "Vous avez demandé la réinitialisation de votre mot de passe.\n"
            "Cliquez sur le lien ci-dessous (valable 30 minutes) pour définir un nouveau mot de passe :\n\n"
            f"{reset_link}\n\n"
            "Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.\n\n"
            "— Reporting App"
        )
        try:
            await email_service.send_message(
                to_emails=[user.email],
                subject="Réinitialisation de votre mot de passe — Reporting App",
                body=body
            )
        except Exception as e:
            print(f"❌ Échec envoi email reset: {e}")

    return {"message": "Si un compte existe pour cet email, un lien de réinitialisation a été envoyé."}

@router.post("/reset-password")
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db)
):
    """Réinitialise le mot de passe à partir d'un token reçu par email."""
    try:
        payload = SecurityService.decode_token(request.token)
    except ValueError:
        raise HTTPException(status_code=400, detail="Lien invalide ou expiré.")

    if payload.get("type") != "reset":
        raise HTTPException(status_code=400, detail="Token invalide.")

    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Compte introuvable ou désactivé.")

    # Vérifier l'empreinte : un token déjà utilisé (mdp changé) ne correspond plus
    if payload.get("fp") != (user.password_hash or "")[-12:]:
        raise HTTPException(status_code=400, detail="Ce lien a déjà été utilisé ou n'est plus valide.")

    user.set_password(request.new_password)
    user.password_changed_at = datetime.utcnow()
    user.reset_failed_attempts()  # déverrouille le compte au passage
    db.commit()

    return {"message": "Mot de passe réinitialisé avec succès. Vous pouvez vous connecter."}

# Endpoints pour les clés API
@router.get("/api-keys", response_model=list[ApiKeyResponse])
async def get_api_keys(
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Récupère toutes les clés API de l'utilisateur"""

    api_keys = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id
    ).order_by(ApiKey.created_at.desc()).all()

    results = []
    for key in api_keys:
        results.append({
            "id": str(key.id),
            "name": key.name,
            "key": "••••••••" + key.key[-8:] if key.key else "",  # Masquer la clé
            "permissions": key.permissions,
            "rate_limit": key.rate_limit,
            "daily_limit": key.daily_limit,
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
            "created_at": key.created_at.isoformat(),
            "is_active": key.is_active
        })

    return results

@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    request: ApiKeyCreate,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Crée une nouvelle clé API"""

    # Générer la clé
    raw_key = SecurityService.generate_api_key()
    hashed_key = SecurityService.hash_api_key(raw_key)

    # Calculer la date d'expiration
    expires_at = None
    if request.expires_in_days:
        expires_at = datetime.utcnow() + timedelta(days=request.expires_in_days)

    api_key = ApiKey(
        user_id=current_user.id,
        name=request.name,
        key=hashed_key,
        permissions=request.permissions,
        expires_at=expires_at
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "key": raw_key,  # Retourner la clé brute une seule fois
        "permissions": api_key.permissions,
        "rate_limit": api_key.rate_limit,
        "daily_limit": api_key.daily_limit,
        "expires_at": expires_at.isoformat() if expires_at else None,
        "created_at": api_key.created_at.isoformat(),
        "is_active": api_key.is_active
    }

@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Supprime une clé API"""

    api_key = db.query(ApiKey).filter(
        ApiKey.id == key_id,
        ApiKey.user_id == current_user.id
    ).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Clé API non trouvée"
        )

    db.delete(api_key)
    db.commit()

    return {"message": "Clé API supprimée"}

@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(AuthDependencies.get_current_active_user)
):
    """Récupère les informations de l'utilisateur courant"""
    return current_user

@router.put("/me")
async def update_current_user(
    full_name: Optional[str] = None,
    department: Optional[str] = None,
    job_title: Optional[str] = None,
    preferences: Optional[dict] = None,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """Met à jour le profil utilisateur"""

    if full_name is not None:
        current_user.full_name = full_name
    if department is not None:
        current_user.department = department
    if job_title is not None:
        current_user.job_title = job_title
    if preferences is not None:
        current_user.preferences.update(preferences)

    current_user.updated_at = datetime.utcnow()
    db.commit()

    return current_user.to_dict()