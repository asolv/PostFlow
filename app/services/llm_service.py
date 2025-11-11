# app/services/llm_service.py
from __future__ import annotations
from typing import List, Dict, Any, Union
from openai import OpenAI
import orjson

from app.core.config import settings

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT = """You are a Korean content editor who turns trending queries into concise, RSS-ready items for Naver/Tistory audiences.

OUTPUT FORMAT:
Return STRICT JSON only (no markdown fences, no commentary):
{
  "items": [
    {"title": "string", "description": "string"}
  ]
}

RULES:
- Korean output.
- 2~5 items total unless instructed otherwise.
- Each description ≤ 280 chars, neutral/informative tone, no emojis, no hashtags.
- Do NOT fabricate specifics (dates, prices, official announcements). Prefer cautious phrasing (e.g., "~로 주목", "~에 관심 증가").
- Prefer angles that match KR blog/portal consumption (요약 + 포인트/활용/이슈).
- Disambiguation is CRUCIAL:
  * Use provided metadata: categories, search_volume, links' hostnames.
  * If categories/hosts imply media/entertainment/streaming (e.g., '미디어', '엔터', '플랫폼', or hosts like youtube.com, tiktok.com, afreecatv.com, chzzk.naver.com), interpret accordingly even for ambiguous Korean nouns.
  * If categories/hosts imply nature/environment/forest services (산림청, 환경, 생태), use that sense.
  * If metadata is mixed or unclear, choose the sense that best fits KR web trends and recent interest, and keep wording conservative.
- No citations, no URLs in the description (titles may include concise identifiers if needed).
"""

def _fallback_items_from_keywords(keywords: List[str]) -> Dict[str, Any]:
    items = []
    for k in keywords[:3]:
        items.append({
            "title": k,
            "description": f"'{k}' 관련 최근 관심도 상승 이슈를 요약. 세부 사항은 공식 발표·주요 매체 보도를 확인하세요."
        })
    return {"items": items}

def _fallback_items_from_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    items = []
    for r in records[:3]:
        title = r.get("title") or r.get("query") or "트렌드"
        cat = r.get("categories") or ""
        sv = r.get("search_volume")
        bits = []
        if cat:
            bits.append(f"카테고리: {cat}")
        if isinstance(sv, int):
            bits.append(f"검색량: {sv}")
        desc = f"{title} 관련 최근 관심 요약" + (f" ({', '.join(bits)})" if bits else "")
        items.append({"title": title, "description": desc[:280]})
    return {"items": items}

def _to_records_from_keywords(keywords: List[str]) -> List[Dict[str, Any]]:
    # 최소 호환: 문자열 키워드만 온 경우 title만 채운 레코드로 변환
    return [{"title": kw} for kw in keywords]

def _build_user_prompt_from_records(records: List[Dict[str, Any]], max_items: int | None = None) -> str:
    # records 예시 필드:
    # title, categories, search_volume, increase_percentage, trends_link, news_link
    lines = []
    lines.append("다음 '트렌드 레코드'를 바탕으로 RSS 항목을 생성해줘.")
    lines.append("- 각 레코드는 중요도에 따라 정렬되어 있음(상위일수록 중요).")
    lines.append("- 제공된 메타데이터(카테고리/검색량/링크 호스트)를 근거로 의미를 정확히 해석해.")
    lines.append("- 한국 블로그·포털의 관심사 흐름을 반영하되 사실 단정은 피하고 보수적으로 기술해.")
    if max_items:
        lines.append(f"- 총 {max_items}개 항목으로 만들어.")
    lines.append("")
    lines.append("트렌드 레코드:")
    for rec in records:
        title = rec.get("title") or rec.get("query") or ""
        cats = rec.get("categories") or ""
        sv = rec.get("search_volume")
        inc = rec.get("increase_percentage")
        tlink = rec.get("trends_link") or ""
        nlink = rec.get("news_link") or ""
        # 호스트 힌트만 텍스트로 제공(실제 접속 요구 없음)
        def _host(url: str) -> str:
            try:
                # 단순 호스트 추출
                h = url.split("//", 1)[-1].split("/", 1)[0]
                return h
            except Exception:
                return ""
        hosts = ", ".join([h for h in [_host(tlink), _host(nlink)] if h])
        meta_parts = []
        if cats: meta_parts.append(f"categories={cats}")
        if isinstance(sv, int): meta_parts.append(f"search_volume={sv}")
        if isinstance(inc, int): meta_parts.append(f"increase_percentage={inc}")
        if hosts: meta_parts.append(f"hosts={hosts}")
        meta = "; ".join(meta_parts) if meta_parts else "no-meta"
        lines.append(f"- title: {title} | meta: {meta}")
    lines.append("")
    lines.append("JSON만 출력해.")
    return "\n".join(lines)

def generate_items_from_keywords(keywords: List[str], max_items: int | None = 4) -> Dict[str, Any]:
    """
    기존 인터페이스 유지: 문자열 키워드 리스트만 받아도 동작.
    가능하면 generate_items_from_records 사용을 권장.
    """
    if not keywords:
        return {"items": []}
    records = _to_records_from_keywords(keywords)
    return generate_items_from_records(records, max_items=max_items)

def generate_items_from_records(records: List[Dict[str, Any]], max_items: int | None = 4) -> Dict[str, Any]:
    """
    권장 인터페이스: 메타데이터를 포함한 레코드들로 LLM에 힌트를 제공.
    각 레코드(dict) 예:
      {
        "title": "숲",
        "categories": "엔터|플랫폼",
        "search_volume": 1200,
        "increase_percentage": 85,
        "trends_link": "https://trends.google.com/...",
        "news_link": "https://news.google.com/..."
      }
    """
    if not records:
        return {"items": []}

    user_prompt = _build_user_prompt_from_records(records, max_items=max_items)

    try:
        resp = client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        text = resp.choices[0].message.content.strip()

        # 안전장치: 혹시라도 fence가 섞이면 제거
        if text.startswith("```"):
            text = text.strip("` \n")
            if text.lower().startswith("json"):
                text = text[4:].strip()

        data = orjson.loads(text)
        # 최소 스키마 검증
        if not isinstance(data, dict) or "items" not in data or not isinstance(data["items"], list):
            # records 기반 폴백
            return _fallback_items_from_records(records)
        # 길이/형식 보정
        fixed_items = []
        for it in data["items"]:
            if not isinstance(it, dict):
                continue
            title = str(it.get("title", "")).strip()
            desc = str(it.get("description", "")).strip()
            if not title:
                continue
            if len(desc) > 280:
                desc = desc[:280]
            fixed_items.append({"title": title, "description": desc})
        if not fixed_items:
            return _fallback_items_from_records(records)
        if max_items:
            fixed_items = fixed_items[:max_items]
        return {"items": fixed_items}
    except Exception:
        # 최후 폴백
        return _fallback_items_from_records(records)
