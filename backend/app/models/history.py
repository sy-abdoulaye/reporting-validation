from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.core.database import Base

class ProcessingHistory(Base):
    """Historique des traitements"""
    __tablename__ = "processing_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Références
    file_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    report_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Informations
    original_filename = Column(String(255), nullable=False)
    action = Column(String(50), nullable=False)  # upload, analyze, generate, email
    status = Column(String(50), default="pending")  # pending, success, failed

    # Détails
    details = Column(JSON, default=dict)  # {columns_count, rows_count, email_recipients, etc}
    error_message = Column(Text, nullable=True)

    # Métriques
    processing_time_ms = Column(Integer, nullable=True)  # temps de traitement en ms
    file_size = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Index pour les recherches rapides
    __table_args__ = (
        Index('ix_history_file_status', 'file_id', 'status'),
        Index('ix_history_created_at', 'created_at'),
    )