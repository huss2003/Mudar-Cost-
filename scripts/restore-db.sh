#!/bin/bash
# =============================================================================
# Auto Cost Engine — Database Restore from MinIO Backup
# =============================================================================
# Downloads a backup file from MinIO and restores it to the PostgreSQL
# database.
#
# Usage:
#   export DATABASE_URL="postgresql://user:pass@host:5432/db"
#   export MINIO_ROOT_USER="..."
#   export MINIO_ROOT_PASSWORD="..."
#   export MINIO_ENDPOINT="minio:9000"
#
#   ./scripts/restore-db.sh ace-backup-20260101-020000.sql.gz
#   ./scripts/restore-db.sh daily/ace-backup-20260101-020000.sql.gz
#   ./scripts/restore-db.sh weekly/ace-backup-20260101-020000.sql.gz
#
# ⚠️  WARNING: This will DESTROY all existing data in the database!
# =============================================================================

set -euo pipefail

# ---- Check for backup file argument ----
if [ $# -lt 1 ]; then
    echo "❌ Usage: $0 <backup-filename>"
    echo ""
    echo "Examples:"
    echo "  $0 ace-backup-20260101-020000.sql.gz"
    echo "  $0 daily/ace-backup-20260101-020000.sql.gz"
    echo ""
    echo "Available backups:"
    echo "  Use MinIO console or 'mc ls ${MINIO_ALIAS:-ace-minio}/ace-backups/daily/'"
    exit 1
fi

BACKUP_PATH="$1"
BACKUP_FILENAME=$(basename "${BACKUP_PATH}")

echo ""
echo "⚠️  ⚠️  ⚠️   DATABASE RESTORE   ⚠️  ⚠️  ⚠️"
echo ""
echo "This will COMPLETELY OVERWRITE the database at:"
echo "  ${DATABASE_URL}"
echo ""
echo "Using backup file: ${BACKUP_PATH}"
echo ""
read -rp "Are you SURE you want to continue? (type 'yes' to confirm): " CONFIRM

if [ "${CONFIRM}" != "yes" ]; then
    echo "❌ Restore cancelled."
    exit 1
fi

# ---- Configuration (override via environment) ----
DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
MINIO_ALIAS="${MINIO_ALIAS:-ace-minio}"
MINIO_BACKUP_BUCKET="${MINIO_BACKUP_BUCKET:-ace-backups}"

RESTORE_DIR="/tmp/ace-restore"
RESTORE_FILE="${RESTORE_DIR}/${BACKUP_FILENAME}"

# ---- Setup ----
mkdir -p "${RESTORE_DIR}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting restore from: ${BACKUP_PATH}"

# ---- Configure MinIO client ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Configuring MinIO client …"
mc alias set "${MINIO_ALIAS}" "http://${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"

# ---- Download backup from MinIO ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Downloading backup from MinIO …"
mc cp "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/${BACKUP_PATH}" "${RESTORE_FILE}"

DOWNLOAD_SIZE=$(du -h "${RESTORE_FILE}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Download complete: ${RESTORE_FILE} (${DOWNLOAD_SIZE})"

# ---- Decompress and restore ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Restoring database …"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Target: ${DATABASE_URL}"

gunzip -c "${RESTORE_FILE}" | psql "${DATABASE_URL}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Restore complete from: ${BACKUP_PATH}"

# ---- Cleanup ----
rm -f "${RESTORE_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Temp files cleaned up"

# ---- Verification ----
echo ""
echo "🔍 Verifying restore …"
if echo "SELECT 1;" | psql "${DATABASE_URL}" -t -q 2>/dev/null | grep -q 1; then
    echo "✅ Database is responsive."
    echo ""
    echo "Quick checks:"
    echo "  docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c '\\dt'"
    echo "  docker compose -f infra/docker-compose.prod.yml exec postgres psql -U estimation -d estimation -c 'SELECT count(*) FROM <table>;'"
else
    echo "⚠️  Database connection failed after restore. Check connection string."
fi

echo ""
echo "📋 Restore summary:"
echo "  Backup:  ${BACKUP_PATH}"
echo "  Time:    $(date)"
echo "  Status:  Complete"
