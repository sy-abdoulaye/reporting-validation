from sqlalchemy.orm import Session
from sqlalchemy import func, and_, desc
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from uuid import UUID

from app.models.user import ApiKey, User
from app.models.excel import ExcelFile
from app.models.report import Report
from app.models.history import ProcessingHistory


class DashboardService:
    """Service pour le dashboard administrateur"""

    def __init__(self, db: Session):
        self.db = db

    async def get_system_stats(self, days: int = 30) -> Dict[str, Any]:
        """Statistiques système globales"""

        # Calculer la date de début pour les statistiques
        sincce = datetime.utcnow() - timedelta(days=days)

        # Statistiques utilisateurs
        total_users =  self.db.query(User).count()
        actives_users = self.db.query(User).filter(User.is_active == True).count()
        new_users = self.db.query(User).filter(User.created_at >= sincce).count()

        # Statistiques fichiers
        total_files = self.db.query(ExcelFile).count()
        total_files_size = self.db.query(func.sum(ExcelFile.file_size)).scalar() or 0
        files_this_month = self.db.query(ExcelFile).filter(ExcelFile.created_at >= sincce).count()

        # Statistiques de traitement
        total_processings = self.db.query(ProcessingHistory).count()
        successful_processings = self.db.query(ProcessingHistory).filter(ProcessingHistory.status == "success").count()
        failed_processings = self.db.query(ProcessingHistory).filter(ProcessingHistory.status == "failed").count()

        # Calcul du temps de traitement moyen pour les succès récents
        avg_time = self.db.query(func.avg(ProcessingHistory.processing_time_ms).filter(
            ProcessingHistory.status == "success",
            ProcessingHistory.created_at >= sincce
        )).scalar() or 0


        storage_used = total_files_size
        storage_limit = 10 * 1024 * 1024 * 1024  # 10 GB
        storage_percent = (storage_used / storage_limit) * 100 if storage_limit > 0 else 0

        return {
            "users": {
                "total": total_users,
                "active": actives_users,
                "new_last_30_days": new_users,
                "inactive": total_users - actives_users
            },
            "files": {
                "total": total_files,
                "total_size_bytes": total_files_size,
                "this_month": files_this_month,
                "total_size_human": self._format_bytes(total_files_size)
            },
            "processings": {
                "total": total_processings,
                "successful": successful_processings,
                "failed": failed_processings,
                "avg_processing_time_ms": round(avg_time, 2),
                "success_rate_percentage": round((successful_processings / total_processings) * 100, 2) if total_processings > 0 else 0
            },
            "storage": {
                "used_bytes": storage_used,
                "used_human": self._format_bytes(storage_used),
                "limit_bytes": storage_limit,
                "limit_human": self._format_bytes(storage_limit),
                "used_percent": round(storage_percent, 2)
            },
            "period_days": days
        }

    async def get_activity_chart(self, days: int = 30) -> Dict[str, Any]:
        """Données pour les graphiques d'activité (fichiers uploadés, traitements)"""

        sincce = datetime.utcnow() - timedelta(days=days)

        #  Activité des fichiers uploadés par jour
        activity = self.db.query(
            func.date(ProcessingHistory.created_at).label("date"),
            func.count(ProcessingHistory.id).label("count")
        ).filter(
            ProcessingHistory.created_at >= sincce
        ).group_by(
            func.date(ProcessingHistory.created_at)
        ).order_by(
            func.date(ProcessingHistory.created_at)
        ).all()

        # Activité par action
        by_action = self.db.query(
            ProcessingHistory.action,
            func.count(ProcessingHistory.id).label("count")
        ).filter(
            ProcessingHistory.created_at >= sincce
        ).group_by(
            ProcessingHistory.action
        ).all()

        # Activité par statut
        daily_status = self.db.query(
            func.date(ProcessingHistory.created_at).label("date"),
            ProcessingHistory.status,
            func.count(ProcessingHistory.id).label("count")
        ).filter(
            ProcessingHistory.created_at >= sincce
        ).group_by(
            func.date(ProcessingHistory.created_at),
            ProcessingHistory.status
        ).order_by(
            func.date(ProcessingHistory.created_at)
        ).all()

        # Formatage des résultats
        dates = [str(record[0]) for record in activity]
        counts = [record[1] for record in activity]

        actions_data = {action: 0 for action in ["upload", "analyze", "generate", "email"]}
        for action, count in by_action:
            if action in actions_data:
                actions_data[action] = count

        success_by_data = {}
        failed_by_data = {}
        for date, status, count in daily_status:
            if status == "success":
                success_by_data[str(date)] = count
            elif status == "failed":
                failed_by_data[str(date)] = count

        success_list = [success_by_data.get(date, 0) for date in dates]
        failed_list = [failed_by_data.get(date, 0) for date in dates]

        return {
            "daily_activity": {
                "dates": dates,
                "counts": counts
            },
            "by_action": actions_data,
            'success_vs_failed': {
                "dates": dates,
                "success": success_list,
                "failed": failed_list
            }
        }

    async def get_top_users(self, limit: int = 10) -> List[Dict[str, Any]]:
        """ Top utilisateurs par nombre de fichiers traités (rapports générés avec succès)."""

        # On ne compte que les générations de rapport réussies — c.-à-d. les
        # fichiers réellement traités — et non l'ensemble des actions d'historique.
        processed_count = func.count(ProcessingHistory.id).filter(
            ProcessingHistory.action == "generate",
            ProcessingHistory.status == "success",
        ).label('total_actions')

        top_users = self.db.query(
            User.id,
            User.username,
            User.email,
            User.full_name,
            processed_count,
        ).join(
            ProcessingHistory, ProcessingHistory.user_id == User.id, isouter=True
        ).group_by(
            # PostgreSQL exige toutes les colonnes non agrégées dans le GROUP BY
            User.id, User.username, User.email, User.full_name
        ).order_by(
            desc('total_actions')
        ).limit(limit).all()

        result = []
        for user in top_users:
            # Les fichiers/rapports ne sont pas liés à l'utilisateur par clé étrangère :
            # on dérive les compteurs depuis l'historique de traitement.
            counts = self._user_activity_counts(user.id)
            result.append({
                "id": str(user.id),
                "username": user.username,
                "email": user.email,
                "full_name": user.full_name,
                "total_actions": user.total_actions or 0,
                "file_count": counts["file_count"],
                "report_count": counts["report_count"],
            })

        return result

    def _user_activity_counts(self, user_id: UUID) -> Dict[str, int]:
        """Compteurs d'activité dérivés de l'historique (pas de FK user sur les fichiers)."""
        actions_count = self.db.query(ProcessingHistory).filter(
            ProcessingHistory.user_id == user_id
        ).count()
        file_count = self.db.query(
            func.count(func.distinct(ProcessingHistory.file_id))
        ).filter(
            ProcessingHistory.user_id == user_id,
            ProcessingHistory.action == "upload",
        ).scalar() or 0
        report_count = self.db.query(
            func.count(func.distinct(ProcessingHistory.report_id))
        ).filter(
            ProcessingHistory.user_id == user_id,
            ProcessingHistory.report_id.isnot(None),
        ).scalar() or 0
        return {
            "actions_count": actions_count,
            "file_count": file_count,
            "report_count": report_count,
        }

    async def get_recent_activity(self, limit: int = 20) -> List[Dict[str, Any]]:
        """ Activité récente (fichiers uploadés, traitements)"""

        recent = self.db.query(ProcessingHistory).order_by(
            desc(ProcessingHistory.created_at)
        ).limit(limit).all()

        result = []
        for activity in recent:
            # Récupérer l'utilisateur
            user = self.db.query(User).filter(User.id == activity.user_id).first() if activity.user_id else None

            result.append({
                "id": str(activity.id),
                "action": activity.action,
                "status": activity.status,
                "filename": activity.original_filename,
                "user": user.to_dict() if user else None,
                "details": activity.details,
                "processing_time_ms": activity.processing_time_ms,
                "created_at": activity.created_at.isoformat(),
                "error_message": activity.error_message
            })

        return result

    # Champs autorisés pour le tri de la liste des utilisateurs
    USER_SORT_FIELDS = {
        "created_at": User.created_at,
        "username": User.username,
        "email": User.email,
        "last_login": User.last_login,
        "full_name": User.full_name,
    }

    async def get_user_list(
        self,
        page: int = 1,
        limit: int = 20,
        search: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_superuser: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Liste des utilisateurs avec pagination, filtres et tri"""

        query = self.db.query(User)

        if search:
            query = query.filter(
                (User.username.ilike(f"%{search}%")) |
                (User.email.ilike(f"%{search}%")) |
                (User.full_name.ilike(f"%{search}%"))
            )

        if is_active is not None:
            query = query.filter(User.is_active == is_active)

        if is_superuser is not None:
            query = query.filter(User.is_superuser == is_superuser)

        total = query.count()

        # Tri sécurisé
        column = self.USER_SORT_FIELDS.get(sort_by, User.created_at)
        column = column.asc() if sort_order == "asc" else column.desc()
        users = query.order_by(column).offset((page - 1) * limit).limit(limit).all()

        # Enrichir avec des statistiques (dérivées de l'historique)
        users_data = []
        for user in users:
            counts = self._user_activity_counts(user.id)
            last_activity = self.db.query(ProcessingHistory).filter(
                ProcessingHistory.user_id == user.id
            ).order_by(desc(ProcessingHistory.created_at)).first()

            user_dict = user.to_dict()
            user_dict.update({
                "is_active": user.is_active,
                "actions_count": counts["actions_count"],
                "last_activity": last_activity.created_at.isoformat() if last_activity else None,
                "file_count": counts["file_count"],
                "report_count": counts["report_count"],
            })
            users_data.append(user_dict)

        return {
            "total": total,
            "page": page,
            "pages": (total + limit - 1) // limit if total else 1,
            "items": users_data
        }

    async def get_user_detail(self, user_id: UUID) -> Dict[str, Any]:
        """Détails complets d'un utilisateur pour l'administration"""
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Utilisateur non trouvé")

        counts = self._user_activity_counts(user.id)
        last_activity = self.db.query(ProcessingHistory).filter(
            ProcessingHistory.user_id == user.id
        ).order_by(desc(ProcessingHistory.created_at)).first()

        # Répartition des actions de traitement
        by_action_rows = self.db.query(
            ProcessingHistory.action, func.count(ProcessingHistory.id)
        ).filter(ProcessingHistory.user_id == user.id).group_by(ProcessingHistory.action).all()

        data = user.to_dict()
        data.update({
            "is_active": user.is_active,
            "phone": user.phone,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "failed_login_attempts": user.failed_login_attempts,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            "actions_count": counts["actions_count"],
            "file_count": counts["file_count"],
            "report_count": counts["report_count"],
            "last_activity": last_activity.created_at.isoformat() if last_activity else None,
            "by_action": {action: count for action, count in by_action_rows},
        })
        return data

    async def update_user(
        self,
        user_id: UUID,
        is_active: Optional[bool] = None,
        is_superuser: Optional[bool] = None,
        department: Optional[str] = None,
        job_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Met à jour les informations d'un utilisateur (actif, superuser, département, poste)"""

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("Utilisateur non trouvé")

        if is_active is not None:
            user.is_active = is_active
        if is_superuser is not None:
            user.is_superuser = is_superuser
        if department is not None:
            user.department = department
        if job_title is not None:
            user.job_title = job_title

        user.updated_at = datetime.utcnow()
        self.db.commit()

        return user.to_dict()

    async def delete_user(self, user_id: UUID) -> bool:
        """Supprime un utilisateur et toutes ses données associées (fichiers, rapports, historique)"""

        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        # Les fichiers (ExcelFile) et rapports (Report) ne sont pas liés à l'utilisateur
        # par clé étrangère ; on nettoie ce qui l'est réellement : historique et clés API.
        # Le journal d'audit est conservé (avec le nom dénormalisé) à des fins de traçabilité.
        self.db.query(ProcessingHistory).filter(ProcessingHistory.user_id == user_id).delete()
        self.db.query(ApiKey).filter(ApiKey.user_id == user_id).delete()

        # Supprimer l'utilisateur
        self.db.delete(user)
        self.db.commit()

        return True

    def _format_bytes(self, size: int) -> str:
        """Convertit les bytes en format lisible (KB, MB, GB)"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} PB"