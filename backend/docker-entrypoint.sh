#!/usr/bin/env bash
set -e

echo "⏳ Attente de la base de données PostgreSQL…"

# Attendre que PostgreSQL soit prêt (max ~60s)
python <<'PYEOF'
import os, time, sys
import psycopg2

url = os.getenv("DATABASE_URL", "")
for i in range(30):
    try:
        conn = psycopg2.connect(url)
        conn.close()
        print("✅ Base de données accessible.")
        sys.exit(0)
    except Exception as e:
        print(f"  … tentative {i+1}/30 : {e}")
        time.sleep(2)
print("❌ Impossible de joindre la base de données.")
sys.exit(1)
PYEOF

echo "🔧 Initialisation des tables…"
python scripts/init_db.py

echo "🚀 Démarrage de l'API sur 0.0.0.0:8000…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
