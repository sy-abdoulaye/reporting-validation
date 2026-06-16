from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.core.database import get_db
from app.core.auth import AuthDependencies
from app.models.user import User
from app.services.dashboard import DashboardService

router = APIRouter(prefix="/admin", tags=["admin"])

# Dépendance pour vérifier que l'utilisateur est un superuser
# Cette dépendance peut être utilisée dans les endpoints d'administration pour restreindre l'accès aux superusers uniquement
AdminDependency = Depends(AuthDependencies.get_current_superuser)

@router.get("/dashboard/stats")
async def get_system_stats(
    days: int = 30,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """
    Endpoint pour récupérer les statistiques globales du système (nombre d'utilisateurs, fichiers, rapports, etc.)
    Accessible uniquement aux superusers.
    """
    service = DashboardService(db)
    return await service.get_system_stats(days)

@router.get("/dashboard/users")
async def get_activity_charts(
    days: int = 30,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """
    Endpoint pour récupérer les données d'activité des utilisateurs (nombre de fichiers uploadés, rapports générés, etc.)
    Accessible uniquement aux superusers.
    """
    service = DashboardService(db)
    return await service.get_activity_charts(days)

@router.get("/dashboard/top-users")
async def get_top_users(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """
    Endpoint pour récupérer les utilisateurs les plus actifs (en fonction du nombre de fichiers uploadés, rapports générés, etc.)
    Accessible uniquement aux superusers.
    """
    service = DashboardService(db)
    return await service.get_top_users(limit)

@router.get("/dashboard/recent-activity")
async def get_recent_activity(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """
    Endpoint pour récupérer les activités récentes du système (fichiers uploadés, rapports générés, etc.)
    Accessible uniquement aux superusers.
    """
    service = DashboardService(db)
    return await service.get_recent_activity(limit)

@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """Liste des utilisateurs"""
    service = DashboardService(db)
    return await service.get_user_list(
        page=page,
        limit=limit,
        search=search,
        is_active=is_active,
        is_superuser=is_superuser
    )

@router.put("/users/{user_id}")
async def update_user(
    user_id: UUID,
    is_active: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    department: Optional[str] = None,
    job_title: Optional[str] = None,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """Met à jour un utilisateur"""
    service = DashboardService(db)

    try:
        updated_user = await service.update_user(
            user_id=user_id,
            is_active=is_active,
            is_superuser=is_superuser,
            department=department,
            job_title=job_title
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/users/{user_id}")
async def update_user(
    user_id: UUID,
    is_active: Optional[bool] = None,
    is_superuser: Optional[bool] = None,
    department: Optional[str] = None,
    job_title: Optional[str] = None,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """Met à jour un utilisateur"""
    service = DashboardService(db)

    try:
        updated_user = await service.update_user(
            user_id=user_id,
            is_active=is_active,
            is_superuser=is_superuser,
            department=department,
            job_title=job_title
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: UUID,
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """Supprime un utilisateur"""
    service = DashboardService(db)

    # Ne pas se supprimer soi-même
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas vous supprimer vous-même")

    success = await service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    return {"message": "Utilisateur supprimé avec succès"}

@router.get("/system/health")
async def system_health(
    current_user: User = AdminDependency,
    db: Session = Depends(get_db)
):
    """État de santé du système"""

    # Vérifier la base de données
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Vérifier le stockage
    from pathlib import Path
    storage_path = Path("data/uploads")
    storage_status = "healthy"
    storage_usage = None

    if storage_path.exists():
        import shutil
        usage = shutil.disk_usage(storage_path)
        storage_usage = {
            "total_gb": round(usage.total / (1024**3), 2),
            "used_gb": round(usage.used / (1024**3), 2),
            "free_gb": round(usage.free / (1024**3), 2),
            "percent_used": round((usage.used / usage.total) * 100, 2)
        }

        if storage_usage["percent_used"] > 90:
            storage_status = "warning"

    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": db_status,
            "storage": storage_status,
            "api": "healthy"
        },
        "storage_usage": storage_usage
    }