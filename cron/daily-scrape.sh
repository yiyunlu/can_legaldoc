#!/bin/bash
# Daily multi-source ingestion script
# Runs inside the Docker container via: docker exec
#
# Install: copy systemd units or add to crontab:
#   echo "0 2 * * * /opt/canlii/cron/daily-scrape.sh" | crontab -

CONTAINER_NAME="canlii-platform"
LOG_FILE="/var/log/canlii-scrape.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') - Starting daily scrape..." >> "$LOG_FILE"

docker exec "$CONTAINER_NAME" python main_multi.py --limit 500 \
    >> "$LOG_FILE" 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Daily scrape completed successfully." >> "$LOG_FILE"
else
    echo "$(date '+%Y-%m-%d %H:%M:%S') - Daily scrape failed (exit code $EXIT_CODE)." >> "$LOG_FILE"
fi
