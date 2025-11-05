import os
from fastapi import APIRouter, Query, Header, HTTPException
from typing import Any, Dict, Optional

from app.services.trends_service import fetch_trending_now
from app.db.postgres import save_keywords

router = APIRouter(prefix="/trends", tags=["trends"])

@router.get("/realtime")
def realtime(
    geo: str = Query("KR"),
    hl: str = Query("ko"),
    category_id: Optional[int] = Query(None),
    hours: int = Query(4, ge=1, le=24),
    no_cache: bool = Query(False),
    x_job_token: Optional[str] = Header(None, convert_underscores=False),
) -> Dict[str, Any]:
    try:
        # ---- 토큰 검증 ----
        expected = os.getenv("JOB_TOKEN", "")
        if expected and x_job_token != expected:
            raise HTTPException(status_code=401, detail="unauthorized")
        # -------------------

        data = fetch_trending_now(geo=geo, hl=hl, category_id=category_id, hours=hours, no_cache=no_cache)
        return data
    except Exception as e:
        return {"items": [], "raw": None, "meta": {"error": f"{type(e).__name__}: {e}"}}

@router.post("/realtime/store")
def realtime_store(
    geo: str = Query("KR"),
    hl: str = Query("ko"),
    category_id: Optional[int] = Query(None),
    hours: int = Query(4, ge=1, le=24),
    no_cache: bool = Query(False),
    x_job_token: Optional[str] = Header(None, convert_underscores=False),
) -> Dict[str, Any]:
    # ---- 토큰 검증 ----
    expected = os.getenv("JOB_TOKEN", "")
    if expected and x_job_token != expected:
        raise HTTPException(status_code=401, detail="unauthorized")
    # -------------------

    data = fetch_trending_now(geo=geo, hl=hl, category_id=category_id, hours=hours, no_cache=no_cache)
    items = data.get("items") or []
    stored = save_keywords(geo=geo, hl=hl, hours=hours, items=items)
    return {"ok": True, "stored": stored, "meta": data.get("meta")}
