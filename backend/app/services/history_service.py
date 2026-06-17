from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, func
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.models.history import ProcessingHistory
from app.models.report import Report

class HistoryService:
    """Service de gestion de l'historique"""

    def __init__(self, db: Session):
        self.db = db

    def log_action(
        self,
        file_id: UUID,
        action: str,
        status: str,
        details: Dict[str, Any] = None,
        error_message: str = None,
        report_id: UUID = None,
        user_id: UUID = None,
        processing_time_ms: int = None,
        file_size: int = None
    ) -> ProcessingHistory:
        """Enregistre une action dans l'historique"""

        history = ProcessingHistory(
            file_id=file_id,
            report_id=report_id,
            user_id=user_id,
            original_filename=details.get('filename', 'unknown') if details else 'unknown',
            action=action,
            status=status,
            details=details or {},
            error_message=error_message,
            processing_time_ms=processing_time_ms,
            file_size=file_size,
            completed_at=datetime.utcnow() if status == 'success' else None
        )

        self.db.add(history)
        self.db.commit()
        self.db.refresh(history)

        return history

    def get_history(
        self,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        action: Optional[str] = None,
        search: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """Récupère l'historique avec filtres"""

        query = self.db.query(ProcessingHistory)

        # Filtres
        if status:
            query = query.filter(ProcessingHistory.status == status)

        if action:
            query = query.filter(ProcessingHistory.action == action)

        if search:
            query = query.filter(
                ProcessingHistory.original_filename.ilike(f"%{search}%")
            )

        if date_from:
            query = query.filter(ProcessingHistory.created_at >= date_from)

        if date_to:
            query = query.filter(ProcessingHistory.created_at <= date_to)

        if user_id:
            query = query.filter(ProcessingHistory.user_id == user_id)

        # Pagination
        total = query.count()
        items = query.order_by(
            desc(ProcessingHistory.created_at)
        ).offset((page - 1) * limit).limit(limit).all()

        # Récupérer les noms des propriétaires en une seule requête (évite le N+1)
        from app.models.user import User
        owner_ids = {item.user_id for item in items if item.user_id}
        owners = {}
        if owner_ids:
            for u in self.db.query(User).filter(User.id.in_(owner_ids)).all():
                owners[u.id] = u.full_name or u.username

        # Enrichir avec les données associées
        enriched_items = []
        for item in items:
            enriched = {
                "id": str(item.id),
                "file_id": str(item.file_id),
                "report_id": str(item.report_id) if item.report_id else None,
                "user_id": str(item.user_id) if item.user_id else None,
                "username": owners.get(item.user_id),
                "filename": item.original_filename,
                "action": item.action,
                "status": item.status,
                "details": item.details,
                "error_message": item.error_message,
                "created_at": item.created_at.isoformat(),
                "completed_at": item.completed_at.isoformat() if item.completed_at else None,
                "processing_time_ms": item.processing_time_ms,
                "file_size": item.file_size
            }

            # Ajouter les informations du rapport si disponible
            if item.report_id:
                report = self.db.query(Report).filter(Report.id == item.report_id).first()
                if report:
                    enriched["report"] = {
                        "filename": report.filename,
                        "status": report.status,
                        "email_sent": getattr(report, "email_sent", None),
                        "email_recipients": getattr(report, "email_recipients", None),
                    }

            enriched_items.append(enriched)

        return {
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit,
            "items": enriched_items
        }

    def get_file_history(self, file_id: UUID) -> List[Dict[str, Any]]:
        """Récupère tout l'historique d'un fichier spécifique"""

        history = self.db.query(ProcessingHistory).filter(
            ProcessingHistory.file_id == file_id
        ).order_by(ProcessingHistory.created_at).all()

        return [
            {
                "id": str(h.id),
                "action": h.action,
                "status": h.status,
                "details": h.details,
                "created_at": h.created_at.isoformat(),
                "processing_time_ms": h.processing_time_ms
            }
            for h in history
        ]

    def get_statistics(self, days: int = 30) -> Dict[str, Any]:
        """Statistiques des traitements"""

        since = datetime.utcnow() - timedelta(days=days)

        query = self.db.query(ProcessingHistory).filter(
            ProcessingHistory.created_at >= since
        )

        # Nombre total
        total = query.count()

        # Par action
        actions = {}
        for action in ['upload', 'analyze', 'generate', 'email']:
            count = query.filter(ProcessingHistory.action == action).count()
            actions[action] = count

        # Par statut
        status_counts = {
            'success': query.filter(ProcessingHistory.status == 'success').count(),
            'failed': query.filter(ProcessingHistory.status == 'failed').count(),
            'pending': query.filter(ProcessingHistory.status == 'pending').count()
        }

        # Temps moyen de traitement
        avg_time = self.db.query(func.avg(ProcessingHistory.processing_time_ms)).filter(
            ProcessingHistory.status == 'success',
            ProcessingHistory.created_at >= since
        ).scalar()

        # Fichiers les plus traités
        top_files = self.db.query(
            ProcessingHistory.file_id,
            func.count(ProcessingHistory.id).label('count')
        ).filter(
            ProcessingHistory.created_at >= since
        ).group_by(ProcessingHistory.file_id).order_by(
            func.count(ProcessingHistory.id).desc()
        ).limit(5).all()

        return {
            "period_days": days,
            "total_actions": total,
            "by_action": actions,
            "by_status": status_counts,
            "avg_processing_time_ms": float(avg_time) if avg_time else 0,
            "most_processed_files": [
                {"file_id": str(f[0]), "count": f[1]} for f in top_files
            ]
        }