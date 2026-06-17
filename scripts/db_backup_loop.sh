#!/bin/sh
# ---------------------------------------------------------------------------
# Planificateur de sauvegardes : exécute db_backup.sh à intervalle régulier.
# Entrypoint du service "db-backup". Tourne en avant-plan (PID 1).
#
#   BACKUP_INTERVAL_HOURS=24   → intervalle entre deux sauvegardes
#   RUN_ON_START=true          → lance une sauvegarde dès le démarrage
# ---------------------------------------------------------------------------
set -u

SCRIPT_DIR="$(dirname "$0")"
INTERVAL_HOURS="${BACKUP_INTERVAL_HOURS:-24}"
RUN_ON_START="${RUN_ON_START:-true}"

echo "$(date '+%F %T') [loop] Service de sauvegarde démarré (intervalle=${INTERVAL_HOURS}h, run_on_start=${RUN_ON_START})"

# Attendre que la base soit prête
until pg_isready >/dev/null 2>&1; do
  echo "$(date '+%F %T') [loop] En attente de la base de données…"
  sleep 3
done
echo "$(date '+%F %T') [loop] Base de données accessible."

if [ "$RUN_ON_START" = "true" ]; then
  sh "$SCRIPT_DIR/db_backup.sh" || echo "$(date '+%F %T') [loop] Sauvegarde initiale en échec (voir backup.log)"
fi

while true; do
  sleep "$((INTERVAL_HOURS * 3600))"
  sh "$SCRIPT_DIR/db_backup.sh" || echo "$(date '+%F %T') [loop] Sauvegarde planifiée en échec (voir backup.log)"
done
