from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# URL de connexion
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost/reporting")

# Création du moteur SQLALchemy
engine = create_engine(
    DATABASE_URL,
    echo=True, # Affiche les requêtes SQL (à désactiver en production)
    pool_size=5,
    max_overflow=10
)

# Session locale
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modéles
Base = declarative_base()

# Dépendance FastAPI pour obtenir la session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()