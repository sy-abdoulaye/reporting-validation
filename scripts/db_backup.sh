#!/bin/sh
# ---------------------------------------------------------------------------
# Sauvegarde PostgreSQL (format custom compressé) avec rétention GFS.
# Conçu pour tourner DANS un conteneur disposant des outils client postgres
# (pg_dump, pg_restore) — voir le service "db-backup" du docker-compose.
#
# Variables d'environnement (toutes optionnelles, valeurs par défaut indiquées) :
#   PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE  → connexion (PGDATABASE=reporting)
#   BACKUP_DIR=/backups                         → racine des sauvegardes
#   RETENTION_DAILY=7        (jours)            → conservation des dumps quotidiens
#   RETENTION_WEEKLY=4       (semaines)         → conservation des copies hebdo
#   RETENTION_MONTHLY=6      (mois)             → conservation des copies mensuelles
#   WEEKLY_DOW=7   (1=lundi .. 7=dimanche)      → jour de la copie hebdomadaire
#   MONTHLY_DOM=01 (jour du mois sur 2 chiffres)→ jour de la copie mensuelle
# ---------------------------------------------------------------------------
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PGDATABASE="${PGDATABASE:-reporting}"
RETENTION_DAILY="${RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"
RETENTION_MONTHLY="${RETENTION_MONTHLY:-6}"
WEEKLY_DOW="${WEEKLY_DOW:-7}"
MONTHLY_DOM="${MONTHLY_DOM:-01}"

LOG_FILE="$BACKUP_DIR/backup.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [backup] $*" | tee -a "$LOG_FILE"; }
fail() { log "ERREUR: $*"; exit 1; }

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"

log "Démarrage de la sauvegarde de la base '$PGDATABASE' (hôte=${PGHOST:-local})"

# Garde-fou : ne JAMAIS sauvegarder une base vide.
# Évite qu'une base fraîchement (re)créée (ex. après `down -v`) ne produise une
# sauvegarde "piège" qui, restaurée par erreur, effacerait les données.
GUARD_TABLE="${GUARD_TABLE:-users}"
GUARD_MIN_ROWS="${GUARD_MIN_ROWS:-1}"
rows="$(psql -d "$PGDATABASE" -tAc "SELECT count(*) FROM \"$GUARD_TABLE\"" 2>/dev/null || echo MISSING)"
if [ "$rows" = "MISSING" ]; then
  log "IGNORÉE : table '$GUARD_TABLE' absente (base non initialisée). Aucune sauvegarde créée."
  exit 0
fi
if [ "$rows" -lt "$GUARD_MIN_ROWS" ]; then
  log "IGNORÉE : '$GUARD_TABLE' contient $rows ligne(s) (< $GUARD_MIN_ROWS) → base vide. Aucune sauvegarde créée."
  exit 0
fi

ts="$(date '+%Y%m%d_%H%M%S')"
file="$BACKUP_DIR/daily/${PGDATABASE}_${ts}.dump"
tmp="${file}.part"

# Dump au format custom (-Fc), compressé (-Z6) → fichier .part puis renommage atomique
if ! pg_dump -Fc -Z6 -f "$tmp" "$PGDATABASE" 2>>"$LOG_FILE"; then
  rm -f "$tmp"
  fail "pg_dump a échoué (voir $LOG_FILE)"
fi
mv "$tmp" "$file"

# Vérification d'intégrité : l'archive doit être lisible par pg_restore
if ! pg_restore --list "$file" >/dev/null 2>>"$LOG_FILE"; then
  rm -f "$file"
  fail "archive corrompue, supprimée : $file"
fi

size="$(du -h "$file" | cut -f1)"
log "Sauvegarde quotidienne OK : $(basename "$file") ($size)"

# --- Copies GFS (grandfather-father-son) ---
dow="$(date '+%u')"   # 1..7
dom="$(date '+%d')"   # 01..31
if [ "$dow" = "$WEEKLY_DOW" ]; then
  cp "$file" "$BACKUP_DIR/weekly/" && log "Copie hebdomadaire créée"
fi
if [ "$dom" = "$MONTHLY_DOM" ]; then
  cp "$file" "$BACKUP_DIR/monthly/" && log "Copie mensuelle créée"
fi

# --- Rétention : suppression des sauvegardes trop anciennes ---
prune() {
  dir="$1"; days="$2"; label="$3"
  count=0
  for f in $(find "$dir" -name '*.dump' -type f -mtime "+$days" 2>/dev/null); do
    rm -f "$f" && count=$((count + 1))
  done
  [ "$count" -gt 0 ] && log "Rétention $label : $count fichier(s) supprimé(s) (> $days j)"
  return 0
}
prune "$BACKUP_DIR/daily"   "$RETENTION_DAILY"               "quotidienne"
prune "$BACKUP_DIR/weekly"  "$((RETENTION_WEEKLY * 7))"      "hebdomadaire"
prune "$BACKUP_DIR/monthly" "$((RETENTION_MONTHLY * 31))"    "mensuelle"

log "Sauvegarde terminée avec succès."
