
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import json

from app.core.database import get_db, SessionLocal
from app.core.auth import AuthDependencies
from app.services.storage import StorageService
from app.services.excel_generator import ExcelGenerator
from app.services.history_service import HistoryService
from app.models.report import Report
from app.models.excel import ExcelFile
from app.models.user import User
from app.models.history import ProcessingHistory
from fastapi import BackgroundTasks
import uuid

router = APIRouter(prefix="/generate", tags=["generate"])
excel_generator = ExcelGenerator()
storage = StorageService()

class ColumnInfo(BaseModel):
    name: str
    # type: Optional[str] = "string"
    # width: Optional[int] = 15

class GenerateRequest(BaseModel):
    selected_columns: List[ColumnInfo]
    output_filename: Optional[str] = None
    date_format: str = "%d/%m/%Y %H:%M:%S"

class RenameRequest(BaseModel):
    filename: str

@router.post("/{file_id}")
async def generate_report(
    file_id: str,
    request: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user)
):
    """Génère un rapport à partir d'un fichier Excel analysé"""
    # Récupérer les métadonnées du fichier depuis la base de données
    excel_file = db.query(ExcelFile).filter(ExcelFile.id == file_id).first()
    if not excel_file:
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")

    # Vérifier que les colonnes sélectionnées existent dans le fichier
    selected_columns = [col.name for col in request.selected_columns]
    missing_columns = [col for col in selected_columns if col not in excel_file.headers]
    if missing_columns:
        raise HTTPException(status_code=400, detail=f"Colonnes sélectionnées manquantes dans le fichier: {', '.join(missing_columns)}")

    # Si l'utilisateur ne fournit pas de nom, conserver celui du fichier d'origine
    # (le rapport est toujours au format .xlsx)
    if request.output_filename:
        output_filename = request.output_filename
    else:
        output_filename = f"{Path(excel_file.original_filename).stem}.xlsx"
    report = Report(
        id=uuid.uuid4(),
        file_id=file_id,
        filename=output_filename,
        # status="completed",
        date_format=request.date_format,
        selected_columns=json.dumps([c.model_dump() for c in request.selected_columns]),
    )

    db.add(report)
    db.commit()
    db.refresh(report)

    # Lancer la génération du rapport en tâche de fond (avec l'utilisateur pour l'historique)
    background_tasks.add_task(generate_report_background, str(report.id), str(file_id), request.dict(), str(current_user.id))

    return {
        "report_id": report.id,
        "file_id": file_id,
        "status": report.status,
        "message": "La génération du rapport a été lancée en tâche de fond."
    }

