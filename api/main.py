import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from api.models import ConfigUpdateRequest, ScraperStatus, ScraperStartRequest, SourcesUpdateRequest, SchedulerConfigRequest
from api.manager import scraper_manager
from api.scheduler import scheduler_service
from utils.config import config

app = FastAPI(title="Canadian Legal Data Platform API")

# ---------- CORS ----------
allowed_origin = os.getenv("ALLOWED_ORIGIN", "*")
origins = ["*"] if allowed_origin == "*" else [o.strip() for o in allowed_origin.split(",")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Root health check (outside /api, for monitoring & Cloudflare) ----------

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Canadian Legal Data Platform", "version": "5.7"}


# ========================================================================
#  API Router — all business endpoints live under /api prefix
# ========================================================================

api_router = APIRouter(prefix="/api")


# ---- Config (legacy targets) ----

@api_router.get("/config")
def get_config():
    return {"targets": config.targets}

@api_router.post("/config")
def update_config(request: ConfigUpdateRequest):
    try:
        targets_data = [t.dict() for t in request.targets]
        config.save_targets(targets_data)
        return {"status": "success", "targets": config.targets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Sources (multi-source config) ----

@api_router.get("/sources")
def get_sources():
    """Get all configured data sources."""
    return {"sources": config.sources}

@api_router.post("/sources")
def update_sources(request: SourcesUpdateRequest):
    """Update data source configuration."""
    try:
        sources_data = [s.dict() for s in request.sources]
        config.save_sources(sources_data)
        return {"status": "success", "sources": config.sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/sources/available")
def list_available_adapters():
    """List all registered adapter types."""
    from scraper.adapters import list_adapters
    adapters = list_adapters()
    return {
        "adapters": [
            {"source_type": st, "class": cls.__name__}
            for st, cls in adapters.items()
        ]
    }

@api_router.get("/sources/stats")
def get_source_stats():
    """Get per-source document counts and DB statistics."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    try:
        return db.get_source_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Scraper Control ----

@api_router.get("/status", response_model=ScraperStatus)
def get_status():
    return scraper_manager.get_status()

@api_router.post("/scraper/start")
def start_scraper(req: ScraperStartRequest):
    success, msg = scraper_manager.start_scraping(
        engine=req.engine,
        headless=req.headless,
        cdp_url=req.cdp_url,
        scrape_limit=req.scrape_limit,
        source_type=req.source_type,
        source_types=req.source_types,
        distribution_mode=req.distribution_mode,
        source_estimates=req.source_estimates,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}

@api_router.post("/scraper/stop")
def stop_scraper():
    success, msg = scraper_manager.stop_scraping()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "stopping", "message": msg}


# ---- Scheduler ----

@api_router.get("/scheduler")
def get_scheduler():
    """Get scheduler configuration and status."""
    return scheduler_service.get_status()

@api_router.post("/scheduler")
def update_scheduler(req: SchedulerConfigRequest):
    """Update scheduler configuration."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    updates = {k: v for k, v in req.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    db.update_scheduler_config(updates)
    return {"status": "success", "config": db.get_scheduler_config()}

@api_router.post("/scheduler/trigger")
def trigger_scheduler():
    """Manually trigger a scheduled scrape run."""
    success, msg = scheduler_service.trigger_now()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "triggered", "message": msg}


# ---- Jobs (paginated history) ----

@api_router.get("/jobs")
def get_jobs(page: int = 1, per_page: int = 25, status: str = None):
    """Get paginated job history with optional status filter."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    if per_page > 100:
        per_page = 100
    return db.get_jobs_paginated(page=page, per_page=per_page, status_filter=status)


# ---- Documents (paginated browser) ----

@api_router.get("/documents")
def list_documents(page: int = 1, per_page: int = 50,
                   source_type: str = None, jurisdiction: str = None,
                   document_type: str = None, search: str = None):
    """Paginated document listing with filters."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    if per_page > 100:
        per_page = 100
    return db.get_documents_paginated(
        page=page, per_page=per_page,
        source_type=source_type, jurisdiction=jurisdiction,
        document_type=document_type, search=search
    )

@api_router.get("/documents/{doc_id}")
def get_document(doc_id: str):
    """Get document detail (metadata + version info)."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    doc = db.get_document_detail(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@api_router.get("/documents/{doc_id}/content")
def get_document_content(doc_id: str, max_length: int = 50000):
    """Get document text content (truncated for preview)."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    try:
        content = db.get_document_content(doc_id, max_length=min(max_length, 200000))
        if content is None:
            raise HTTPException(status_code=404, detail="Document or content not found")
        return content
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Database Diagnostics ----

@api_router.get("/debug/db")
def get_db_diagnostics():
    """Run comprehensive database diagnostics for debugging."""
    from scraper.db_client import DatabaseClient
    db = DatabaseClient()
    try:
        return db.get_db_diagnostics()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---- Discovery (legacy CanLII) ----

@api_router.get("/discovery/explore")
def explore_targets():
    """Trigger a discovery scan with streaming progress"""
    from api.discovery import discovery_engine

    def event_generator():
        for event in discovery_engine.discover_targets_generator():
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@api_router.get("/discovery/cache")
def get_discovery_cache():
    """Get cached discovery results"""
    from api.discovery import discovery_engine
    return {"results": discovery_engine.get_cached_results()}


# ========================================================================
#  Register API router, then mount static frontend (order matters!)
# ========================================================================

app.include_router(api_router)


# ---------- Startup: auto-start scheduler ----------

@app.on_event("startup")
def startup_scheduler():
    scheduler_service.start()

# Serve built React frontend in production (when web/dist/ exists)
_dist = Path(__file__).parent.parent / "web" / "dist"
if _dist.exists():
    # Vite puts hashed JS/CSS bundles in /assets/
    app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    # SPA catch-all: any route not matched by /api/* or /assets/* returns index.html
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = _dist / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_dist / "index.html"))
