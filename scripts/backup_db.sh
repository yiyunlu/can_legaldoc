#!/bin/bash
# Database backup script for Canadian Legal Data Platform
# Creates compressed PostgreSQL dumps with count-based rotation (keep last N dumps)
#
# Usage:
#   ./scripts/backup_db.sh                    # Backup to default /backups dir
#   ./scripts/backup_db.sh /custom/path       # Backup to custom dir
#   BACKUP_KEEP_COUNT=5 ./scripts/backup_db.sh  # Keep 5 dumps instead of 2
#
# Add to crontab (daily at 3:00 AM):
#   0 3 * * * /home/yiyun/canlii/scripts/backup_db.sh >> /home/yiyun/canlii/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${1:-/home/yiyun/backups/canlii}"
KEEP_COUNT="${BACKUP_KEEP_COUNT:-2}"
CONTAINER="canlii-postgres"
DB_USER="canlii"
DB_NAME="canlii"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/canlii_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting database backup..."

# Ensure backup directory exists
mkdir -p "${BACKUP_DIR}"

# Create compressed backup using pg_dump inside the container
docker exec "${CONTAINER}" pg_dump -U "${DB_USER}" -d "${DB_NAME}" \
    --format=custom --compress=6 \
    --no-owner --no-privileges \
    > "${BACKUP_DIR}/canlii_${TIMESTAMP}.dump"

BACKUP_SIZE=$(du -h "${BACKUP_DIR}/canlii_${TIMESTAMP}.dump" | cut -f1)
echo "[$(date)] Backup created: canlii_${TIMESTAMP}.dump (${BACKUP_SIZE})"

# Rotate old backups: keep only the N most recent
EXCESS=$(ls -t "${BACKUP_DIR}"/canlii_*.dump 2>/dev/null | tail -n +$((KEEP_COUNT + 1)))
if [ -n "${EXCESS}" ]; then
    DELETED=$(echo "${EXCESS}" | tee /dev/stderr | xargs rm -- | wc -l)
    echo "[$(date)] Rotated $(echo "${EXCESS}" | wc -l) backup(s), keeping ${KEEP_COUNT} most recent"
fi

# Show backup summary
TOTAL_BACKUPS=$(find "${BACKUP_DIR}" -name "canlii_*.dump" | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "[$(date)] Backup complete. ${TOTAL_BACKUPS} backup(s) kept (max ${KEEP_COUNT}), total ${TOTAL_SIZE}"
