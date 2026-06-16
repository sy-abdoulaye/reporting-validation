from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

from app.core.database import get_db
from app.core.security import SecurityService
from app.models.user import User, ApiKey
from app.services.history_service import HistoryService

# Configuration OAuth2
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
security = HTTPBearer(auto_error=False)

class AuthDependencies:
    """Dépendances pour l'authentification"""

    @staticmethod
    async def get_current_user(
        token: Optional[str] = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
    ) -> Optional[User]:
        """Récupère l'utilisateur courant depuis le token JWT"""
        if not token:
            return None

        try:
            payload = SecurityService.decode_token(token)

            # Vérifier le type de token
            if payload.get("type") != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Type de token invalide"
                )

            user_id = payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token invalide"
                )

            user = db.query(User).filter(User.id == user_id).first()

            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Utilisateur non trouvé"
                )

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Compte désactivé"
                )

            # Vérifier si le compte est verrouillé
            if user.locked_until and user.locked_until > datetime.utcnow():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail=f"Compte verrouillé jusqu'à {user.locked_until}"
                )

            return user

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=str(e)
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token invalide ou expiré"
            )

    @staticmethod
    async def get_current_active_user(
        current_user: User = Depends(get_current_user)
    ) -> User:
        """Récupère l'utilisateur actif courant"""
        if not current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentification requise",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return current_user

    @staticmethod
    async def get_current_superuser(
        current_user: User = Depends(get_current_active_user)
    ) -> User:
        """Récupère l'utilisateur admin courant"""
        if not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Droits administrateur requis"
            )
        return current_user

    @staticmethod
    async def get_api_key_user(
        credentials: HTTPAuthorizationCredentials = Security(security),
        db: Session = Depends(get_db)
    ) -> Optional[User]:
        """Authentification par clé API"""
        if not credentials:
            return None

        api_key = credentials.credentials

        # Hasher la clé pour la recherche
        hashed_key = SecurityService.hash_api_key(api_key)

        # Chercher la clé API
        api_key_obj = db.query(ApiKey).filter(
            ApiKey.key == hashed_key,
            ApiKey.is_active == True
        ).first()

        if not api_key_obj:
            return None

        # Vérifier l'expiration
        if api_key_obj.is_expired():
            return None

        # Vérifier les limites
        if api_key_obj.daily_limit and api_key_obj.usage_count >= api_key_obj.daily_limit:
            return None

        # Mettre à jour l'utilisation
        api_key_obj.last_used_at = datetime.utcnow()
        api_key_obj.usage_count += 1
        db.commit()

        # Récupérer l'utilisateur
        user = db.query(User).filter(User.id == api_key_obj.user_id).first()

        return user if user and user.is_active else None

    @staticmethod
    def require_permission(permission: str):
        """Décorateur pour vérifier les permissions"""
        async def dependency(
            current_user: User = Depends(get_current_active_user)
        ) -> User:
            # Les superusers ont tous les droits
            if current_user.is_superuser:
                return current_user

            # Vérifier la permission spécifique
            # Pour l'instant, tous les utilisateurs actifs ont les droits
            # À personnaliser selon vos besoins
            return current_user
        return dependency