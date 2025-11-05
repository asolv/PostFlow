from __future__ import annotations
from typing import Any, Dict, List, Optional
import requests

from app.core.config import settings

SERP_ENDPOINT = "https://serpapi.com/search"  # engine=google_trends_trending_now 

def _pick_trending_array(data: Dict[str, Any]) -> List[Dict[str, Any]]:

    if isinstance(data, dict):
        arr = data.get("trending_searches")
        if isinstance(arr, list) and arr:
            return arr

    return []

def fetch_trending_now(
    geo: str = "KR",
    hl: str = "ko",
    category_id: Optional[int] = None,
    hours: int = 24,
    no_cache: bool = False,
    timeout: tuple[float, float] = (5.0, 20.0),
) -> Dict[str, Any]:
    if not settings.SERPAPI_API_KEY:
        return {"items": [], "raw": None, "meta": {"error": "SERPAPI_API_KEY is empty"}}

    params: Dict[str, Any] = {
        "engine": "google_trends_trending_now",
        "api_key": settings.SERPAPI_API_KEY,
        "geo": geo,
        "hl": hl,
        "hours": hours,
    }
    if category_id is not None:
        params["category_id"] = category_id
    if no_cache:
        params["no_cache"] = "true"

    r = requests.get(SERP_ENDPOINT, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()

    items = _pick_trending_array(data)

    meta = {"geo": geo, "hl": hl, "category_id": category_id, "hours": hours, "count": len(items)}
    if "error" in data:
        meta["error"] = data.get("error")

    return {"items": items, "raw": data, "meta": meta}
