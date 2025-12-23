from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import json
from api.models import ConfigUpdateRequest, ScraperStatus
from api.manager import scraper_manager
from utils.config import config

app = FastAPI(title="CanLII Scraper API")

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, set to specific frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"status": "ok", "service": "CanLII Scraper API"}

@app.get("/config")
def get_config():
    return {"targets": config.targets}

@app.post("/config")
def update_config(request: ConfigUpdateRequest):
    try:
        # Convert Pydantic models to dicts
        targets_data = [t.dict() for t in request.targets]
        config.save_targets(targets_data)
        return {"status": "success", "targets": config.targets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/status", response_model=ScraperStatus)
def get_status():
    return scraper_manager.get_status()

from api.models import ConfigUpdateRequest, ScraperStatus, ScraperStartRequest

@app.post("/scraper/start")
def start_scraper(req: ScraperStartRequest):
    success, msg = scraper_manager.start_scraping(
        engine=req.engine, 
        headless=req.headless, 
        cdp_url=req.cdp_url,
        scrape_limit=req.scrape_limit
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

