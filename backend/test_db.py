from app.core.database import SessionLocal, engine
from app.models.excel import ExcelFile
from datetime import datetime
import uuid


def test_database():
    """Test simple de la base"""

    # 1. Créer une session
    db = SessionLocal()
    try:
        # 2. Créer un enregistrement test
        test_file = ExcelFile(
            filename="test.xlsx",
            original_filename="test_upload.xlsx",
            file_size=1024,
            file_hash="test_hash_123",
            status="pending"
        )

        # 3. Ajouter à la base
        db.add(test_file)
        db.commit()
        db.refresh(test_file)

        print(f"✅ Fichier créé avec ID: {test_file.id}")

        # 4. Lire l'enregistrement
        retrieved = db.query(ExcelFile).filter(ExcelFile.id == test_file.id).first()
        print(f"✅ Fichier récupéré: {retrieved.filename}")

        # 5. Supprimer (nettoyage)
        db.delete(retrieved)
        db.commit()
        print("✅ Nettoyage effectué")

    except Exception as e:
        print(f"❌ Erreur: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    test_database()