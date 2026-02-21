#!/usr/bin/env python3
"""
Multi-Source Canadian Legal Data Ingestion CLI

Usage:
    python main_multi.py --list-sources
    python main_multi.py --source-type justice_canada_xml --limit 10
    python main_multi.py --source-type bc_laws_api --limit 5
    python main_multi.py --source-type a2aj_case_law --limit 100
    python main_multi.py  # Run all enabled sources (full mode)

    # Incremental mode: only fetch docs not checked within --max-age hours
    python main_multi.py --incremental --max-age 24
    python main_multi.py --incremental --max-age 72 --source-type bc_laws_api
"""
import argparse
import sys
import threading

from utils.config import config
from utils.logger import logger
from utils.checkpoint import Checkpoint
from scraper.db_client import DatabaseClient
from scraper.adapters import get_adapter, list_adapters


def main():
    parser = argparse.ArgumentParser(description="Multi-Source Canadian Legal Data Ingestion")
    parser.add_argument('--source-type', type=str, default=None,
                        help='Run only this source type (e.g. justice_canada_xml, bc_laws_api, a2aj_case_law)')
    parser.add_argument('--limit', type=int, default=None,
                        help='Limit total documents to process')
    parser.add_argument('--list-sources', action='store_true',
                        help='List all available and configured sources')
    parser.add_argument('--reset', action='store_true',
                        help='Clear checkpoint before running')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only discover documents, do not fetch or save')
    parser.add_argument('--incremental', action='store_true',
                        help='Incremental mode: skip docs checked within --max-age hours')
    parser.add_argument('--max-age', type=int, default=24,
                        help='Max age in hours for incremental mode (default: 24)')
    parser.add_argument('--show-freshness', action='store_true',
                        help='Show per-source freshness summary and exit')
    args = parser.parse_args()

    # Init DB client
    db_client = DatabaseClient()

    # Show freshness summary
    if args.show_freshness:
        if not db_client.test_connection():
            logger.error("Database connection failed")
            sys.exit(1)
        freshness = db_client.get_source_freshness()
        print("\n=== Source Freshness Summary ===")
        for source_type, info in freshness.get('sources', {}).items():
            total = info.get('total_docs', 0)
            fresh_24h = info.get('checked_24h', 0)
            fresh_7d = info.get('checked_7d', 0)
            never = info.get('never_checked', 0)
            oldest = info.get('oldest_check', 'never')
            pct_24h = (fresh_24h / total * 100) if total > 0 else 0
            print(f"\n  {source_type}:")
            print(f"    Total: {total:,} docs")
            print(f"    Fresh (24h): {fresh_24h:,} ({pct_24h:.0f}%)")
            print(f"    Fresh (7d):  {fresh_7d:,}")
            print(f"    Never checked: {never:,}")
            print(f"    Oldest check: {oldest}")
            if 'last_sync' in info:
                sync = info['last_sync']
                print(f"    Last sync: {sync.get('mode', '?')} at {sync.get('started_at', '?')}")
        return

    # List sources
    if args.list_sources:
        print("\n=== Registered Adapters ===")
        for source_type, cls in list_adapters().items():
            print(f"  {source_type}: {cls.__name__}")

        print("\n=== Configured Sources ===")
        for src in config.sources:
            status = "ENABLED" if src.get('enabled', True) else "disabled"
            print(f"  [{status}] {src['source_type']}: {src.get('name', '?')} ({src.get('jurisdiction', '?')})")
        return

    # Reset checkpoint if requested
    checkpoint = Checkpoint()
    if args.reset:
        checkpoint.reset()
        logger.info("Checkpoint cleared")

    if not db_client.test_connection():
        logger.error("Database connection failed")
        sys.exit(1)

    # Determine which sources to run
    sources = config.sources
    if args.source_type:
        sources = [s for s in sources if s['source_type'] == args.source_type]
        if not sources:
            # Try running the adapter directly even if not in config
            logger.info(f"Source type '{args.source_type}' not in config, trying direct adapter...")
            sources = [{"source_type": args.source_type, "name": args.source_type,
                        "jurisdiction": "?", "enabled": True, "params": {}}]

    sources = [s for s in sources if s.get('enabled', True)]

    if not sources:
        logger.error("No enabled sources to run")
        sys.exit(1)

    mode_str = "incremental" if args.incremental else "full"
    logger.info(f"Mode: {mode_str}" + (f" (max_age={args.max_age}h)" if args.incremental else ""))

    # Run
    stop_event = threading.Event()
    stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0, 'skipped_fresh': 0}
    session_total = 0

    for source_cfg in sources:
        if stop_event.is_set():
            break
        if args.limit and session_total >= args.limit:
            break

        source_type = source_cfg['source_type']
        logger.info(f"\n{'='*60}")
        logger.info(f"SOURCE: {source_cfg.get('name', source_type)} [{source_type}] ({mode_str})")
        logger.info(f"{'='*60}")

        # Create per-source sync log
        sync_id = db_client.create_sync_log(
            source_type=source_type,
            mode=mode_str,
            trigger_source='cli',
            max_age_hours=args.max_age if args.incremental else None,
        )
        source_stats = {
            'discovered': 0, 'checked': 0, 'new': 0,
            'updated': 0, 'unchanged': 0, 'failed': 0,
            'skipped_fresh': 0,
        }

        try:
            adapter = get_adapter(source_type, **source_cfg.get('params', {}))
        except Exception as e:
            logger.error(f"Failed to create adapter: {e}")
            db_client.finalize_sync_log(sync_id, error_message=str(e))
            continue

        # Discover
        remaining = (args.limit - session_total) if args.limit else None
        try:
            doc_list = adapter.discover_documents(limit=remaining)
            source_stats['discovered'] = len(doc_list)
            logger.info(f"Discovered {len(doc_list)} documents")
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            db_client.finalize_sync_log(sync_id, error_message=str(e))
            continue

        stats['total'] += len(doc_list)

        if args.dry_run:
            for d in doc_list[:10]:
                logger.info(f"  [{d.jurisdiction_code}] {d.title[:70]} | {d.source_url[:80]}")
            if len(doc_list) > 10:
                logger.info(f"  ... and {len(doc_list) - 10} more")
            db_client.finalize_sync_log(sync_id, docs_discovered=len(doc_list),
                                         notes="dry-run")
            continue

        # ---- Filter: incremental (DB) vs full (checkpoint) ----
        doc_urls = [d.source_url for d in doc_list]

        if args.incremental:
            fresh_urls = db_client.get_fresh_urls(doc_urls, args.max_age)
            to_fetch = [d for d in doc_list if d.source_url not in fresh_urls]
            skipped_fresh = len(fresh_urls)
            source_stats['skipped_fresh'] = skipped_fresh
            stats['skipped_fresh'] += skipped_fresh
            stats['skipped'] += skipped_fresh
            if skipped_fresh:
                logger.info(f"Incremental: skipped {skipped_fresh} fresh docs (checked within {args.max_age}h)")
        else:
            already_scraped = checkpoint.filter_scraped_urls(doc_urls)
            to_fetch = [d for d in doc_list if d.source_url not in already_scraped]
            skipped = len(doc_list) - len(to_fetch)
            stats['skipped'] += skipped
            if skipped:
                logger.info(f"Skipped {skipped} already-processed documents")

        if not to_fetch:
            logger.info("All documents up-to-date for this source")
            db_client.finalize_sync_log(sync_id,
                docs_discovered=source_stats['discovered'],
                docs_skipped_fresh=source_stats['skipped_fresh'])
            continue

        # Ensure jurisdiction exists
        jur = adapter.get_jurisdiction()
        if jur and jur != 'multi':
            db_client.ensure_jurisdiction(jur)

        # Fetch and save
        effective_limit = remaining
        for doc_content in adapter.fetch_documents_batch(to_fetch, limit=effective_limit, stop_event=stop_event):
            if stop_event.is_set():
                break

            upsert_data = doc_content.to_upsert_dict(source_type=source_type)

            # Ensure jurisdiction for multi-jurisdiction sources
            if doc_content.jurisdiction_code:
                db_client.ensure_jurisdiction(doc_content.jurisdiction_code)

            try:
                success = db_client.upsert_document_v3(upsert_data)
                if success:
                    stats['success'] += 1
                    checkpoint.add(doc_content.source_url)
                    session_total += 1
                    source_stats['checked'] += 1
                else:
                    stats['failed'] += 1
                    source_stats['failed'] += 1
            except Exception as e:
                logger.error(f"Save failed: {e}")
                stats['failed'] += 1
                source_stats['failed'] += 1

            if (stats['success'] + stats['failed']) % 50 == 0:
                logger.info(f"Progress: success={stats['success']} failed={stats['failed']} skipped={stats['skipped']}")

        # Finalize per-source sync log
        db_client.finalize_sync_log(sync_id,
            docs_discovered=source_stats['discovered'],
            docs_checked=source_stats['checked'],
            docs_failed=source_stats['failed'],
            docs_skipped_fresh=source_stats['skipped_fresh'],
        )

    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info(f"INGESTION COMPLETE ({mode_str})")
    logger.info(f"{'='*60}")
    logger.info(f"Total discovered: {stats['total']}")
    logger.info(f"Success: {stats['success']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Skipped: {stats['skipped']}")
    if args.incremental:
        logger.info(f"  (fresh/skipped: {stats['skipped_fresh']})")
    if stats['total'] > 0:
        rate = stats['success'] / stats['total'] * 100
        logger.info(f"Success rate: {rate:.1f}%")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
