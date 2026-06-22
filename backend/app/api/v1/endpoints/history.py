from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from datetime import datetime, timedelta
from app.core.database import get_db
from app.core.auth import AuthDependencies
from app.models.history import ProcessingHistory
from app.models.user import User
from app.services.history_service import HistoryService

router = APIRouter(prefix="/history", tags=["history"])

@router.get("/")
async def get_history(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, regex="^(pending|success|failed)$"),
    action: Optional[str] = Query(None, regex="^(upload|analyze|generate|email)$"),
    search: Optional[str] = None,
    days: Optional[int] = Query(None, ge=1, le=365),
    user_id: Optional[UUID] = Query(None, description="Filtrer par utilisateur (admin uniquement)"),
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Récupère l'historique des traitements.

    - Un utilisateur standard ne voit que ses propres entrées.
    - Un administrateur voit toutes les entrées et peut filtrer par `user_id`.
    """
    service = HistoryService(db)

    # Calculer la période si demandée
    date_from = None
    if days:
        date_from = datetime.utcnow() - timedelta(days=days)

    # Portée : non-admin restreint à ses entrées ; admin = tout, avec filtre optionnel
    if current_user.is_superuser:
        effective_user_id = user_id
    else:
        effective_user_id = current_user.id

    result = service.get_history(
        page=page,
        limit=limit,
        status=status,
        action=action,
        search=search,
        date_from=date_from,
        user_id=effective_user_id
    )

    return result

@router.get("/file/{file_id}")
async def get_file_history(
    file_id: str,
    current_user: User = Depends(AuthDependencies.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Récupère l'historique d'un fichier spécifique
    """
    from app.models.excel import ExcelFile

    # Vérifier les droits d'accès
    excel_file = db.query(ExcelFile).filter(ExcelFile.id == file_id).first()
    if not excel_file:
        raise HTTPException(404, "Fichier non trouvé")

    if not current_user.is_superuser and excel_file.user_id != current_user.id:
        raise HTTPException(403, "Accès non autorisé")

    service = HistoryService(db)
    history = service.get_file_history(file_id)

    return {
        "file_id": file_id,
        "filename": excel_file.original_filename,
        "history": history
    }

@router.get("/statistics")
async def get_statistics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(AuthDependencies.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Statistiques des traitements
    """
    # Seuls les admins peuvent voir les stats globales
    if not current_user.is_superuser:
        raise HTTPException(403, "Accès réservé aux administrateurs")

    service = HistoryService(db)
    stats = service.get_statistics(days)

    return stats

@router.delete("/{history_id}")
async def delete_history_entry(
    history_id: str,
    current_user: User = Depends(AuthDependencies.get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Supprime une seule entrée d'historique.
    L'utilisateur ne peut supprimer que ses propres entrées (admin : toutes).
    """
    entry = db.query(ProcessingHistory).filter(
        ProcessingHistory.id == history_id
    ).first()
    if not entry:
        raise HTTPException(404, "Entrée d'historique non trouvée")

    if not current_user.is_superuser and entry.user_id != current_user.id:
        raise HTTPException(403, "Accès non autorisé")

    db.delete(entry)
    db.commit()

    return {"message": "Entrée supprimée", "id": history_id}

@router.delete("/")
async def clear_history(
    older_than_days: int = Query(90, ge=30, le=365),
    current_user: User = Depends(AuthDependencies.get_current_user),
    db: Session = Depends(get_db)
):
    """
    Nettoie l'historique (admin uniquement)
    """
    if not current_user.is_superuser:
        raise HTTPException(403, "Accès réservé aux administrateurs")

    cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)

    deleted = db.query(ProcessingHistory).filter(
        ProcessingHistory.created_at < cutoff_date
    ).delete()

    db.commit()

    return {
        "message": f"{deleted} entrées supprimées",
        "older_than_days": older_than_days
    }