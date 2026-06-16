from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timedelta
import uuid
import bcrypt

from app.core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=True)

    # Authentication
    password_hash = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)

    # Profile
    department = Column(String(100), nullable=True)
    job_title = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)

    # Preferences utilisateur
    preferences = Column(JSON, default={
        "default_date_format": "%d/%m/%Y %H:%M:%S",
        "default_column_width": 15,
        "email_notifications": True,
        "theme": "light"
    })

    # Security
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, default=datetime.utcnow)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password: str):
        """Hash et stocke le mot de passe"""
        salt = bcrypt.gensalt(rounds=12)
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, password: str) -> bool:
        """Vérifie le mot de passe"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def increment_failed_attempts(self):
        """Incrémente le compteur d'échecs"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = datetime.utcnow() + timedelta(minutes=30)

    def reset_failed_attempts(self):
        """Réinitialise le compteur d'échecs"""
        self.failed_login_attempts = 0
        self.locked_until = None

    def to_dict(self):
        """Convertit en dictionnaire (sans données sensibles)"""
        return {
            "id": str(self.id),
            "email": self.email,
            "username": self.username,
            "full_name": self.full_name,
            "department": self.department,
            "job_title": self.job_title,
            "is_superuser": self.is_superuser,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None
        }


class ApiKey(Base):
    """Clés API pour l'intégration"""
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key = Column(String(64), unique=True, nullable=False, index=True)

    # Permissions
    permissions = Column(JSON, default=["upload", "analyze", "generate", "email"])

    # Rate limiting
    rate_limit = Column(Integer, default=100)  # requêtes par minute
    daily_limit = Column(Integer, default=1000)  # requêtes par jour

    # Usage
    last_used_at = Column(DateTime, nullable=True)
    usage_count = Column(Integer, default=0)

    # Expiration
    expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    def is_expired(self) -> bool:
        """Vérifie si la clé a expiré"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def can_access(self, permission: str) -> bool:
        """Vérifie si la clé a une permission spécifique"""
        return permission in self.permissions