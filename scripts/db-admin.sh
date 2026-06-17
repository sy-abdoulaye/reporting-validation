#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Outil d'administration des sauvegardes (à lancer depuis l'HÔTE).
#
#   ./scripts/db-admin.sh backup                  → sauvegarde immédiate
#   ./scripts/db-admin.sh list                    → liste les sauvegardes
#   ./scripts/db-admin.sh restore <fichier>       → restauration COMPLÈTE
#   ./scripts/db-admin.sh restore-users <fichier> → restaure SEULEMENT les users
#   ./scripts/db-admin.sh logs                    → affiche les derniers logs
#
# S'appuie sur le service Docker Compose "db-backup".
# ---------------------------------------------------------------------------
set -euo pipefail

# Se placer à la racine du projet (où se trouve docker-compose.yml)
cd "$(dirname "$0")/.."

SVC="db-backup"

# Détecter la commande compose disponible
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ Docker Compose introuvable." >&2; exit 1
fi

ensure_running() {
  if ! $DC ps --status running 2>/dev/null | grep -q "$SVC"; then
    echo "ℹ️  Le service $SVC n'est pas démarré, lancement…"
    $DC up -d "$SVC"
    sleep 2
  fi
}

cmd="${1:-}"
case "$cmd" in
  backup)
    ensure_running
    echo "▶️  Sauvegarde en cours…"
    $DC exec -T "$SVC" sh /scripts/db_backup.sh
    echo "✅ Sauvegarde terminée. (./scripts/db-admin.sh list pour voir les fichiers)"
    ;;

  list)
    ensure_running
    echo "=== Sauvegardes disponibles (./backups) ==="
    $DC exec -T "$SVC" sh -c '
      for d in daily weekly monthly; do
        echo "--- $d ---"
        ls -lh "/backups/$d" 2>/dev/null | grep -E "\.dump$" || echo "  (aucune)"
      done'
    ;;

  restore|restore-users)
    file="${2:-}"
    if [ -z "$file" ]; then
      echo "Usage: $0 $cmd <fichier.dump>"; exit 2
    fi
    if [ "$cmd" = "restore-users" ]; then
      scope="users"
      warn="Seuls les COMPTES UTILISATEURS seront remplacés par ceux de « $file » (les autres tables ne sont pas touchées)."
    else
      scope="full"
      warn="La base ENTIÈRE va être ÉCRASÉE par « $file » (toutes les tables et données)."
    fi
    ensure_running
    echo "⚠️  ATTENTION : $warn"
    read -r -p "Confirmer ? [y/N] " ans
    if [ "${ans:-N}" != "y" ] && [ "${ans:-N}" != "Y" ]; then
      echo "Annulé."; exit 1
    fi
    echo "⏸️  Arrêt du backend pour une restauration propre…"
    $DC stop backend >/dev/null 2>&1 || true
    set +e
    $DC exec -T "$SVC" sh /scripts/db_restore.sh "$file" "$scope"
    rc=$?
    set -e
    echo "▶️  Redémarrage du backend…"
    $DC start backend >/dev/null 2>&1 || true
    if [ $rc -eq 0 ]; then
      echo "✅ Restauration terminée."
    else
      echo "❌ La restauration a rencontré une erreur (code $rc). Consultez : $0 logs"
      exit $rc
    fi
    ;;

  logs)
    ensure_running
    $DC exec -T "$SVC" sh -c 'tail -n 60 /backups/backup.log 2>/dev/null || echo "(aucun log)"'
    ;;

  *)
    echo "Usage: $0 {backup | list | restore <fichier> | restore-users <fichier> | logs}"
    echo "  backup         : sauvegarde immédiate"
    echo "  list           : liste les sauvegardes"
    echo "  restore        : restauration COMPLÈTE (toutes les tables)"
    echo "  restore-users  : restaure UNIQUEMENT les comptes utilisateurs"
    echo "  logs           : derniers logs de sauvegarde"
    exit 2
    ;;
esac
