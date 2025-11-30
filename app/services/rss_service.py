from xml.etree.ElementTree import Element, SubElement, tostring
from datetime import datetime, timezone
from email.utils import format_datetime
import html
from typing import List, Dict, Any


def build_rss_xml(
    raw_items: List[Dict[str, Any]],
    feed_title: str = "뉴스 RSS 피드",
    feed_link: str = "https://example.com",
    feed_description: str = "GPT로 생성된 뉴스 요약 피드",
) -> bytes:
    """
    raw_items 예시 1:
        [
            {"items": [
                {"title": "...", "summary": "...", "content": "...", "tags": "... 또는 [...]"},
                ...
            ]},
            {"items": [
                {"title": "...", "summary": "...", "content": "...", "tags": "... 또는 [...]"},
            ]},
        ]

    raw_items 예시 2:
        [
            {"title": "...", "summary": "...", "content": "...", "tags": "... 또는 [...]"},
            ...
        ]

    두 경우 모두 처리해서
    RSS 2.0 XML(bytes)를 리턴한다.

    tags 처리 규칙:
      - tags 가 list 면: ["Samsung Family", "Innovation", "Future Vision"]
      - tags 가 str 면: 콤마/줄바꿈 기준 split 후 trim
      - RSS 상에서는
          <tags>Samsung Family,Innovation,Future Vision</tags>
          <category>Samsung Family</category>
          <category>Innovation</category>
          <category>Future Vision</category>
        형태로 내려간다.
    """

    # 1) 먼저 평탄화: 최종적으로 articles = [{title, summary, content, tags, ...}, ...]
    articles: List[Dict[str, Any]] = []

    for it in raw_items or []:
        if not isinstance(it, dict):
            continue

        # case: {"items": [ {...}, {...} ]}
        if "items" in it and isinstance(it["items"], list):
            for inner in it["items"]:
                if isinstance(inner, dict):
                    articles.append(inner)
        # case: {"title": "...", "summary": "...", "content": "...", ...}
        elif "title" in it or "summary" in it or "content" in it or "tags" in it:
            articles.append(it)

    # 2) RSS XML 생성
    now = datetime.now(timezone.utc)

    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = html.escape(feed_title)
    SubElement(channel, "link").text = feed_link
    SubElement(channel, "description").text = html.escape(feed_description)
    SubElement(channel, "lastBuildDate").text = format_datetime(now)

    for idx, art in enumerate(articles, start=1):
        item_el = SubElement(channel, "item")

        title = str(art.get("title") or f"Untitled {idx}")
        summary = str(art.get("summary") or "")
        content = str(art.get("content") or "")

        # summary + content를 description에 합쳐서 넣기
        description_text = (summary + "\n\n" + content).strip()

        SubElement(item_el, "title").text = html.escape(title)
        SubElement(item_el, "description").text = html.escape(description_text)

        # ---- tags 처리 시작 ----
        raw_tags = art.get("tags")
        tag_list: List[str] = []

        if isinstance(raw_tags, list):
            # 리스트일 경우
            tag_list = [str(t).strip() for t in raw_tags if str(t).strip()]
            tags_text = ",".join(tag_list) if tag_list else ""
        elif isinstance(raw_tags, str):
            # 문자열일 경우: 콤마/줄바꿈 기준으로 split
            parts = []
            for chunk in raw_tags.replace("\r", "\n").split("\n"):
                for p in chunk.split(","):
                    p = p.strip()
                    if p:
                        parts.append(p)
            tag_list = parts
            tags_text = ",".join(tag_list) if tag_list else ""
        else:
            tags_text = ""

        # <tags> 요소: 클라이언트에서 그대로 읽어서 사용하기 좋게
        if tags_text:
            SubElement(item_el, "tags").text = html.escape(tags_text)

        # <category> 요소: RSS 표준 태그(원하면 RSS 리더에서도 활용 가능)
        for tg in tag_list:
            SubElement(item_el, "category").text = html.escape(tg)
        # ---- tags 처리 끝 ----

        guid = f"trend:{idx}:{int(now.timestamp())}"
        SubElement(item_el, "guid").text = guid
        SubElement(item_el, "pubDate").text = format_datetime(now)

    return tostring(rss, encoding="utf-8", xml_declaration=True)
