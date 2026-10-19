# Reporting App

Application web de reporting à partir de fichiers Excel : upload, analyse automatique des colonnes, génération de rapports formatés, envoi par email et historique complet des traitements — avec authentification, gestion des utilisateurs et tableau de bord d'administration.

## Fonctionnalités

- **Upload & analyse** — dépose un fichier Excel (`.xlsx`/`.xls`), détection automatique des colonnes (dates, types, formats) via `ColumnDetector`
- **Profils de colonnes** — sauvegarde de mappings de colonnes réutilisables par utilisateur, avec un profil par défaut
- **Génération de rapports** — transformation du fichier source vers un rapport Excel mis en forme (styles, types de dates réels, en-têtes), génération en tâche de fond
- **Envoi par email** — distribution directe des rapports générés depuis l'application
- **Historique & statistiques** — traçabilité de chaque traitement (par fichier, par utilisateur), purge automatique configurable (`cleanup_history.py`)
- **Authentification** — JWT (access + refresh token), mots de passe hashés en bcrypt, verrouillage de compte après 5 échecs, réinitialisation de mot de passe par email
- **Clés API** — clés dédiées à l'intégration externe, avec permissions, quotas (par minute / par jour) et expiration
- **Administration** — gestion des utilisateurs, tableau de bord (statistiques système, graphiques d'activité, top utilisateurs, activité récente)
- **Sauvegardes automatiques** — `pg_dump` planifié avec rétention GFS (quotidien/hebdomadaire/mensuel), voir [BACKUP.md](BACKUP.md)

## Stack technique

| Composant | Choix |
|---|---|
| Backend | FastAPI, SQLAlchemy + Alembic (migrations), PostgreSQL |
| Traitement Excel | pandas, openpyxl |
| Authentification | python-jose (JWT), passlib/bcrypt |
| Frontend | HTML/CSS/JS natif (pas de framework) |
| Reverse proxy | nginx (terminaison TLS) |
| Déploiement | Docker Compose |

## Architecture

```
┌──────────────┐      HTTPS       ┌──────────────┐      SQL       ┌──────────────┐
│   Frontend   │ ───────────────▶ │   Backend    │ ─────────────▶ │  PostgreSQL  │
│ (nginx + JS) │ ◀─────────────── │  (FastAPI)   │ ◀───────────── │   (reporting)│
└──────────────┘    JSON / API    └──────────────┘                └──────────────┘
                                         │
                                         ├── Upload / Analyze / Generate / Email
                                         ├── Auth (JWT) & Admin
                                         └── History & Audit

┌──────────────┐
│  db-backup   │  pg_dump planifié (GFS) → ./backups/ (bind-mount hôte)
└──────────────┘
```

## Démarrage rapide

```bash
git clone https://github.com/sy-abdoulaye/reporting-app.git
cd reporting-app

# Renseigner backend/.env (SECRET_KEY, SMTP si envoi d'email souhaité, etc.)
cp backend/.env backend/.env.local  # ou éditer directement backend/.env

docker compose up -d --build
```

- Frontend : `https://localhost:8080`
- API + documentation Swagger : `https://localhost:8000/docs`

### Créer un compte administrateur

```bash
docker compose exec backend python scripts/make_admin.py <nom_utilisateur>
```

## Structure du projet

```
reporting-app/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # upload, analyze, generate, email, history, auth, admin, column_profiles
│   │   ├── core/                # config, auth, security, database
│   │   ├── models/              # User, ApiKey, Report, History, ColumnProfile, Audit
│   │   └── services/            # excel_reader/generator, column_detector, dashboard, email, storage, audit
│   ├── migrations/               # Alembic
│   └── scripts/                  # init_db, make_admin, cleanup_history
├── frontend/                     # pages HTML + JS (login, register, reports, history, admin…)
├── scripts/                       # sauvegarde/restauration PostgreSQL (GFS)
├── docker-compose.yml
└── BACKUP.md                      # stratégie de sauvegarde détaillée
```

## Configuration

Variables principales (`backend/.env`, voir aussi les valeurs équivalentes dans `docker-compose.yml`) :

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Connexion PostgreSQL |
| `SECRET_KEY` | Clé de signature des JWT — **à régénérer** avant tout déploiement (`python -c "import secrets; print(secrets.token_urlsafe(32))"`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Envoi d'email (réinitialisation de mot de passe, distribution de rapports) |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | Expéditeur affiché |

## Sauvegarde & restauration

Voir [BACKUP.md](BACKUP.md) pour la stratégie complète (rétention GFS, procédure de restauration, garde-fous contre l'écrasement par une base vide).

## Licence

Projet personnel — à adapter selon l'usage souhaité.
