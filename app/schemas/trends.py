from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict

# 공통 쿼리 파라미터
class TrendsCommon(BaseModel):
    hl: str = Field(default="ko-KR", description="UI 언어")
    tz: int = Field(default=540, description="타임존 분 단위(KST=540)")

class RealtimeQuery(TrendsCommon):
    pn: str = Field(default="KR", description="실시간 트렌드 지역 코드. 예: KR, US, JP")
    limit: int = Field(default=20, ge=1, le=100)

class DailyQuery(TrendsCommon):
    pn: str = Field(default="south_korea", description="일간 trending_searches의 pn")
    limit: int = Field(default=20, ge=1, le=50)

class InterestQuery(TrendsCommon):
    keywords: List[str] = Field(..., description="관심도 조회 키워드 리스트")
    timeframe: str = Field(default="now 7-d", description="now 1-d | now 7-d | today 3-m | 2024-01-01 2025-01-01")
    geo: str = Field(default="KR", description="국가/지역 코드")
    cat: int = Field(default=0, description="카테고리 코드(0=전체)")
    gprop: Literal["", "images", "news", "youtube", "froogle"] = Field(default="", description="검색 vertical")

class InterestPoint(BaseModel):
    timestamp: str
    values: Dict[str, int]

class InterestResponse(BaseModel):
    params: InterestQuery
    points: List[InterestPoint]

class RealtimeItem(BaseModel):
    title: str
    entity: Optional[List[str]] = None
    link: Optional[str] = None

class RealtimeResponse(BaseModel):
    params: RealtimeQuery
    items: List[RealtimeItem]

class DailyResponse(BaseModel):
    params: DailyQuery
    items: List[str]
