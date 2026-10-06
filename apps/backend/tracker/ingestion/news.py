import hashlib
import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import feedparser
import trafilatura
from parsel import Selector

from .contracts import AdapterError, SourceEvent, parse_release_time
from .http import get_bytes, safe_url
from .kakuyomu import clean

PRESS_PAGES = {
    "apple": "https://www.apple.com/tv-pr/news/",
    "netflix": "https://media.netflix.com/en/press-releases",
    "disney": "https://press.disneyplus.com/news",
}


def article(url):
    from .scrapy_runner import fetch_html

    html = fetch_html(safe_url(url))
    extracted = trafilatura.extract(html, output_format="json", with_metadata=True, include_comments=False)
    import json

    value = json.loads(extracted) if extracted else {}
    text = value.get("text", "")
    if not text:
        raise AdapterError("No article text could be extracted")
    publication = None
    if value.get("date"):
        parsed = parse_release_time(value["date"])
        publication = parsed.timestamp  # Date-only source publications stay date-only in metadata.
    return {"title": value.get("title") or urlsplit(url).hostname, "text": text[:30000], "published_at": publication, "publication_date": value.get("date", ""), "url": url}


def feed_entries(url, *, source_kind="rss", work=None):
    if source_kind in PRESS_PAGES:
        from .scrapy_runner import fetch_html

        selector = Selector(text=fetch_html(PRESS_PAGES[source_kind]))
        entries = []
        for anchor in selector.css('a[href*="/news/"], a[href*="/press-release"], a[href*="/pressrelease"], a[href*="/news-and-updates/"]'):
            title = clean(" ".join(anchor.xpath(".//text()").getall()))
            link = urljoin(PRESS_PAGES[source_kind], anchor.attrib.get("href", ""))
            if title and work and matches_work(title, work):
                entries.append({"id": link, "title": title, "url": link, "text": title, "published_at": None})
        return list({r['id']: r for r in entries}.values())[:30]
    feed = feedparser.parse(get_bytes(safe_url(url)))
    if feed.bozo and not feed.entries:
        raise AdapterError("Source did not return a readable RSS or Atom feed")
    entries = []
    for entry in feed.entries[:50]:
        link = entry.get("link", "")
        if not link:
            continue
        safe_url(link)
        published = entry.get("published_parsed")
        publication = datetime(*published[:6], tzinfo=timezone.utc) if published else None
        text = clean(" ".join(Selector(text=entry.get("summary") or entry.get("title", "")).xpath("//text()").getall()))
        title = entry.get("title", "Untitled update")
        if source_kind == "youtube" and work and not matches_work(title + " " + text, work):
            continue
        entries.append({"id": str(entry.get("id") or link), "title": title[:1000], "url": link, "text": text[:12000], "published_at": publication})
    return entries


def matches_work(text, work):
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return any(unicodedata.normalize("NFKC", title).casefold() in normalized for title in [work.title, work.original_title, *work.aliases] if len(title) >= 3)


def suggested_event(entry, *, source_kind="rss"):
    title = entry['title']
    key = hashlib.sha256(entry['id'].encode()).hexdigest()[:32]
    pv = source_kind == "youtube" or bool(re.search(r"\b(?:PV|trailer|teaser)\b|予告|ＰＶ", title, re.I))
    release = parse_release_time(entry['published_at'].isoformat()) if pv and entry['published_at'] else parse_release_time(None)
    return SourceEvent(external_key=f"news:{key}", kind="pv" if pv else "announcement", title=title, summary=entry['text'][:2000], release=release, url=entry['url'], original_text=entry['text'], published_at=entry['published_at'], verification="unverified", lifecycle="released" if pv else "announced", locator="feed entry / source article")
