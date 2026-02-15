from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
from api.models import ConfigUpdateRequest, ScraperStatus, ScraperStartRequest, SourcesUpdateRequest
from api.manager import scraper_manager
from utils.config import config

app = FastAPI(title="Canadian Legal Data Platform API")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "Canadian Legal Data Platform API", "version": "4.0"}

# ========== Config (legacy targets) ==========

@app.get("/config")
def get_config():
    return {"targets": config.targets}

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    try:
        targets_data = [t.dict() for t in request.targets]
        config.save_targets(targets_data)
        return {"status": "success", "targets": config.targets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ========== Sources (multi-source config) ==========

@app.get("/sources")
def get_sources():
    """Get all configured data sources."""
    return {"sources": config.sources}

@app.post("/sources")
def update_sources(request: SourcesUpdateRequest):
    """Update data source configuration."""
    try:
        sources_data = [s.dict() for s in request.sources]
        config.save_sources(sources_data)
        return {"status": "success", "sources": config.sources}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sources/available")
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

# ========== Scraper Control ==========

@app.get("/status", response_model=ScraperStatus)
def get_status():
    return scraper_manager.get_status()

@app.post("/scraper/start")
def start_scraper(req: ScraperStartRequest):
    success, msg = scraper_manager.start_scraping(
        engine=req.engine,
        headless=req.headless,
        cdp_url=req.cdp_url,
        scrape_limit=req.scrape_limit,
        source_type=req.source_type,
        source_types=req.source_types,
    )
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": msg}

@app.post("/scraper/stop")
def stop_scraper():
    success, msg = scraper_manager.stop_scraping()
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "stopping", "message": msg}

# ========== Discovery (legacy CanLII) ==========

@app.get("/discovery/explore")
def explore_targets():
    """Trigger a discovery scan with streaming progress"""
    from api.discovery import discovery_engine

    def event_generator():
        for event in discovery_engine.discover_targets_generator():
            yield json.dumps(event) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.get("/discovery/cache")
def get_discovery_cache():
    """Get cached discovery results"""
    from api.discovery import discovery_engine
    return {"results": discovery_engine.get_cached_results()}
