#!/bin/bash
# =============================================================================
# Auto Cost Engine — Automated Database Backup
# =============================================================================
# Dumps the PostgreSQL database, compresses it, and uploads to MinIO.
#
# Usage:
#   export DATABASE_URL="postgresql://user:pass@host:5432/db"
#   export MINIO_ROOT_USER="..."
#   export MINIO_ROOT_PASSWORD="..."
#   export MINIO_ENDPOINT="minio:9000"
#   ./scripts/backup-db.sh
#
# Can be scheduled via cron:
#   0 2 * * * /path/to/auto-cost-engine/scripts/backup-db.sh >> /var/log/ace-backup.log 2>&1
# =============================================================================

set -euo pipefail

# ---- Configuration (override via environment) ----
DATABASE_URL="${DATABASE_URL:?DATABASE_URL is required}"
MINIO_ROOT_USER="${MINIO_ROOT_USER:?MINIO_ROOT_USER is required}"
MINIO_ROOT_PASSWORD="${MINIO_ROOT_PASSWORD:?MINIO_ROOT_PASSWORD is required}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-minio:9000}"
MINIO_ALIAS="${MINIO_ALIAS:-ace-minio}"
MINIO_BACKUP_BUCKET="${MINIO_BACKUP_BUCKET:-ace-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
RETENTION_WEEKS="${RETENTION_WEEKS:-4}"
RETENTION_MONTHS="${RETION_MONTHS:-3}"

# Timestamps
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
DATE_ONLY=$(date +%Y%m%d)
DAY_OF_WEEK=$(date +%u)      # 1=Monday … 7=Sunday
DAY_OF_MONTH=$(date +%d)

BACKUP_DIR="/tmp/ace-backups"
BACKUP_FILE="${BACKUP_DIR}/ace-backup-${TIMESTAMP}.sql.gz"
LOG_FILE="${BACKUP_DIR}/backup.log"

# ---- Setup ----
mkdir -p "${BACKUP_DIR}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting backup …" | tee -a "${LOG_FILE}"

# ---- Dump database ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dumping database …" | tee -a "${LOG_FILE}"
pg_dump "${DATABASE_URL}" | gzip > "${BACKUP_FILE}"
DUMP_SIZE=$(du -h "${BACKUP_FILE}" | cut -f1)
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Dump complete: ${BACKUP_FILE} (${DUMP_SIZE})" | tee -a "${LOG_FILE}"

# ---- Upload to MinIO ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Uploading to MinIO …" | tee -a "${LOG_FILE}"

# Configure MinIO client
mc alias set "${MINIO_ALIAS}" "http://${MINIO_ENDPOINT}" "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" 2>&1 | tee -a "${LOG_FILE}"

# Ensure bucket exists
mc mb "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}" 2>/dev/null || true

# Upload to daily path
mc cp "${BACKUP_FILE}" "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/daily/" 2>&1 | tee -a "${LOG_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Daily upload complete" | tee -a "${LOG_FILE}"

# If Sunday, also copy to weekly
if [ "${DAY_OF_WEEK}" = "7" ]; then
    mc cp "${BACKUP_FILE}" "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/weekly/" 2>&1 | tee -a "${LOG_FILE}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Weekly copy complete" | tee -a "${LOG_FILE}"
fi

# If 1st of month, also copy to monthly
if [ "${DAY_OF_MONTH}" = "01" ]; then
    mc cp "${BACKUP_FILE}" "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/monthly/" 2>&1 | tee -a "${LOG_FILE}"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Monthly copy complete" | tee -a "${LOG_FILE}"
fi

# ---- Cleanup old backups (retention) ----
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Applying retention policy …" | tee -a "${LOG_FILE}"

# Remove daily backups older than RETENTION_DAYS
mc rm "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/daily/" --old --days "${RETENTION_DAYS}" --recursive 2>/dev/null || true

# Remove weekly backups older than RETENTION_WEEKS weeks (days * 7)
mc rm "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/weekly/" --old --days $((RETENTION_WEEKS * 7)) --recursive 2>/dev/null || true

# Remove monthly backups older than RETENTION_MONTHS months (days * 30)
mc rm "${MINIO_ALIAS}/${MINIO_BACKUP_BUCKET}/monthly/" --old --days $((RETENTION_MONTHS * 30)) --recursive 2>/dev/null || true

# ---- Cleanup local temp file ----
rm -f "${BACKUP_FILE}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Local temp file removed" | tee -a "${LOG_FILE}"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Backup complete: ${TIMESTAMP}" | tee -a "${LOG_FILE}"
echo "" >> "${LOG_FILE}"
