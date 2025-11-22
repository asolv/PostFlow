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
                {"title": "...", "summary": "...", "content": "..."},
                ...
            ]},
            {"items": [
                {"title": "...", "summary": "...", "content": "..."},
            ]},
        ]

    raw_items 예시 2:
        [
            {"title": "...", "summary": "...", "content": "..."},
            ...
        ]

    두 경우 모두 처리해서
    RSS 2.0 XML(bytes)를 리턴한다.
    """

    # 1) 먼저 평탄화: 최종적으로 articles = [{title, summary, content}, ...]
    articles: List[Dict[str, Any]] = []

    for it in raw_items or []:
        if not isinstance(it, dict):
            continue

        # case: {"items": [ {...}, {...} ]}
        if "items" in it and isinstance(it["items"], list):
            for inner in it["items"]:
                if isinstance(inner, dict):
                    articles.append(inner)
        # case: {"title": "...", "summary": "...", "content": "..."}
        elif "title" in it or "summary" in it or "content" in it:
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

        guid = f"trend:{idx}:{int(now.timestamp())}"
        SubElement(item_el, "guid").text = guid
        SubElement(item_el, "pubDate").text = format_datetime(now)

    return tostring(rss, encoding="utf-8", xml_declaration=True)