@router.get("/{report_id}/download")
async def download_report(report_id: str, db: Session = Depends(get_db)):
    """Télécharge un rapport généré"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    if report.status != "completed":
        raise HTTPException(status_code=400, detail="Rapport pas encore prêt")
    if not report.output_path:
        raise HTTPException(status_code=404, detail="Chemin du fichier manquant")
    report_path = Path(report.output_path)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")
    return FileResponse(
        path=str(report_path),
        filename=report.filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.delete("/{report_id}")
async def delete_report(
    report_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Supprime un rapport : fichier sur disque, enregistrement et entrées d'historique liées."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Entrées d'historique liées à ce rapport (sert aussi à vérifier la propriété)
    hist_entries = db.query(ProcessingHistory).filter(
        ProcessingHistory.report_id == report_id
    ).all()

    if not current_user.is_superuser:
        owner_ids = {e.user_id for e in hist_entries if e.user_id is not None}
        if owner_ids and current_user.id not in owner_ids:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

    # Supprimer le fichier généré sur le disque
    if report.output_path:
        try:
            report_path = Path(report.output_path)
            if report_path.exists():
                report_path.unlink()
        except OSError:
            pass

    # Supprimer les entrées d'historique liées puis le rapport
    for entry in hist_entries:
        db.delete(entry)
    db.delete(report)
    db.commit()

    return {"message": "Rapport supprimé", "report_id": report_id}


@router.patch("/{report_id}")
async def rename_report(
    report_id: str,
    request: RenameRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
):
    """Renomme un rapport (nom affiché et nom de téléchargement)."""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")

    # Nettoyer le nom fourni : pas de séparateurs de chemin, pas d'espaces superflus
    new_name = (request.filename or "").strip().replace("/", "").replace("\\", "")
    if not new_name:
        raise HTTPException(status_code=400, detail="Le nom du fichier ne peut pas être vide")
    if not new_name.lower().endswith((".xlsx", ".xls")):
        new_name += ".xlsx"

    # Entrées d'historique liées (sert aussi à vérifier la propriété)
    hist_entries = db.query(ProcessingHistory).filter(
        ProcessingHistory.report_id == report_id
    ).all()

    if not current_user.is_superuser:
        owner_ids = {e.user_id for e in hist_entries if e.user_id is not None}
        if owner_ids and current_user.id not in owner_ids:
            raise HTTPException(status_code=403, detail="Accès non autorisé")

    # Mettre à jour le nom du rapport (utilisé pour le téléchargement)
    report.filename = new_name

    # Mettre à jour le nom affiché dans les entrées d'historique (colonne JSON)
    for entry in hist_entries:
        details = dict(entry.details or {})
        details["filename"] = new_name
        entry.details = details

    db.commit()

    return {"message": "Rapport renommé", "report_id": report_id, "filename": new_name}


@router.get("/{report_id}")
async def get_report_status(report_id: str, db: Session = Depends(get_db)):
    """Retourne le statut d'un rapport"""
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="Rapport non trouvé")
    return {
        "report_id": str(report.id),
        "file_id": str(report.file_id),
        "status": report.status,
        "filename": report.filename,
        "total_rows": report.total_rows,
        "total_columns": report.total_columns,
        "file_size": report.file_size,
        "error_message": report.error_message,
    }


async def generate_report_background(report_id: str, file_id: str, request_data: dict, user_id: str = None):
    """Tâche de fond pour générer le rapport Excel"""
    db = SessionLocal()
    report = None
    try:
        report = db.query(Report).filter(Report.id == report_id).first()
        if not report:
            print(f"Report with ID {report_id} not found.")
            return

        excel_file = db.query(ExcelFile).filter(ExcelFile.id == file_id).first()
        if not excel_file:
            print(f"Excel file with ID {file_id} not found.")
            report.status = "failed"
            db.commit()
            return

        file_path = storage.get_file(excel_file.filename)
        output_path = Path("data/reports") / report.filename
        output_path.parent.mkdir(parents=True, exist_ok=True)

        columns_info = [{"name": col["name"], "type": col.get("type", "string")} for col in request_data["selected_columns"]]
        result = await excel_generator.generate_excel(
            input_path=file_path,
            output_path=output_path,
            columns=columns_info,
            date_format=request_data.get("date_format", "%d/%m/%Y %H:%M:%S")
        )

        report.status = "completed"
        report.output_path = str(output_path)
        report.total_rows = result["total_rows"]
        report.total_columns = result["total_columns"]
        report.file_size = result["file_size"]
        db.commit()

        # Journaliser le succès
        HistoryService(db).log_action(
            file_id=file_id,
            report_id=report_id,
            action="generate",
            status="success",
            user_id=user_id,
            details={
                "filename": report.filename,
                "total_rows": result["total_rows"],
                "total_columns": result["total_columns"],
                "report_id": report_id,
            },
            file_size=result["file_size"],
        )
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        if report:
            report.status = "failed"
            db.commit()
            try:
                HistoryService(db).log_action(
                    file_id=file_id,
                    report_id=report_id,
                    action="generate",
                    status="failed",
                    user_id=user_id,
                    details={"filename": report.filename, "report_id": report_id},
                    error_message=str(e),
                )
            except Exception:
                pass
    finally:
        db.close()


