from __future__ import annotations
from typing import Iterable, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
import re

import psycopg
from psycopg_pool import ConnectionPool
from psycopg.types.json import Json
from psycopg.rows import dict_row

from app.core.config import settings

pool: ConnectionPool | None = None

DDL_CREATE = """
CREATE TABLE IF NOT EXISTS trending_keywords (
  id                  BIGSERIAL PRIMARY KEY,
  collected_at        TIMESTAMPTZ NOT NULL,
  geo                 TEXT,
  hl                  TEXT,
  hours               INT,
  title               TEXT NOT NULL,        -- = query(호환성을 위해 title 컬럼 유지)
  link                TEXT,                 -- 기존 호환용 (없으면 NULL)
  categories          TEXT,                 -- 카테고리 name들을 '|'로 합친 문자열
  search_volume       INT,
  increase_percentage INT,
  active              BOOLEAN,
  start_time          TIMESTAMPTZ,          -- start_timestamp(초) -> UTC 변환
  trends_link         TEXT,                 -- serpapi_google_trends_link
  news_page_token     TEXT,                 -- news_page_token
  news_link           TEXT,                 -- serpapi_news_link
  raw_json            JSONB
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_trending_keywords_collected_at ON trending_keywords (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_trending_keywords_title        ON trending_keywords (title);

-- 네이버 랭킹뉴스 테이블
CREATE TABLE IF NOT EXISTS naver_ranking_news (
  id           BIGSERIAL PRIMARY KEY,
  collected_at TIMESTAMPTZ NOT NULL,
  press        TEXT        NOT NULL,   -- 언론사 이름
  category     TEXT,                   -- 섹션(정치/경제/사회 등), 없으면 NULL
  rank         INT         NOT NULL,   -- 언론사별 랭킹 순위
  title        TEXT        NOT NULL,   -- 기사 제목
  link         TEXT        NOT NULL,   -- 기사 링크
  raw_json     JSONB                   -- 원본 전체 JSON
);

CREATE INDEX IF NOT EXISTS idx_naver_ranking_collected_at ON naver_ranking_news (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_naver_ranking_press        ON naver_ranking_news (press);
CREATE INDEX IF NOT EXISTS idx_naver_ranking_title        ON naver_ranking_news (title);
"""

def init_pool():
    """Initialize the global connection pool and ensure DDL exists."""
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
    """Bulk-insert trending keywords collected at the same time."""
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

# ---------------------------
# 신규: 상위 트렌드 키워드 조회
# ---------------------------

def _category_regex(category: str) -> str:
    """
    categories 컬럼이 'A|B|C' 형태일 때 정확한 토큰 매칭을 위한 정규식 패턴을 생성.
    대소문자 무시(~* 사용).
    """
    safe = re.escape(category.strip())
    # 경계: 시작/끝 또는 파이프(|)
    return rf"(^|\|){safe}($|\|)"

def get_top_trending_keyword(category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    최근 4시간 내(collected_at 기준), search_volume >= 500 조건에서
    (선택) 카테고리 정확 매칭으로 필터하여 가장 높은 검색어 하나를 반환.
    - category 가 주어졌는데 해당 범위에 데이터 없으면 None.
    - category 가 없으면 전체에서 선택.
    반환값: dict(컬럼 전부 포함) 또는 None
    """
    if pool is None:
        raise RuntimeError("Pool not initialized")

    cutoff = datetime.now(timezone.utc) - timedelta(hours=4)

    sql_base = """
        SELECT
            id, collected_at, geo, hl, hours,
            title, link, categories, search_volume, increase_percentage,
            active, start_time, trends_link, news_page_token, news_link, raw_json
        FROM trending_keywords
        WHERE collected_at >= %s
          AND (search_volume IS NOT NULL AND search_volume >= 500)
    """

    args = [cutoff]

    if category and category.strip():
        # 정확 매칭 정규식 (~* : case-insensitive)
        pattern = _category_regex(category)
        sql = sql_base + " AND categories IS NOT NULL AND categories ~* %s "
        args.append(pattern)
    else:
        sql = sql_base

    # 우선순위 정렬
    sql += """
        ORDER BY
            search_volume DESC NULLS LAST,
            increase_percentage DESC NULLS LAST,
            collected_at DESC
        LIMIT 1
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, args)
            row = cur.fetchone()

    return dict(row) if row else None

# ---------------------------
# 신규: 네이버 랭킹뉴스 저장
# ---------------------------

def save_naver_ranking_news(items: Iterable[Dict[str, Any]]) -> int:
    """
    네이버 랭킹뉴스 목록을 naver_ranking_news 테이블에 저장.
    - 제목(title) 기준으로 UNIQUE.
    - 이미 같은 제목이 있으면 500 에러 대신 그냥 무시(삽입 안 함).
    - 저장 시점에 기준으로 3일 이전 데이터는 먼저 삭제.
    """
    if pool is None:
        raise RuntimeError("Pool not initialized")

    now = datetime.now(timezone.utc)
    rows = []

    for it in items:
        press = it.get("press")
        title = it.get("title")
        link = it.get("link")
        rank = it.get("rank")
        category = it.get("category")

        if not press or not title or not link or rank is None:
            continue

        try:
            rank_int = int(rank)
        except Exception:
            continue

        rows.append(
            (now, press, category, rank_int, title, link, Json(it))
        )

    if not rows:
        return 0

    sql = """
    INSERT INTO naver_ranking_news (
      collected_at,
      press,
      category,
      rank,
      title,
      link,
      raw_json
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (title) DO NOTHING;
    """

    with pool.connection() as conn:
        with conn.cursor() as cur:
            # 🔹 먼저 3일 이전 데이터 삭제
            cur.execute(
                """
                DELETE FROM naver_ranking_news
                 WHERE collected_at < NOW() - INTERVAL '3 days'
                """
            )
            # 🔹 그 다음 새 데이터 삽입
            cur.executemany(sql, rows)
        conn.commit()

    return len(rows)

def get_top_news(category: str | None = None) -> Optional[Dict[str, Any]]:
    """
    24시간 내 최신뉴스 중 랜덤 1개 추출.
    category 다중 입력 가능: "정치|경제|사회"
    """
    if pool is None:
        raise RuntimeError("Pool not initialized")

    # 기본 SQL
    base_sql = """
        SELECT id, press, rank, title
          FROM naver_ranking_news
         WHERE collected_at >= NOW() - INTERVAL '24 hours'
    """

    params = []

    # 다중 카테고리 처리
    if category:
        cats = [c.strip() for c in category.split("|") if c.strip()]
        if cats:
            placeholders = ",".join(["%s"] * len(cats))
            base_sql += f" AND category IN ({placeholders})"
            params.extend(cats)

    # 랜덤 순서
    base_sql += """
         ORDER BY RANDOM()
         LIMIT 1;
    """

    with pool.connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(base_sql, params)
            row = cur.fetchone()

    return dict(row) if row else None