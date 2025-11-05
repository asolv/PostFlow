from __future__ import annotations
from typing import Iterable, Dict, Any, Optional
from datetime import datetime, timezone

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.types.json import Json

from app.core.config import settings

pool: ConnectionPool | None = None

DDL_CREATE = """
CREATE TABLE IF NOT EXISTS trending_keywords (
  id                 BIGSERIAL PRIMARY KEY,
  collected_at       TIMESTAMPTZ NOT NULL,
  geo                TEXT,
  hl                 TEXT,
  hours              INT,
  title              TEXT NOT NULL,        -- = query(호환성을 위해 title 컬럼 유지)
  link               TEXT,                 -- 기존 호환용 (없으면 NULL)
  categories         TEXT,                 -- 카테고리 name들을 '|'로 합친 문자열
  search_volume      INT,
  increase_percentage INT,
  active             BOOLEAN,
  start_time         TIMESTAMPTZ,          -- start_timestamp(초) -> UTC 변환
  trends_link        TEXT,                 -- serpapi_google_trends_link
  news_page_token    TEXT,                 -- news_page_token
  news_link          TEXT,                 -- serpapi_news_link
  raw_json           JSONB
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trending_keywords_collected_at ON trending_keywords (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_trending_keywords_title        ON trending_keywords (title);
"""

def init_pool():
    global pool
    if pool is None:
        if not settings.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is empty")
        pool = ConnectionPool(settings.DATABASE_URL, min_size=1, max_size=4, open=True)
        with pool.connection() as conn:
            conn.execute(DDL_CREATE)

def close_pool():
    global pool
    if pool:
        pool.close()
        pool = None

def _epoch_to_ts(epoch: Optional[int]) -> Optional[datetime]:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    except Exception:
        return None

def _categories_pipe(item: Dict[str, Any]) -> Optional[str]:
    cats = item.get("categories")
    if isinstance(cats, list) and cats:
        names = [c.get("name") for c in cats if isinstance(c, dict) and c.get("name")]
        if names:
            return "|".join(names)
    return None

def _normalize_item_for_insert(it: Dict[str, Any]) -> Dict[str, Any]:
    # SerpAPI data.trending_searches[] 표준 키들 매핑
    query = it.get("query") or it.get("title") or it.get("name")
    link = it.get("link") or it.get("explore_link")  # 호환용(없어도 무방)
    start_ts = _epoch_to_ts(it.get("start_timestamp"))
    categories = _categories_pipe(it)

    return {
        "title": query,  # DB 컬럼은 title 이름 유지
        "link": link,
        "categories": categories,
        "search_volume": it.get("search_volume"),
        "increase_percentage": it.get("increase_percentage"),
        "active": it.get("active"),
        "start_time": start_ts,
        "trends_link": it.get("serpapi_google_trends_link"),
        "news_page_token": it.get("news_page_token"),
        "news_link": it.get("serpapi_news_link"),
        "raw": it,
    }

def save_keywords(geo: str, hl: str, hours: int, items: Iterable[Dict[str, Any]]) -> int:
    if pool is None:
        raise RuntimeError("Pool not initialized")

    now = datetime.now(timezone.utc)
    rows = []
    for it in items:
        n = _normalize_item_for_insert(it)
        if not n.get("title"):
            continue  # 제목(=query) 없으면 스킵
        rows.append((
            now, geo, hl, hours,
            n["title"], n["link"],
            n["categories"], n["search_volume"], n["increase_percentage"], n["active"], n["start_time"],
            n["trends_link"], n["news_page_token"], n["news_link"],
            Json(n["raw"]),
        ))

    if not rows:
        return 0

    sql = """
    INSERT INTO trending_keywords (
      collected_at, geo, hl, hours,
      title, link,
      categories, search_volume, increase_percentage, active, start_time,
      trends_link, news_page_token, news_link,
      raw_json
    )
    VALUES (
      %s,%s,%s,%s,
      %s,%s,
      %s,%s,%s,%s,%s,
      %s,%s,%s,
      %s
    );
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)
        conn.commit()
    return len(rows)
