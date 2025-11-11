from fastapi import APIRouter, Query, HTTPException, Response

from app.db.postgres import get_top_trending_keyword
from app.services.llm_service import generate_items_from_keywords
from app.services.rss_service import build_rss_xml

router = APIRouter(prefix="/rss", tags=["rss"])


@router.get("/generate", summary="카테고리별 상위 검색어 RSS 생성")
def generate_rss(
    category: str | None = Query(None, description="카테고리(없으면 전체에서 검색)"),
):
    # 1) DB에서 최근 4시간 내 search_volume >= 500 중 상위 키워드 1개 조회
    row = get_top_trending_keyword(category)

    if row is None:
        # 조건을 만족하는 키워드 자체가 없으면 RSS 생성 불가 → 204
        raise HTTPException(status_code=204, detail="검색어 없음 (최근 4시간 내 해당 카테고리 데이터 없음)")

    keyword = row["title"]

    # 2) ChatGPT로 RSS item 생성 (키워드 1개 list 형태로 전달)
    items = generate_items_from_keywords([keyword])

    # 3) RSS XML 생성
    xml_data = build_rss_xml(items)

    # 4) XML 반환
    return Response(content=xml_data, media_type="application/rss+xml; charset=utf-8")
