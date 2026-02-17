import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from api.models import ConfigUpdateRequest, ScraperStatus, ScraperStartRequest, SourcesUpdateRequest
from api.manager import scraper_manager
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
    return {"status": "ok", "service": "Canadian Legal Data Platform", "version": "5.1"}


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
    from scraper.supabase_client import SupabaseClient
    db = SupabaseClient()
    try:
        # Total count
        total_res = db.client.table('documents').select('id', count='exact').execute()
        total_docs = total_res.count or 0

        # Per source_type counts
        source_counts = {}
        for st in ['justice_canada_xml', 'bc_laws_api', 'alberta_kings_printer', 'a2aj_case_law', 'canlii_legacy']:
            res = db.client.table('documents').select('id', count='exact').eq('source_type', st).execute()
            if res.count:
                source_counts[st] = res.count

        # Per jurisdiction counts
        jur_counts = {}
        jur_res = db.client.table('jurisdictions').select('code,name').execute()
        if jur_res.data:
            for jur in jur_res.data:
                res = db.client.table('documents').select('id', count='exact').eq('jurisdiction_code', jur['code']).execute()
                if res.count:
                    jur_counts[jur['code']] = {"name": jur['name'], "count": res.count}

        # Recent scrape jobs
        jobs_res = db.client.table('scrape_jobs').select('*').order('id', desc=True).limit(10).execute()
        recent_jobs = jobs_res.data or []

        # Per document_type counts
        type_counts = {}
        for dt in ['legislation', 'regulation', 'case_law']:
            res = db.client.table('documents').select('id', count='exact').eq('document_type', dt).execute()
            if res.count:
                type_counts[dt] = res.count

        return {
            "total_documents": total_docs,
            "by_source": source_counts,
            "by_jurisdiction": jur_counts,
            "by_type": type_counts,
            "recent_jobs": recent_jobs,
        }
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
