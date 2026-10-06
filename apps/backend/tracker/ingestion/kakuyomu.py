import re
import unicodedata
from datetime import datetime
from urllib.parse import quote, urljoin, urlsplit
from zoneinfo import ZoneInfo

from parsel import Selector

from .contracts import AdapterError, Candidate, Identity, Metadata, Snapshot, SourceUnit, diff_snapshots, parse_release_time
from .http import identifier


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def japanese_date(value: str):
    match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", value)
    return parse_release_time("-".join([match[1], match[2].zfill(2), match[3].zfill(2)])) if match else parse_release_time(None)


def parse_kakuyomu(html: str, work_id: str, *, url: str | None = None) -> Snapshot:
    work_id = identifier(work_id)
    canonical = f"https://kakuyomu.jp/works/{work_id}"
    selector = Selector(text=html)
    title = clean("".join(selector.css("#workTitle, h1")[:1].xpath(".//text()").getall()))
    if not title:
        raise AdapterError("Work title missing: Kakuyomu layout may have changed")
    canonical_link = selector.css('link[rel="canonical"]::attr(href)').get()
    if canonical_link and urlsplit(canonical_link).path.rstrip("/") != f"/works/{work_id}":
        raise AdapterError("Kakuyomu returned a different work")
    author_node = selector.css('#workAuthor-activityName, #workAuthor a[href^="/users/"], header a[href^="/users/"]')[:1]
    if not author_node:
        author_node = selector.xpath('(//h1/following::a[starts-with(@href,"/users/")])[1]')
    author = clean("".join(author_node.xpath(".//text()").getall()))
    author_url = author_node.css("::attr(href)").get() or author_node.css("a::attr(href)").get() or ""
    count_nodes = selector.css("#workState, #workStatus, [data-testid='work-status'], .widget-workStatus")
    state_text = clean(" ".join(count_nodes.xpath(".//text()").getall()))
    status = "completed" if "完結済" in state_text else "ongoing" if "連載中" in state_text else "unknown"
    # Scope to the work's index. Reviews/recommendations must never become chapters.
    toc = selector.css("#table-of-contents, #workEpisodes, .widget-toc, [data-testid='table-of-contents']")
    if not toc:
        toc = selector
    units = []
    seen = set()
    for anchor in toc.css(f'a[href*="/works/{work_id}/episodes/"]'):
        href = anchor.attrib.get("href", "")
        match = re.fullmatch(rf"/works/{work_id}/episodes/([0-9]+)/?", urlsplit(urljoin(canonical, href)).path)
        if not match or match[1] in seen:
            continue
        seen.add(match[1])
        chapter_title = clean("".join(anchor.css(".widget-toc-episode-titleLabel::text, [data-testid='episode-title']::text").getall()))
        if not chapter_title:
            chapter_title = clean(" ".join(anchor.xpath(".//text()[not(ancestor::time)]").getall()))
        if not chapter_title:
            raise AdapterError("Chapter title missing")
        row = anchor.xpath("ancestor::li[1]")
        timestamp = anchor.css("time::attr(datetime)").get() or row.css("time::attr(datetime)").get()
        date_text = " ".join(anchor.css("time::text").getall() + row.css("time::text").getall())
        if timestamp:
            if "T" in timestamp:
                stamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
                release = parse_release_time(stamp.isoformat())
                release.timezone = "Asia/Tokyo"
            else:
                release = parse_release_time(timestamp)
        else:
            release = japanese_date(date_text)
        units.append(SourceUnit(external_id=match[1], kind="chapter", title=chapter_title, ordinal=len(units), url=urljoin(canonical, href), release=release, published_at=release.timestamp))
    # A recommendation's chapter count must never establish this work's coverage.
    count_text = state_text
    expected = re.search(r"全\s*([0-9,]+)\s*話", count_text)
    expected_count = int(expected[1].replace(",", "")) if expected else None
    pending = bool(toc.css('a[rel="next"], button[data-load-more]:not([disabled]), [data-has-more="true"]'))
    complete = expected_count is not None and expected_count == len(units) and not pending
    diagnostics = []
    if expected_count is None:
        diagnostics.append("Chapter count unavailable; completeness cannot be established")
    elif expected_count != len(units):
        diagnostics.append(f"Chapter index contains {len(units)} of {expected_count} declared chapters")
    if pending:
        diagnostics.append("More chapter-index pages remain")
    publication_links = sorted({urljoin(canonical, href) for href in selector.css('a[href*="/publication/entry/"]::attr(href)').getall()})
    # Schedules remain text expectations, never a promised chapter release.
    expectation = clean(" ".join(selector.css('#workNextEpisode, .widget-workSchedule, [data-testid="update-schedule"]').xpath(".//text()").getall()))
    return Snapshot(metadata=Metadata(provider="kakuyomu", namespace="work", external_id=work_id, title=title, original_title=title, kind="web_novel", creators=[author] if author else [], language="ja", status=status, url=canonical, extra={"author_url": urljoin(canonical, author_url) if author_url else "", "publication_links": publication_links, "expected_update_schedule": expectation, "declared_chapter_count": expected_count}), units=units, complete=complete, diagnostics=diagnostics)


