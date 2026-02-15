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
    current_source: Optional[str] = None
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
    # Multi-source fields
    source_type: Optional[str] = None  # filter to a specific source type
    source_types: Optional[List[str]] = None  # or multiple source types

class SourceConfig(BaseModel):
    source_type: str
    name: str
    jurisdiction: str
    category: str
    enabled: bool = True
    params: dict = {}

class SourcesUpdateRequest(BaseModel):
    sources: List[SourceConfig]
