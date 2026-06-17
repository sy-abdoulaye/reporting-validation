#!/bin/sh
# ---------------------------------------------------------------------------
# Restauration PostgreSQL à partir d'une sauvegarde (format custom).
# À exécuter DANS le conteneur "db-backup".
#
#   Usage : db_restore.sh <fichier.dump | chemin> [full|users]
#   - Le fichier peut être un chemin absolu, relatif à /backups, ou un simple
#     nom de fichier (recherché récursivement dans /backups).
#   - Portée (2e argument, défaut "full") :
#       full  → restauration COMPLÈTE (toutes les tables et données)
#       users → restaure UNIQUEMENT la table des utilisateurs (comptes/login)
#
# La restauration :
#   1. vérifie l'intégrité de l'archive ;
#   2. crée la base si elle n'existe pas ;
#   3. coupe les connexions actives ;
#   4. restaure (drop + recreate des objets via --clean --if-exists).
# ---------------------------------------------------------------------------
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
PGDATABASE="${PGDATABASE:-reporting}"
LOG_FILE="$BACKUP_DIR/backup.log"
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') [restore] $*" | tee -a "$LOG_FILE"; }
fail() { log "ERREUR: $*"; exit 1; }

arg="${1:-}"
scope="${2:-full}"
[ -n "$arg" ] || fail "usage : db_restore.sh <fichier.dump> [full|users]"
case "$scope" in full|users) ;; *) fail "portée invalide : '$scope' (attendu : full | users)";; esac

# Résolution du chemin
if [ -f "$arg" ]; then
  path="$arg"
elif [ -f "$BACKUP_DIR/$arg" ]; then
  path="$BACKUP_DIR/$arg"
else
  path="$(find "$BACKUP_DIR" -name "$arg" -type f 2>/dev/null | head -n1)"
fi
[ -n "${path:-}" ] && [ -f "$path" ] || fail "fichier de sauvegarde introuvable : $arg"

log "Restauration demandée depuis : $path"

# 1. Intégrité de l'archive
pg_restore --list "$path" >/dev/null 2>>"$LOG_FILE" || fail "archive invalide ou illisible : $path"

# 2. Créer la base si nécessaire
exists="$(psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE'")" || fail "connexion au serveur impossible"
if [ "$exists" != "1" ]; then
  log "La base '$PGDATABASE' n'existe pas → création"
  psql -d postgres -c "CREATE DATABASE \"$PGDATABASE\"" >/dev/null || fail "création de la base impossible"
fi

# 3. Couper les connexions actives sur la base cible
psql -d postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$PGDATABASE' AND pid<>pg_backend_pid();" \
  >/dev/null 2>&1 || true

# 4. Restauration selon la portée demandée
if [ "$scope" = "users" ]; then
  # Vérifier que l'archive contient bien la table users
  # (format pg_restore --list : "... TABLE[ DATA] public users <owner>")
  pg_restore --list "$path" | grep -qiE "[[:space:]]public[[:space:]]+users([[:space:]]|$)" \
    || fail "cette sauvegarde ne contient pas la table 'users'"
  log "Restauration des UTILISATEURS uniquement depuis $(basename "$path")…"
  # --clean --if-exists -t users : supprime puis recrée la table users (schéma + données),
  # qu'elle existe déjà ou non. Les autres tables ne sont pas touchées.
  if pg_restore --clean --if-exists --no-owner --no-privileges \
       -t users -d "$PGDATABASE" "$path" 2>>"$LOG_FILE"; then
    n="$(psql -d "$PGDATABASE" -tAc 'SELECT count(*) FROM users' 2>/dev/null || echo '?')"
    log "Utilisateurs restaurés : $n compte(s)."
  else
    log "Restauration des utilisateurs terminée AVEC avertissements (voir $LOG_FILE)."
  fi
else
  log "Restauration COMPLÈTE en cours… (cela peut prendre un moment)"
  if pg_restore --clean --if-exists --no-owner --no-privileges \
       -d "$PGDATABASE" "$path" 2>>"$LOG_FILE"; then
    log "Restauration complète terminée avec succès depuis $(basename "$path")."
  else
    # pg_restore peut signaler des avertissements non bloquants (objets absents).
    log "Restauration terminée AVEC avertissements (voir $LOG_FILE). Vérifiez les données."
  fi
fi
