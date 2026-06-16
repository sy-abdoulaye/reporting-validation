from datetime import datetime
import hashlib
from pathlib import Path
from fastapi import UploadFile, HTTPException



class StorageService:
    def __init__(self, base_path: str = "data/uploads"):
        """Service de gestion des fichiers"""
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, file: UploadFile, content: bytes | None = None) -> dict:
        """Enregistre le fichier uploadé et retourne les métadonnées"""
        # Générer un nom de fichier unique
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{timestamp}_{file.filename}"
        file_path = self.base_path / unique_filename

        # Lire le contenu du fichier pour obtenir sa taille
        if content is None:
            content = await file.read()
        file_size = len(content)

        if file_size > 50 * 1024 * 1024:  # Limite de 50MB
            raise HTTPException(status_code=413, detail="Le fichier dépasse la limite de taille de 50MB.")

        # Calculer le hash du fichier pour éviter les doublons
        file_hash = hashlib.sha256(content).hexdigest()

        with open(file_path, "wb") as f:
            f.write(content)

        return {
            "path": str(file_path),
            "filename": file.filename,
            "storage_filename": unique_filename,
            "size": file_size,
            "hash": file_hash
        }

    def get_file(self, filename: str) -> Path:
        """Retourne un fichier par son nom"""
        file_path = self.base_path / filename
        if file_path.exists():
            return file_path
        raise FileNotFoundError(f"Fichier {filename} non trouvé dans le stockage.")

    def delete_file(self, filename: str):
        """Supprime un fichier du stockage"""
        file_path = self.base_path / filename
        if file_path.exists():
            file_path.unlink()
            return True
        return False