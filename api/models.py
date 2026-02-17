from pydantic import BaseModel
from typing import Dict, List, Optional

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
    scheduler: Optional[dict] = None

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
    # Limit distribution: sequential | equal | proportional
    distribution_mode: Optional[str] = "proportional"
    # Estimated totals for proportional mode (source_type -> count)
    source_estimates: Optional[Dict[str, int]] = None

class SchedulerConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    schedule_type: Optional[str] = None          # 'daily' | 'interval'
    daily_time: Optional[str] = None             # HH:MM UTC
    interval_hours: Optional[int] = None
    scrape_limit: Optional[int] = None
    source_types: Optional[str] = None           # JSON array string, null = all
    distribution_mode: Optional[str] = None
    supabase_keepalive: Optional[bool] = None
    supabase_keepalive_interval_hours: Optional[int] = None

class SourceConfig(BaseModel):
    source_type: str
    name: str
    jurisdiction: str
    category: str
    enabled: bool = True
    params: dict = {}

class SourcesUpdateRequest(BaseModel):
    sources: List[SourceConfig]
