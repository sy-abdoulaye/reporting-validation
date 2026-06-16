from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List
from sqlalchemy.orm import Session
from pathlib import Path

from app.core.database import get_db
from app.core.auth import AuthDependencies
from app.models.report import Report
from app.models.user import User
from app.services.email_service import EmailService
from app.services.history_service import HistoryService

router = APIRouter(prefix="/email", tags=["email"])

class EmailRequest(BaseModel):
    recipients: List[str]
    subject: str
    body: str

@router.post("/send/{report_id}")
async def send_report_email(
    report_id: str,
    request: EmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user)
):
    """
    Envoie un rapport par email
    """
    # 1. Vérifier le rapport
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(404, "Rapport non trouvé")

    if report.status != "completed":
        raise HTTPException(400, "Le rapport n'est pas encore prêt")

    # 2. Vérifier le fichier
    if not report.output_path:
        raise HTTPException(404, "Le rapport n'a pas de fichier de sortie")

    report_path = Path(report.output_path)
    if not report_path.exists():
        raise HTTPException(404, "Fichier rapport non trouvé")

    # 3. Envoyer l'email
    email_service = EmailService()
    success = await email_service.send_report(
        to_emails=request.recipients,
        subject=request.subject,
        body=request.body,
        attachment_path=report_path,
        attachment_name=report.filename
    )

    # Journaliser l'action email
    HistoryService(db).log_action(
        file_id=report.file_id,
        report_id=report.id,
        action="email",
        status="success" if success else "failed",
        user_id=current_user.id,
        details={
            "filename": report.filename,
            "recipients": request.recipients,
            "report_id": str(report.id),
        },
        error_message=None if success else "Échec de l'envoi SMTP",
    )

    if not success:
        raise HTTPException(500, "Erreur lors de l'envoi de l'email")

    return {
        "success": True,
        "message": "Email envoyé avec succès",
        "recipients": request.recipients
    }