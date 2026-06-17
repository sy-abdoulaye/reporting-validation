from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from app.models.audit import AuditLog
from app.models.user import User


# Champs autorisés pour le tri (protège contre l'injection de colonnes arbitraires)
SORTABLE_FIELDS = {
    "created_at": AuditLog.created_at,
    "action": AuditLog.action,
    "category": AuditLog.category,
    "status": AuditLog.status,
    "username": AuditLog.username,
}


class AuditService:
    """Service de journalisation et de consultation du journal d'audit."""

    def __init__(self, db: Session):
        self.db = db

    def log(
        self,
        action: str,
        category: str = "system",
        status: str = "success",
        user: Optional[User] = None,
        user_id: Optional[UUID] = None,
        username: Optional[str] = None,
        target_type: Optional[str] = None,
        target_id: Optional[Any] = None,
        target_label: Optional[str] = None,
        description: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[AuditLog]:
        """Enregistre une entrée d'audit.

        La journalisation ne doit jamais faire échouer l'action métier : toute
        erreur est avalée (rollback) et ``None`` est retourné.
        """
        try:
            if user is not None:
                user_id = user_id or user.id
                username = username or user.username

            entry = AuditLog(
                user_id=user_id,
                username=username,
                action=action,
                category=category,
                status=status,
                target_type=target_type,
                target_id=str(target_id) if target_id is not None else None,
                target_label=target_label,
                description=description,
                details=details or {},
                ip_address=ip_address,
            )
            self.db.add(entry)
            self.db.commit()
            self.db.refresh(entry)
            return entry
        except Exception as e:  # noqa: BLE001 - journalisation best-effort
            print(f"⚠️  Échec d'enregistrement de l'audit ({action}): {e}")
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    def get_logs(
        self,
        page: int = 1,
        limit: int = 20,
        category: Optional[str] = None,
        action: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        user_id: Optional[UUID] = None,
        days: Optional[int] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Liste paginée du journal d'audit avec filtres, recherche et tri."""

        query = self.db.query(AuditLog)

        if category:
            query = query.filter(AuditLog.category == category)
        if action:
            query = query.filter(AuditLog.action == action)
        if status:
            query = query.filter(AuditLog.status == status)
        if user_id:
            query = query.filter(AuditLog.user_id == user_id)
        if days:
            query = query.filter(AuditLog.created_at >= datetime.utcnow() - timedelta(days=days))
        if search:
            pattern = f"%{search}%"
            query = query.filter(
                or_(
                    AuditLog.username.ilike(pattern),
                    AuditLog.description.ilike(pattern),
                    AuditLog.target_label.ilike(pattern),
                    AuditLog.action.ilike(pattern),
                )
            )

        # Tri sécurisé
        column = SORTABLE_FIELDS.get(sort_by, AuditLog.created_at)
        direction = asc if sort_order == "asc" else desc
        query = query.order_by(direction(column))

        total = query.count()
        items = query.offset((page - 1) * limit).limit(limit).all()

        return {
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if total else 1,
            "items": [self._serialize(i) for i in items],
        }

    def get_distinct_actions(self) -> List[str]:
        """Liste des actions distinctes présentes (pour alimenter un filtre)."""
        rows = self.db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
        return [r[0] for r in rows]

    @staticmethod
    def _serialize(entry: AuditLog) -> Dict[str, Any]:
        return {
            "id": str(entry.id),
            "user_id": str(entry.user_id) if entry.user_id else None,
            "username": entry.username,
            "action": entry.action,
            "category": entry.category,
            "status": entry.status,
            "target_type": entry.target_type,
            "target_id": entry.target_id,
            "target_label": entry.target_label,
            "description": entry.description,
            "details": entry.details,
            "ip_address": entry.ip_address,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
