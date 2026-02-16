#!/bin/bash
set -e

echo "=== Canadian Legal Data Platform v5.0 ==="
echo "Checking environment..."

if [ -z "$SUPABASE_URL" ] || [ -z "$SUPABASE_KEY" ]; then
    echo "ERROR: SUPABASE_URL and SUPABASE_KEY must be set"
    exit 1
fi

echo "Environment OK"
echo "Starting uvicorn on 0.0.0.0:8000 ..."

# workers=1: ScraperManager is an in-process singleton.
# Multiple workers would create independent instances that
# can't share scraper state. The scraper runs in a background
# thread and does not block the async event loop.
exec uvicorn api.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info \
    --access-log
