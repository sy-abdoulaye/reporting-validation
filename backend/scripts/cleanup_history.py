#!/usr/bin/env python
"""
Script de nettoyage automatique de l'historique
À exécuter via cron ou tâche planifiée
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from app.core.database import SessionLocal
from app.models.history import ProcessingHistory
from app.services.storage import StorageService
from app.models.excel import ExcelFile, Report

def cleanup_old_history(retention_days: int = 90):
    """
    Supprime l'historique plus vieux que retention_days
    """
    db = SessionLocal()
    storage = StorageService()

    cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

    try:
        # Récupérer les anciens fichiers
        old_files = db.query(ExcelFile).filter(
            ExcelFile.created_at < cutoff_date
        ).all()

        deleted_count = 0
        for file in old_files:
            # Supprimer les fichiers physiques
            try:
                storage.delete_file(file.filename)
            except:
                pass

            # Supprimer les rapports associés
            reports = db.query(Report).filter(Report.source_file_id == file.id).all()
            for report in reports:
                try:
                    storage.delete_file(report.storage_path)
                except:
                    pass

            db.delete(file)
            deleted_count += 1

        # Supprimer l'historique orphelin
        deleted_history = db.query(ProcessingHistory).filter(
            ProcessingHistory.created_at < cutoff_date
        ).delete()

        db.commit()

        print(f"✅ Nettoyage terminé:")
        print(f"   - Fichiers supprimés: {deleted_count}")
        print(f"   - Entrées historique supprimées: {deleted_history}")

    except Exception as e:
        print(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=90, help="Jours de rétention")
    args = parser.parse_args()

    cleanup_old_history(args.days)