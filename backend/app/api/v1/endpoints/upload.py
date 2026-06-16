from datetime import date, datetime
from io import BytesIO
from fastapi import APIRouter, HTTPException, UploadFile, File, Depends
from sqlalchemy.orm import Session
import numpy as np
import pandas as pd

from app.core.database import get_db
from app.core.auth import AuthDependencies
from app.services.storage import StorageService
from app.services.history_service import HistoryService
from app.services.excel_reader import read_excel_bytes
from app.models.excel import ExcelFile
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])
storage = StorageService()


@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(AuthDependencies.get_current_active_user)
):
    print(f"📁 Upload reçu: {file.filename}")
    # Valider le type de fichier
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Format de fichier non supporté. Veuillez uploader un fichier .xlsx ou .xls.")

    file_info = None
    try:
        # Lire le contenu du fichier une seule fois
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Le fichier uploadé est vide.")

        # Enregistrer le fichier et obtenir les métadonnées
        file_info = await storage.save_upload(file, content)

        # Lire le fichier en détectant automatiquement la vraie ligne d'en-tête
        # (saute les lignes de titre/préambule qui produisent des colonnes "Unnamed")
        df = read_excel_bytes(content, file.filename, nrows=10)
        df.columns = [str(c).strip() for c in df.columns]
        df = df.fillna("")  # Remplacer les NaN par des chaînes vides pour éviter les problèmes de validation

        def sanitize_value(value):
            if isinstance(value, (datetime, date)):
                return value.isoformat()
            if isinstance(value, (pd.Timestamp, pd.Timedelta)):
                return str(value)
            if isinstance(value, np.generic):
                return value.item()
            if isinstance(value, bytes):
                return value.decode("utf-8", errors="ignore")
            return value

        #  Créer un aperçu des données pour la validation côté client
        preview = {
            "header": df.columns.tolist(), # Convertir les colonnes en liste pour une meilleure lisibilité
            "rows": [[sanitize_value(value) for value in row] for row in df.values.tolist()]
        }

        # Enregistrer les métadonnées du fichier dans la base de données
        excel_file = ExcelFile(
            filename=file_info["storage_filename"],
            original_filename=file_info["filename"],
            file_size=file_info["size"],
            file_hash=file_info["hash"],
            status="uploaded",
            headers=preview["header"],  # Enregistrer les en-têtes pour une validation future
            preview_data=preview # Enregistrer l'aperçu des données pour une validation future
        )

        db.add(excel_file) # Ajouter l'enregistrement à la session
        db.commit() # Valider les changements dans la base de données
        db.refresh(excel_file) # Rafraîchir l'instance pour obtenir l'ID généré

        print(f"✅ Fichier enregistré en base avec ID: {excel_file.id}")

        # Journaliser l'action dans l'historique (associée à l'utilisateur)
        HistoryService(db).log_action(
            file_id=excel_file.id,
            action="upload",
            status="success",
            user_id=current_user.id,
            details={
                "filename": excel_file.original_filename,
                "total_columns": len(excel_file.headers or []),
            },
            file_size=excel_file.file_size,
        )

        return {
            "id": str(excel_file.id),
            "original_filename": excel_file.original_filename,
            "file_size": excel_file.file_size,
            "status": excel_file.status,
            "headers": excel_file.headers,
            "preview_data": excel_file.preview_data
        }
    except Exception as e:
        # En cas d'erreur, supprimer le fichier du stockage pour éviter les fichiers orphelins
        if file_info is not None:
            storage.delete_file(file_info["storage_filename"])
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload du fichier: {str(e)}")


@router.get("/{file_id}")
def get_file_info(file_id: str, db: Session = Depends(get_db)):
    """Récupère les métadonnées d'un fichier uploadé par son ID"""
    excel_file = db.query(ExcelFile).filter(ExcelFile.id == file_id).first()
    if not excel_file:
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")

    return {
        "id": str(excel_file.id),
        "original_filename": excel_file.original_filename,
        "file_size": excel_file.file_size,
        "status": excel_file.status,
        "headers": excel_file.headers,
        "preview_data": excel_file.preview_data
    }


