from curl_cffi import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple
from utils.logger import logger
from utils.config import config
import time
import json

import os

class DiscoveryEngine:
    """
    负责探索 CanLII 网站结构以发现新的抓取目标
    Responsible for exploring CanLII structure to discover new scrape targets
    """
    CACHE_FILE = "discovery_cache.json"
    
    def __init__(self):
        self.base_url = "https://www.canlii.org"
        # Use curl_cffi session for 403 bypass
        self.session = requests.Session()
        self.session.headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
            "Sec-Ch-Ua": '"Not?A_Brand";v="8", "Chromium";v="124", "Google Chrome";v="124"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1"
        }
        self.is_warmed_up = False
        
    def get_cached_results(self) -> List[Dict]:
        """Load results from cache file"""
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load discovery cache: {e}")
        return []

    def _save_cache(self, results: List[Dict]):
        """Save results to cache file"""
        try:
            with open(self.CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save discovery cache: {e}")
        
    def _warm_up(self):
        """Visit home page to get DataDome cookies"""
        if self.is_warmed_up:
            return
        try:
            logger.info("DiscoveryEngine: Warming up session...")
            self.session.get(self.base_url, impersonate="safari15_5", timeout=10)
            self.is_warmed_up = True
            time.sleep(1) # Be polite
        except Exception as e:
            logger.warning(f"DiscoveryEngine warmup warning: {e}")

    def discover_targets_generator(self):
        """
        Generator that yields progress events and finally the results.
        Yields: dict with 'type' ('progress', 'found', 'complete', 'error') and data
        """
        targets = [] # Accumulate full list
        try:
            logger.info("Starting discovery...")
            self._warm_up()
            
            jurisdictions = [
                {'code': 'ca', 'name': 'Canada (Federal)'},
                {'code': 'ab', 'name': 'Alberta'},
                {'code': 'bc', 'name': 'British Columbia'},
                {'code': 'on', 'name': 'Ontario'},
                {'code': 'qc', 'name': 'Quebec'},
                {'code': 'ns', 'name': 'Nova Scotia'},
                {'code': 'nb', 'name': 'New Brunswick'},
                {'code': 'mb', 'name': 'Manitoba'},
                {'code': 'pe', 'name': 'Prince Edward Island'},
                {'code': 'sk', 'name': 'Saskatchewan'},
                {'code': 'nl', 'name': 'Newfoundland and Labrador'},
            ]
            
            total_checks = len(jurisdictions) # base progress on jurisdictions
            completed_checks = 0

            for jur in jurisdictions:
                # Yield progress for jurisdiction start
                yield {
                    "type": "progress", 
                    "message": f"Scanning {jur['name']}...", 
                    "percent": int((completed_checks / total_checks) * 100)
                }
                
                # Fetch jurisdiction page to find all databases (Legislation, Courts, Tribunals)
                jur_url = f"{self.base_url}/en/{jur['code']}/"
                
                # Moderate delay for jurisdiction page
                time.sleep(1.0)
                
                databases = self._scan_jurisdiction_page(jur_url, jur['code'], jur['name'])
                
                if not databases:
                    logger.warning(f"No databases found for {jur['name']}, possibly rate limited.")
                
                for db in databases:
                    # OPTIMIZATION: Only check details (make network request) for Legislation to get counts.
                    # For Courts and Tribunals, blindly trust the index page to avoid 50+ requests per province.
                    
                    target = None
                    
                    if db['category'] == 'Legislation':
                        # Distinguish Statutes vs Regulations
                        sub_cat = "Statutes"
                        if '/regu' in db['url']:
                            sub_cat = "Regulations"
                        elif '/stat' in db['url'] or '/astat' in db['url']:
                            sub_cat = "Statutes"
                        
                        # Fetch item count
                        exists, count = self._check_target_details(db['url'], db['category'])
                        if exists:
                            target = {
                                "name": db['name'],
                                "province": jur['code'],
                                "province_name": jur['name'],
                                "type": sub_cat,
                                "type_name": db['name'],
                                "url": db['url'],
                                "status": "Available",
                                "item_count": count
                            }
                        # Delay for active check
                        time.sleep(0.5) 
                    else:
                        # "Passive" discovery for Courts/Tribunals - Assume valid if on page
                        target = {
                            "name": db['name'],
                            "province": jur['code'],
                            "province_name": jur['name'],
                            "type": db['category'],
                            "type_name": db['name'],
                            "url": db['url'],
                            "status": "Available",
                            "item_count": "Browse" # Don't fetch generic page just to say it exists
                        }
                        # Minimal delay for passive processing
                        time.sleep(0.01)

                    if target:
                        targets.append(target)
                        # Yield immediate result for UI
                        yield {"type": "found", "data": target}
                
                # Periodically save cache (optional but safer)
                self._save_cache(targets)
                
                completed_checks += 1
            
            # Final yield
            self._save_cache(targets)
            yield {"type": "complete", "results": targets}
                    
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            yield {"type": "error", "message": str(e)}

    def _scan_jurisdiction_page(self, url: str, jur_code: str, jur_name: str) -> List[Dict]:
        """
        Parse jurisdiction page to find databases.
        Returns list of dict: {'name': str, 'url': str, 'category': str}
        """
        databases = []
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                resp = self.session.get(url, impersonate="safari15_5", timeout=15)
                
                if resp.status_code == 429:
                    wait = (attempt + 1) * 5 # Back to moderate backoff
                    logger.warning(f"Rate limited (429) on {url}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                
                if resp.status_code != 200:
                    logger.warning(f"Failed to fetch jurisdiction page {url}: {resp.status_code}")
                    return []
                
                # Success - break retry loop
                break
                
            except Exception as e:
                logger.warning(f"Error fetching {url}: {e}")
                if attempt == max_retries - 1:
                    return []
                time.sleep(2)
        else:
            # Failed after retries
            return []

        try:
            soup = BeautifulSoup(resp.content, 'lxml')
            
            # Use body or fall back to soup if no body (unlikely)
            content_root = soup.find('body') or soup
            
            current_category = "Other"
            
            # Categories we care about
            valid_categories = ['Legislation', 'Courts', 'Boards and Tribunals', 'Législation', 'Tribunaux']
            
            # Iterate through all relevant tags in document order
            # We filter for only headers and links to save processing time check
            tags = content_root.find_all(['h2', 'h3', 'a'])
            
            for element in tags:
                if element.name in ['h2', 'h3']:
                    text = element.get_text(strip=True)
                    # Normalize category
                    if any(c in text for c in valid_categories):
                        current_category = text.split('(')[0].strip() # Remove (3) counts if any
                        # Map French to English
                        if 'Législation' in current_category: current_category = 'Legislation'
                        if 'Tribunaux' in current_category: current_category = 'Courts'
                        if 'Boards' in current_category or 'Tribunals' in current_category: current_category = 'Boards and Tribunals'
                
                if element.name == 'a' and element.get('href'):
                    href = element.get('href')
                    text = element.get_text(strip=True)
                    
                    # Must be a relative path starting with /jur_code/ or /en/jur_code/ to be internal
                    # Filter out external links (http...)
                    if href.startswith('http'):
                        continue
                    
                    # Filter out noise
                    if 'reset' in href or 'javascript' in href:
                        continue
                        
                    # Normalize URL to full path without /en/ prefix for scraper consistency
                    # href might be "/ab/laws/stat/" or "/en/ab/laws/stat/"
                    # We want "https://www.canlii.org/ab/laws/stat"
                    
                    full_url = ""
                    if href.startswith('/en/'):
                        full_url = f"https://www.canlii.org{href.replace('/en/', '/')}"
                    elif href.startswith('/'):
                        full_url = f"https://www.canlii.org{href}"
                    else:
                        continue
                        
                    # Remove trailing slash
                    full_url = full_url.rstrip('/')
                    
                    # Only add if it belongs to this jurisdiction (simple check)
                    if f"/{jur_code}" not in full_url:
                        continue

                    # Determine if it's a database index or a comprehensive list
                    # Usually database indices are like /ab/abca or /ab/laws/stat
                    # If it's a specific document (c-a-1), we might skip it? 
                    # No, for 'Annual Statutes' it might link to a list.
                    # Let's verify commonly known patterns or just accept all internal database links.
                    
                    # Heuristic: Valid databases usually don't have many segments after jurisdiction
                    # /ab/laws/stat -> OK
                    # /ab/abca -> OK
                    # /ab/laws/stat/rsa-2000-c-a-1 -> Document (Skip)
                    
                    # Count segments after domain
                    path_parts = full_url.replace("https://www.canlii.org/", "").split('/')
                    # path_parts = ['ab', 'laws', 'stat'] or ['ab', 'abca']
                    
                    if len(path_parts) > 4: # Too deep, likely a document
                        continue
                        
                    databases.append({
                        'name': text,
                        'url': full_url,
                        'category': current_category
                    })
            
            return databases
            
        except Exception as e:
            logger.warning(f"Error scanning jurisdiction {url}: {e}")
            return []

    def _check_target_details(self, url: str, category: str = "Legislation") -> Tuple[bool, Optional[str]]:
        """
        Check if target exists and try to return item count.
        Returns: (exists: bool, count: str|int|None)
        """
        try:
            # Strategy 1: JSON API (Legislation)
            if category == "Legislation":
                api_url = url.rstrip('/') + "/items"
                headers = self.session.headers.copy()
                headers["Referer"] = "https://www.canlii.org/"
                headers["Sec-Fetch-Site"] = "same-origin"
                
                resp = self.session.get(
                    api_url, 
                    impersonate="safari15_5", 
                    headers=headers,
                    timeout=10
                )
                
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                        return True, len(data)
                    except:
                        return True, 0
                elif resp.status_code == 404:
                    return False, None
                else:
                    # 403 or other, assume exists
                    return True, "Access Denied"

            # Strategy 2: Simple Page Check (Courts/Tribunals)
            else:
                resp = self.session.get(
                    url, 
                    impersonate="safari15_5", 
                    timeout=10
                )
                if resp.status_code == 200:
                    return True, "Browse" # Count unknown
                elif resp.status_code == 404:
                    return False, None
                else:
                    return True, "Protected"

        except Exception as e:
            logger.warning(f"URL check error for {url}: {e}")
            return False, None
discovery_engine = DiscoveryEngine()
