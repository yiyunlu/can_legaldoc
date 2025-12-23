from pydantic import BaseModel
from typing import List, Optional

class ScrapeTarget(BaseModel):
    province: str
    type: str
    url: str
    name: str

class ConfigUpdateRequest(BaseModel):
    targets: List[ScrapeTarget]

class ScraperStatus(BaseModel):
    is_running: bool
    current_target: Optional[str] = None
    stats: dict
    message: str
    scrape_limit: Optional[int] = None

class DiscoveryRequest(BaseModel):
    url: Optional[str] = None # Optional starting point override

class ScraperStartRequest(BaseModel):
    engine: Optional[str] = "fast" # "fast" (curl_cffi) or "deep" (playwright)
    headless: Optional[bool] = True
    cdp_url: Optional[str] = None
    scrape_limit: Optional[int] = 100