class KakuyomuAdapter:
    name = "kakuyomu"
    diff = staticmethod(diff_snapshots)

    def resolve(self, value: str):
        match = re.fullmatch(r"https://kakuyomu\.jp/works/([0-9]+)(?:/episodes/[0-9]+)?/?(?:\?[^#]*)?", value)
        if match:
            return Identity(provider=self.name, namespace="work", external_id=match[1])
        match = re.fullmatch(r"kakuyomu:(?:work:)?([0-9]+)", value)
        return Identity(provider=self.name, namespace="work", external_id=match[1]) if match else None

    def search(self, query: str, author: str = ""):
        from .scrapy_runner import fetch_html

        html = fetch_html(f"https://kakuyomu.jp/search?q={quote(unicodedata.normalize('NFKC', query + ' ' + author).strip())}")
        selector = Selector(text=html)
        candidates = []
        seen = set()
        for anchor in selector.css('.widget-workCard-title a, .widget-workCard-titleLabel, a[data-testid="work-title"]'):
            href = anchor.attrib.get("href", "")
            match = re.fullmatch(r"/works/([0-9]+)", urlsplit(href).path)
            title = clean(" ".join(anchor.xpath(".//text()").getall()))
            if match and title and match[1] not in seen:
                seen.add(match[1])
                candidates.append(Candidate(provider=self.name, namespace="work", external_id=match[1], title=title, kind="web_novel", url=urljoin("https://kakuyomu.jp", href)))
        return candidates[:20]

    def fetch_snapshot(self, identity: Identity):
        from .scrapy_runner import fetch_html

        url = f"https://kakuyomu.jp/works/{identifier(identity.external_id)}"
        html = fetch_html(url)
        snapshot = parse_kakuyomu(html, identity.external_id)
        combined = {unit.external_id: unit for unit in snapshot.units}
        seen_pages = {url}
        # Ordinary index pagination is cheaper than launching a browser. Only follow
        # pagination on this work's index, never episode pages or recommended works.
        for _ in range(20):
            selector = Selector(text=html)
            next_link = selector.css('#table-of-contents a[rel="next"]::attr(href), .widget-toc a[rel="next"]::attr(href), #workEpisodes a[rel="next"]::attr(href)').get()
            if not next_link:
                break
            next_url = urljoin(url, next_link)
            parsed = urlsplit(next_url)
            if parsed.scheme != 'https' or parsed.hostname != 'kakuyomu.jp' or parsed.path.rstrip('/') != f'/works/{identity.external_id}' or next_url in seen_pages:
                raise AdapterError("Chapter-index pagination was unsafe or repeated")
            seen_pages.add(next_url)
            html = fetch_html(next_url)
            page = parse_kakuyomu(html, identity.external_id)
            combined.update({unit.external_id: unit for unit in page.units})
            snapshot.units = [unit.model_copy(update={'ordinal': ordinal}) for ordinal, unit in enumerate(combined.values())]
            expected = snapshot.metadata.extra.get('declared_chapter_count')
            snapshot.complete = expected is not None and len(combined) == expected and not Selector(text=html).css('#table-of-contents a[rel="next"], .widget-toc a[rel="next"], #workEpisodes a[rel="next"], button[data-load-more]:not([disabled]), [data-has-more="true"]')
            if snapshot.complete:
                snapshot.diagnostics = []
                break
        if not snapshot.complete:
            snapshot = parse_kakuyomu(fetch_html(url, render=True), identity.external_id)
        return snapshot
