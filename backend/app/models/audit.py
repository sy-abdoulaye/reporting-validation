from sqlalchemy import Column, String, DateTime, JSON, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid

from app.core.database import Base


class AuditLog(Base):
    """Journal d'audit : trace les actions sensibles de l'application
    (connexions, inscriptions, gestion des utilisateurs, suppression/renommage
    de rapports, etc.). Séparé de ``ProcessingHistory`` qui ne concerne que le
    traitement des fichiers Excel."""

    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Auteur de l'action (nullable : ex. échec de connexion sur un compte inconnu)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    # Nom dénormalisé : reste lisible même si l'utilisateur est supprimé plus tard
    username = Column(String(150), nullable=True)

    # Action machine (ex. "login", "login_failed", "user.update", "report.delete")
    action = Column(String(100), nullable=False, index=True)
    # Catégorie pour le filtrage ("auth", "user", "report", "system")
    category = Column(String(50), nullable=False, default="system", index=True)
    # Issue de l'action
    status = Column(String(20), nullable=False, default="success")  # success | failed

    # Cible éventuelle de l'action (utilisateur, rapport…)
    target_type = Column(String(50), nullable=True)
    target_id = Column(String(100), nullable=True)
    target_label = Column(String(255), nullable=True)

    # Description lisible + détails libres
    description = Column(Text, nullable=True)
    details = Column(JSON, default=dict)

    # Contexte de la requête
    ip_address = Column(String(64), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_audit_category_action", "category", "action"),
        Index("ix_audit_created_at", "created_at"),
    )
