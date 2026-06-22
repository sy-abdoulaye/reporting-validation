from sqlalchemy import Column, String, Boolean, DateTime, JSON, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.core.database import Base


class ColumnProfile(Base):
    """Sélection de colonnes enregistrée (profil / filtre réutilisable) par utilisateur.

    Le champ ``columns`` est volontairement stocké en JSON afin de rester
    extensible : on peut y ajouter d'autres préférences (filtres, tris…) sans
    migration de schéma.
    """
    __tablename__ = "column_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    name = Column(String(100), nullable=False)

    # Liste de colonnes : [{"name": str, "width": int}]
    columns = Column(JSON, default=list)

    # Préférences réutilisées avec le profil
    date_format = Column(String(50), nullable=True)

    # Profil appliqué automatiquement à l'ouverture d'un nouveau workflow
    is_default = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        # Un nom de profil unique par utilisateur
        UniqueConstraint("user_id", "name", name="uq_column_profile_user_name"),
        Index("ix_column_profile_user_default", "user_id", "is_default"),
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "name": self.name,
            "columns": self.columns or [],
            "date_format": self.date_format,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
