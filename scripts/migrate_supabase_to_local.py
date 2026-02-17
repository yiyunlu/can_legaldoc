#!/usr/bin/env python3
"""
Migrate data from Supabase to local PostgreSQL.

Requires both SUPABASE_URL/SUPABASE_KEY and DATABASE_URL to be set in .env.

Usage:
    # From project root (with .env configured):
    python scripts/migrate_supabase_to_local.py

    # Or from inside Docker:
    docker exec canlii-platform python scripts/migrate_supabase_to_local.py

Tables migrated (in order):
    1. jurisdictions
    2. scrape_targets
    3. documents
    4. document_versions
    5. scrape_jobs
"""
import os
import sys
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import psycopg2
import psycopg2.extras
from supabase import create_client


def get_supabase_client():
    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set for migration")
        sys.exit(1)
    return create_client(url, key)


def get_pg_conn():
    db_url = os.getenv('DATABASE_URL')
    if not db_url:
        print("ERROR: DATABASE_URL must be set for migration")
        sys.exit(1)
    return psycopg2.connect(db_url)


def fetch_all_rows(supabase, table_name, batch_size=1000):
    """Fetch all rows from a Supabase table with pagination."""
    all_rows = []
    offset = 0
    while True:
        res = supabase.table(table_name).select('*').range(offset, offset + batch_size - 1).execute()
        if not res.data:
            break
        all_rows.extend(res.data)
        print(f"  ... fetched {len(all_rows)} rows so far", end='\r')
        offset += batch_size
        if len(res.data) < batch_size:
            break
    print(f"  Fetched {len(all_rows)} rows from Supabase        ")
    return all_rows


def migrate_table(supabase, pg_conn, table_name, conflict_col='id'):
    """Migrate a single table from Supabase to local PostgreSQL."""
    print(f"\n{'='*50}")
    print(f"Migrating: {table_name}")
    print(f"{'='*50}")

    all_rows = fetch_all_rows(supabase, table_name)

    if not all_rows:
        print(f"  No data to migrate for {table_name}")
        return 0

    # Get column names from first row
    columns = list(all_rows[0].keys())
    cols_str = ', '.join(columns)
    placeholders = ', '.join([f'%({c})s' for c in columns])

    query = f"""
        INSERT INTO {table_name} ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_col}) DO NOTHING
    """

    cur = pg_conn.cursor()
    inserted = 0
    errors = 0
    commit_batch = 100

    for i, row in enumerate(all_rows):
        # Convert dict/list values to JSON strings for JSONB columns
        processed = {}
        for k, v in row.items():
            if isinstance(v, (dict, list)):
                processed[k] = json.dumps(v)
            else:
                processed[k] = v

        try:
            cur.execute(query, processed)
            inserted += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error inserting row {i}: {e}")
            pg_conn.rollback()
            continue

        # Commit in batches
        if inserted % commit_batch == 0:
            pg_conn.commit()
            print(f"  Progress: {inserted}/{len(all_rows)} inserted, {errors} errors", end='\r')

    pg_conn.commit()
    print(f"  Done: {inserted} inserted, {errors} errors, {len(all_rows)} total       ")
    return inserted


def main():
    print("=" * 60)
    print("Supabase → Local PostgreSQL Migration")
    print("=" * 60)

    start = time.time()

    # Connect to both databases
    print("\nConnecting to Supabase...")
    supabase = get_supabase_client()

    print("Connecting to local PostgreSQL...")
    pg_conn = get_pg_conn()

    # Test local connection
    cur = pg_conn.cursor()
    cur.execute("SELECT 1")
    print("Local PostgreSQL connection OK")

    # Migrate tables in order (respecting foreign keys)
    tables = [
        ('jurisdictions', 'code'),
        ('scrape_targets', 'url'),
        ('documents', 'source_url'),
        ('document_versions', 'id'),
        ('scrape_jobs', 'id'),
    ]

    total_migrated = 0
    for table_name, conflict_col in tables:
        try:
            count = migrate_table(supabase, pg_conn, table_name, conflict_col)
            total_migrated += count
        except Exception as e:
            print(f"  FAILED: {e}")
            pg_conn.rollback()

    # Summary
    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print("MIGRATION COMPLETE")
    print(f"{'='*60}")
    print(f"Total rows migrated: {total_migrated}")
    print(f"Time elapsed: {elapsed:.1f}s")
    print(f"{'='*60}")

    pg_conn.close()


if __name__ == "__main__":
    main()
