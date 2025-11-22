# app/services/naver_ranking_service.py
from __future__ import annotations

from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup

from app.schemas.naver_ranking import NaverRankingNewsItem
from app.db.postgres import save_naver_ranking_news
from app.services.llm_service import categorize_news_titles_by_gpt

# 네이버 랭킹뉴스(많이 본 뉴스) 페이지
NAVER_RANKING_URL = "https://news.naver.com/main/ranking/popularDay.naver"

# 네이버 뉴스 섹션 코드 → 카테고리명 매핑 (기사 개별 링크에 sid/sid1가 있을 때만 사용 가능)
SID_CATEGORY_MAP = {
    "100": "정치",
    "101": "경제",
    "102": "사회",
    "103": "생활/문화",
    "104": "세계",
    "105": "IT/과학",
    "110": "오피니언",
}


def _extract_category_from_link(link: str) -> Optional[str]:
    """
    기사 링크의 쿼리스트링(sid, sid1 등)을 보고 섹션 카테고리를 추출하는 헬퍼.
    실제 랭킹 페이지의 기사 URL은 보통 sid 파라미터가 없어서 대부분 None일 것.
    """
    try:
        parsed = urlparse(link)
        q = parse_qs(parsed.query)
        sid = q.get("sid1", [""])[0] or q.get("sid", [""])[0]
        if not sid:
            return None
        return SID_CATEGORY_MAP.get(sid)
    except Exception:
        return None


def fetch_naver_ranking_html(timeout: tuple[float, float] = (5.0, 20.0)) -> str:
    """
    네이버 랭킹뉴스 HTML을 그대로 가져오는 함수.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PostFlowBot/1.0; +https://example.com)"
    }
    resp = requests.get(NAVER_RANKING_URL, headers=headers, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def parse_naver_ranking(html: str) -> List[NaverRankingNewsItem]:
    """
    네이버 '언론사별 랭킹뉴스' 페이지 HTML을 파싱해서
    (언론사, 순위, 제목, 링크, 카테고리) 리스트를 반환.
    - 언론사: strong.rankingnews_name
    - 제목: a.list_title
    - 링크: a.list_title 의 href
    - 순위: em.list_ranking_num
    - 카테고리: 링크의 sid/sid1 기반 추정 (없으면 None)
    """
    soup = BeautifulSoup(html, "lxml")
    items: List[NaverRankingNewsItem] = []

    # 언론사별 블록
    for box in soup.select("div.rankingnews_box"):
        press_el = box.select_one(".rankingnews_name")
        if not press_el:
            continue

        press_name = press_el.get_text(strip=True)

        # 언론사별 랭킹 리스트 (ul.rankingnews_list > li)
        for li in box.select("ul.rankingnews_list > li"):
            # 순위
            rank_el = li.select_one("em.list_ranking_num")
            a_title = li.select_one("a.list_title")
            if not a_title:
                continue

            title = a_title.get_text(strip=True)
            href = a_title.get("href")
            if not title or not href:
                continue

            link = urljoin(NAVER_RANKING_URL, href)

            try:
                rank = int(rank_el.get_text(strip=True)) if rank_el else None
            except Exception:
                rank = None
            if rank is None:
                continue

            # 카테고리: 기사 링크에서 sid/sid1 추출 시도 (없으면 None)
            category = _extract_category_from_link(link)

            items.append(
                NaverRankingNewsItem(
                    press=press_name,
                    category=category,
                    rank=rank,
                    title=title,
                    link=link,
                )
            )

    return items


def _dedup_by_title(items: List[NaverRankingNewsItem]) -> List[NaverRankingNewsItem]:
    """
    제목 기준으로 중복 제거 (같은 제목은 한 번만 남김).
    """
    seen: Set[str] = set()
    deduped: List[NaverRankingNewsItem] = []

    for it in items:
        # 완전 동일한 문자열 기준 (필요하면 lower() 등 추가 가능)
        if it.title in seen:
            continue
        seen.add(it.title)
        deduped.append(it)

    return deduped


def save_naver_ranking_to_db(items: List[NaverRankingNewsItem]) -> int:
    """
    파싱된 랭킹뉴스를 PostgreSQL에 저장.
    1) rank == 1만 대상으로 필터
    2) 제목 기준으로 in-memory 중복 제거
    3) category가 비어 있는 항목들에 대해 GPT로 카테고리 분류
    4) DB 저장
    """
    if not items:
        return 0

    # 🔹 1위 기사만 남기기
    items = [it for it in items if it.rank == 1]
    if not items:
        return 0

    # 2) 제목 기준 dedup
    items = _dedup_by_title(items)

    # 3) GPT로 카테고리 채우기 (category == None 이나 빈 값만 대상으로)
    idx_list: list[int] = []
    titles_for_gpt: list[str] = []

    for idx, it in enumerate(items):
        if not it.category:  # None 또는 빈 문자열
            idx_list.append(idx)
            titles_for_gpt.append(it.title)

    if titles_for_gpt:
        cats = categorize_news_titles_by_gpt(titles_for_gpt)
        for idx, cat in zip(idx_list, cats):
            items[idx].category = cat

    # 4) DB 저장 (여기서도 한 번 더 rank == 1만 저장)
    payload = [
        {
            "press": it.press,
            "category": it.category,
            "rank": it.rank,
            "title": it.title,
            "link": it.link,
        }
        for it in items
        if it.rank == 1
    ]

    if not payload:
        return 0

    return save_naver_ranking_news(payload)


def collect_and_save_naver_ranking() -> List[NaverRankingNewsItem]:
    """
    1) HTML 가져오고
    2) 파싱해서
    3) rank 1만 필터 + 제목 기준 중복 제거 후 DB에 저장
    4) 최종 아이템 리스트 반환
    """
    html = fetch_naver_ranking_html()
    items = parse_naver_ranking(html)
    save_naver_ranking_to_db(items)
    # 반환도 rank 1 기준으로
    return [it for it in items if it.rank == 1]
