from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
import secrets
import hashlib
import base64

from app.core.config import settings

# Contexte pour le hachage des mots de passe
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class SecurityService:
    """Service de sécurité pour l'authentification"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Vérifie un mot de passe"""
        return pwd_context.verify(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash un mot de passe"""
        return pwd_context.hash(password)

    @staticmethod
    def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
        """Crée un token d'accès JWT"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({
            "exp": expire,
            "type": "access",
            "iat": datetime.utcnow(),
            "aud": settings.AUTH_JWT_AUDIENCE,
            "iss": settings.AUTH_JWT_ISSUER,
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        return encoded_jwt

    @staticmethod
    def create_refresh_token(data: Dict[str, Any]) -> str:
        """Crée un token de rafraîchissement"""
        to_encode = data.copy()

        expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        to_encode.update({
            "exp": expire,
            "type": "refresh",
            "iat": datetime.utcnow(),
            "aud": settings.AUTH_JWT_AUDIENCE,
            "iss": settings.AUTH_JWT_ISSUER,
        })

        encoded_jwt = jwt.encode(
            to_encode,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        return encoded_jwt

    @staticmethod
    def create_password_reset_token(user_id: str, fingerprint: str) -> str:
        """Crée un token de réinitialisation de mot de passe (courte durée de vie).

        `fingerprint` est un extrait du hash du mot de passe actuel : une fois le
        mot de passe changé, l'empreinte ne correspond plus → le token devient inutilisable.
        """
        expire = datetime.utcnow() + timedelta(minutes=30)
        to_encode = {
            "sub": str(user_id),
            "fp": fingerprint,
            "exp": expire,
            "type": "reset",
            "iat": datetime.utcnow(),
            "aud": settings.AUTH_JWT_AUDIENCE,
            "iss": settings.AUTH_JWT_ISSUER,
        }
        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def decode_token(token: str) -> Dict[str, Any]:
        """Décode et valide un token JWT"""
        try:
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM],
                audience=settings.AUTH_JWT_AUDIENCE,
                issuer=settings.AUTH_JWT_ISSUER
            )
            return payload
        except JWTError as e:
            raise ValueError(f"Token invalide: {str(e)}")

    @staticmethod
    def generate_api_key() -> str:
        """Génère une clé API unique"""
        # Format: rp_ + 32 caractères aléatoires
        random_bytes = secrets.token_bytes(24)
        api_key = "rp_" + base64.urlsafe_b64encode(random_bytes).decode('utf-8').replace('=', '')
        return api_key[:40]  # Limiter à 40 caractères

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash d'une clé API pour stockage"""
        return hashlib.sha256(api_key.encode()).hexdigest()