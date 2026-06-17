# Sauvegarde, restauration et reprise après incident

Stratégie de protection des données de la base PostgreSQL de l'application Reporting.

## Vue d'ensemble

| Élément | Détail |
|---|---|
| Base de données | PostgreSQL 16 (service `db`, conteneur `reporting-db`) |
| Données vivantes | Volume Docker nommé **`pgdata`** (persiste hors du conteneur) |
| Sauvegardes | Format custom `pg_dump -Fc` compressé, dans **`./backups/`** (hôte) |
| Automatisation | Service **`db-backup`** (conteneur `reporting-db-backup`) |
| Rétention | GFS : quotidien / hebdomadaire / mensuel (configurable) |

> ⚠️ **DANGER — `docker compose down -v`** détruit le volume `pgdata` et donc
> **toutes les données vivantes**. N'utilisez jamais le drapeau `-v` en
> production. En cas de sinistre, restaurez depuis `./backups/` (qui survit, car
> c'est un bind-mount hôte). Une base **vide** n'est jamais sauvegardée
> automatiquement (garde-fou intégré), pour éviter d'écraser une bonne sauvegarde
> par une sauvegarde « piège ».

Deux niveaux de protection complémentaires :

1. **Persistance** — les données vivent dans le volume `pgdata`, indépendant du
   cycle de vie du conteneur `db`. Supprimer/recréer le conteneur ne perd pas les
   données (`docker compose up/down` conserve les volumes ; seul `down -v` les détruit).
2. **Sauvegardes** — des dumps réguliers stockés sur l'hôte dans `./backups/`,
   donc récupérables même si le volume `pgdata` est corrompu ou détruit.

## Sauvegardes automatiques

Le service `db-backup` exécute une sauvegarde **au démarrage** puis **toutes les
24 h** (configurable). Chaque sauvegarde :

1. génère un dump `pg_dump -Fc -Z6` dans `./backups/daily/` ;
2. vérifie l'intégrité de l'archive (`pg_restore --list`) ;
3. crée une copie hebdomadaire (dimanche) et mensuelle (1er du mois) ;
4. applique la rétention (suppression des anciennes sauvegardes).

Arborescence produite :

```
backups/
├── backup.log          # journal horodaté de toutes les opérations
├── daily/   reporting_YYYYMMDD_HHMMSS.dump
├── weekly/  reporting_YYYYMMDD_HHMMSS.dump
└── monthly/ reporting_YYYYMMDD_HHMMSS.dump
```

### Configuration (dans `docker-compose.yml`, service `db-backup`)

| Variable | Défaut | Rôle |
|---|---|---|
| `BACKUP_INTERVAL_HOURS` | `24` | Intervalle entre deux sauvegardes |
| `RUN_ON_START` | `true` | Sauvegarde immédiate au démarrage |
| `RETENTION_DAILY` | `7` | Jours de conservation des dumps quotidiens |
| `RETENTION_WEEKLY` | `4` | Semaines de conservation des copies hebdo |
| `RETENTION_MONTHLY` | `6` | Mois de conservation des copies mensuelles |
| `WEEKLY_DOW` | `7` | Jour de la copie hebdo (1=lundi … 7=dimanche) |
| `MONTHLY_DOM` | `01` | Jour du mois de la copie mensuelle |

Après modification : `docker compose up -d db-backup`.

## Commandes d'administration

Toutes via le wrapper hôte `./scripts/db-admin.sh` :

```bash
# Déclencher une sauvegarde manuelle immédiate
./scripts/db-admin.sh backup

# Lister les sauvegardes disponibles (daily / weekly / monthly)
./scripts/db-admin.sh list

# Restaurer une sauvegarde précise — COMPLÈTE (toutes les tables)
./scripts/db-admin.sh restore reporting_20260616_081500.dump

# Restaurer UNIQUEMENT les comptes utilisateurs (login) — les autres tables
# (historique, rapports, audit…) ne sont PAS touchées
./scripts/db-admin.sh restore-users reporting_20260616_081500.dump

# Consulter le journal des sauvegardes
./scripts/db-admin.sh logs
```

### Restauration complète vs. utilisateurs seuls

| Commande | Effet |
|---|---|
| `restore <fichier>` | Restaure **toutes les tables** (remet la base dans l'état du dump) |
| `restore-users <fichier>` | Restaure **seulement la table `users`** ; les autres tables restent inchangées |

Cas d'usage typique après `docker compose down -v` (volumes supprimés) :

```bash
docker compose up -d                                   # base recréée (vide)
./scripts/db-admin.sh restore-users <fichier.dump>     # récupérer les comptes (obligatoire)
# puis, si souhaité seulement :
./scripts/db-admin.sh restore <fichier.dump>           # récupérer toutes les données
```

> Note : `down -v` supprime aussi les volumes `uploads`/`reports` (fichiers Excel
> et rapports générés sur disque). La restauration ramène les **enregistrements**
> en base, mais pas ces fichiers physiques — sauvegardez-les séparément si besoin.

> La restauration demande une confirmation, arrête le backend le temps de
> l'opération, puis le redémarre automatiquement.

## Procédure de restauration

### Cas 1 — Restaurer un état antérieur (les données existent encore)

```bash
./scripts/db-admin.sh list                       # repérer la sauvegarde voulue
./scripts/db-admin.sh restore <fichier.dump>     # confirmer par « y »
```

La restauration supprime puis recrée les objets (`--clean --if-exists`) et
recharge les données du dump. Le backend est arrêté/redémarré automatiquement.

### Cas 2 — Reprise après suppression du conteneur de base

Les données survivent à la suppression du **conteneur** car elles sont dans le
volume `pgdata` :

```bash
docker compose rm -sf db      # suppression du conteneur (volume conservé)
docker compose up -d db       # recréation : les données sont toujours là
```

### Cas 3 — Reprise après perte/corruption du volume (sinistre complet)

```bash
# 1. (Re)créer une base vide
docker compose up -d db

# 2. Restaurer la dernière sauvegarde saine
./scripts/db-admin.sh list
./scripts/db-admin.sh restore <fichier.dump>

# 3. Vérifier l'application
docker compose up -d
```

Le script de restauration **crée la base si elle n'existe pas**, ce qui couvre le
cas d'un volume entièrement neuf.

### Restauration manuelle (sans le wrapper)

```bash
docker compose exec -T db-backup sh /scripts/db_restore.sh <fichier.dump>
```

## Gestion des erreurs & vérifications

- Chaque dump est **vérifié** (`pg_restore --list`) ; une archive corrompue est
  supprimée et l'opération échoue explicitement.
- Écriture **atomique** (`.part` puis renommage) : pas de dump partiel exploité.
- Toutes les opérations sont **journalisées** dans `./backups/backup.log`.
- La restauration coupe les connexions actives et tolère les avertissements non
  bloquants (objets absents lors d'un `--clean` sur base neuve).

## Bonnes pratiques de production

- **Copie hors-site** : répliquer périodiquement `./backups/` vers un stockage
  distant (rsync, S3, NFS…) pour se prémunir d'une perte de l'hôte.
- **Tests réguliers** : restaurer une sauvegarde sur un environnement de test
  pour valider les dumps.
- Ne jamais utiliser `docker compose down -v` en production : cela **détruit** le
  volume `pgdata`.
