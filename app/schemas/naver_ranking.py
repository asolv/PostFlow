from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel


class NaverRankingNewsItem(BaseModel):
    press: str
    category: Optional[str] = None
    rank: int
    title: str
    link: str


class NaverRankingCollectResult(BaseModel):
    count: int
    items: List[NaverRankingNewsItem]
