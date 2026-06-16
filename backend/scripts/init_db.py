#!/usr/bin/env python
"""Script pour initialiser la base de données """

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import engine, Base
from app.models import excel, report, history, user# Import pour enregistrer les modèles

def init_db():
    """Crée toutes les tables"""
    print("Création des tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables créées avec succès!")

if __name__ == "__main__":
    init_db()