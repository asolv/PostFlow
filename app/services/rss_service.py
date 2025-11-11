from datetime import datetime, timezone
from typing import Dict
from xml.etree.ElementTree import Element, SubElement, tostring
from app.core.config import settings
import html

def build_rss_xml(items_json: Dict) -> bytes:
    """
    items_json = {"items": [{"title": "...", "description": "..."}, ...]}
    반환: RSS 2.0 XML (bytes)
    """
    now_rfc2822 = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S %z")

    rss = Element("rss", attrib={"version": "2.0"})
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = settings.RSS_TITLE
    SubElement(channel, "link").text = settings.RSS_LINK
    SubElement(channel, "description").text = settings.RSS_DESCRIPTION
    SubElement(channel, "lastBuildDate").text = now_rfc2822
    SubElement(channel, "language").text = "ko-KR"

    for idx, it in enumerate(items_json.get("items", []), start=1):
        item = SubElement(channel, "item")
        title = it.get("title") or f"Untitled {idx}"
        desc  = it.get("description") or ""

        SubElement(item, "title").text = html.escape(title)
        SubElement(item, "description").text = html.escape(desc)
        # 내부용 GUID (발행 전까지 링크 미정)
        guid = f"trend:{title}:{int(datetime.now(timezone.utc).timestamp())}"
        SubElement(item, "guid").text = guid

    return tostring(rss, encoding="utf-8", xml_declaration=True)
