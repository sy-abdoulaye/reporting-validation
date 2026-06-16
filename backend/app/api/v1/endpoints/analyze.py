
from fastapi import APIRouter, Depends, HTTPException
from app.models.excel import ExcelFile

from sqlalchemy.orm import Session
from app.core.database import get_db
from app.api.v1.endpoints.upload import StorageService
from app.services.column_detector import ColumnDetector


router = APIRouter(prefix="/analyze", tags=["analyze"])
column_detector = ColumnDetector()
storage = StorageService()

@router.get("/{file_id}")
async def analyze_file(file_id: str, db: Session = Depends(get_db)):
    """Analyse un fichier Excel et retourne les résultats"""
    # Récupérer les métadonnées du fichier depuis la base de données
    excel_file = db.query(ExcelFile).filter(ExcelFile.id == file_id).first()
    if not excel_file:
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")

    try:
        # Récupérer le chemin du fichier depuis le stockage
        file_path = storage.get_file(excel_file.filename)

        # Analyser le fichier pour détecter les colonnes
        detected_columns = column_detector.analyse_file(file_path)

        return {
            "file_id": file_id,
            "original_filename": excel_file.original_filename,
            "total_rows": detected_columns["total_rows"],
            "total_columns": detected_columns["total_columns"],
            "columns": detected_columns["columns"],
            "preview": detected_columns["preview"]
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Fichier non trouvé dans le stockage.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'analyse du fichier: {str(e)}")