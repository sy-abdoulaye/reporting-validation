from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.endpoints.upload import router as upload_router
from app.api.v1.endpoints.analyze import router as analyze_router
from app.api.v1.endpoints.generate import router as generate_router
from app.api.v1.endpoints.email import router as email_router
from app.api.v1.endpoints.history import router as history_router
from app.api.v1.endpoints.auth import router as api_router
from app.api.v1.endpoints.admin import router as admin_router
from app.api.v1.endpoints.column_profiles import router as profiles_router


app = FastAPI(title="Reporting API")

# Ajouter après la création de l'app
app.add_middleware(
    CORSMiddleware,
    # Autorise localhost, 127.0.0.1 et toute IP privée (LAN / Docker host) sur n'importe quel port
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.\d+\.\d+\.\d+)(:\d+)?",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")  # Importer le router d'authentification
app.include_router(analyze_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")  # Importer le router d'administration
app.include_router(email_router, prefix="/api/v1")  # Importer le router d'envoi d'emails
app.include_router(generate_router, prefix="/api/v1")  # Importer le router de génération de rapports
app.include_router(history_router, prefix="/api/v1")  # Importer le router d'historique
app.include_router(upload_router, prefix="/api/v1")
app.include_router(profiles_router, prefix="/api/v1")  # Importer le router des profils de colonnes

@app.get('/')
async def root():
    return {"message": "Reporting API ready"}

@app.get('/health')
async def health():
    return {"status": "health"}