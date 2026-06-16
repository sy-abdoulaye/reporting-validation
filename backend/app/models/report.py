from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
import uuid
from app.core.database import Base

class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    status = Column(String(50), default="processing")  # pending, processing, completed, failed
    date_format = Column(String(50), default="%d/%m/%Y %H:%M:%S")
    total_rows = Column(Integer, nullable=True)
    total_columns = Column(Integer, nullable=True)
    file_size = Column(Integer, nullable=True)
    output_path = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    selected_columns = Column(Text, nullable=True)  # JSON string des colonnes sélectionnées
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)