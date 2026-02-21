#!/bin/bash
# Database backup script for Canadian Legal Data Platform
# Creates compressed PostgreSQL dumps with rotation (keep last 7 days)
#
# Usage:
#   ./scripts/backup_db.sh                    # Backup to default /backups dir
#   ./scripts/backup_db.sh /custom/path       # Backup to custom dir
#   BACKUP_RETAIN_DAYS=14 ./scripts/backup_db.sh  # Keep 14 days instead of 7
#
# Add to crontab (daily at 3:00 AM):
#   0 3 * * * /home/yiyun/canlii/scripts/backup_db.sh >> /home/yiyun/canlii/backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${1:-/home/yiyun/backups/canlii}"
RETAIN_DAYS="${BACKUP_RETAIN_DAYS:-7}"
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

# Rotate old backups
DELETED=$(find "${BACKUP_DIR}" -name "canlii_*.dump" -mtime +${RETAIN_DAYS} -print -delete | wc -l)
if [ "${DELETED}" -gt 0 ]; then
    echo "[$(date)] Rotated ${DELETED} backup(s) older than ${RETAIN_DAYS} days"
fi

# Show backup summary
TOTAL_BACKUPS=$(find "${BACKUP_DIR}" -name "canlii_*.dump" | wc -l)
TOTAL_SIZE=$(du -sh "${BACKUP_DIR}" | cut -f1)
echo "[$(date)] Backup complete. ${TOTAL_BACKUPS} backup(s), total ${TOTAL_SIZE}"
