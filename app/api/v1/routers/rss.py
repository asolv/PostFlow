# app\api\v1\routers\rss.py
from fastapi import APIRouter, Query, HTTPException, Response
from app.db.postgres import get_top_news
from app.services.llm_service import generate_rss_feed_by_gpt
from app.services.rss_service import build_rss_xml

from app.schemas.naver_ranking import NaverRankingCollectResult
from app.services.naver_ranking_service import collect_and_save_naver_ranking

router = APIRouter(prefix="/rss", tags=["rss"])

from fastapi import APIRouter, Query, Response

from app.db.postgres import get_top_news
from app.services.llm_service import generate_rss_feed_by_gpt
from app.services.rss_service import build_rss_xml

router = APIRouter(prefix="/rss", tags=["rss"])
@router.post("/generate", summary="최신뉴스 기반 RSS 생성")
def generate_rss(
    keyword: str | None = Query(
        None,
        description="키워드 (없으면 최신뉴스 제목 자동 사용)"
    ),
    category: str | None = Query(
        None,
        description="""카테고리 (없으면 최신뉴스 제목 자동 사용)
예: 정치|경제|육아
- "육아"
- "교육"
- "경제"
- "스포츠"
- "연예"
- "사회"
- "생활"
- "세계"
- "문화"
- "IT"
- "과학"
- "정치"
- "오피니언"
"""
    ),

    # ---- 옵션 파라미터(없으면 기본값 적용) ----
    ages: int | None = Query(
        30,
        description="연령대 (예: 20, 30, 40)"
    ),
    contry_type: str | None = Query(
        '대한민국',
        description="국가/지역 정보"
    ),
    sex: str | None = Query(
        '남성',
        description="성별"
    ),
    type: str | None = Query(
        '유쾌한',
        description="말투/톤"
    ),
    length: int | None = Query(
        8000,
        description="본문 목표 글자 수 (없으면 기본값 5000)"
    ),
):
    if not keyword:
        row = get_top_news(category)
        keyword = row["title"] if row else "오늘의 주요 뉴스"

    ages = ages or 30
    contry_type = contry_type or "대한민국"
    sex = sex or "남성"
    type = type or "진중한"
    length = length or 5000

    items = generate_rss_feed_by_gpt(
        keyword=keyword,
        ages=ages,
        contry_type=contry_type,
        sex=sex,
        type=type,
        length=length,
    )

    xml_data = build_rss_xml([items])
    return Response(content=xml_data, media_type="application/rss+xml; charset=utf-8")



@router.post("/naver/ranking/collect", response_model=NaverRankingCollectResult)
def collect_naver_ranking_news() -> NaverRankingCollectResult:
    """
    네이버 랭킹뉴스(언론사별 많이 본 뉴스)를 스크래핑해서 DB에 저장하고,
    저장된 항목들을 그대로 반환하는 API.
    """
    items = collect_and_save_naver_ranking()
    return NaverRankingCollectResult(count=len(items), items=items)
