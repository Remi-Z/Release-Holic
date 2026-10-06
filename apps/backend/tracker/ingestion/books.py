import json
import re
from urllib.parse import urlencode, urljoin, urlsplit

from parsel import Selector

from .contracts import AdapterError, Candidate, Identity, Metadata, Snapshot, SourceEdition, SourceEvent, diff_snapshots, parse_release_time
from .http import get_bytes, get_json, identifier
from .identifiers import normalize_isbn, shogakukan_product_id
from .kakuyomu import clean, japanese_date


def parse_product(html, url, provider):
    selector = Selector(text=html)
    root = selector.css("main, #main, #contents")[:1] or selector
    book = {}
    for raw in selector.css('script[type="application/ld+json"]::text').getall():
        try:
            nodes = json.loads(raw)
            nodes = nodes if isinstance(nodes, list) else nodes.get("@graph", [nodes])
            for node in nodes:
                types = node.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if set(types) & {"Book", "Product"}:
                    book = node
                    break
        except (ValueError, TypeError, AttributeError):
            continue
    title = clean(book.get("name") or " ".join(root.css("h1")[:1].xpath('.//text()').getall()))
    if not title:
        raise AdapterError("Publisher product title missing; parser may need updating")
    text = clean(" ".join(root.xpath(".//text()[not(ancestor::script) and not(ancestor::style)]").getall()))
    isbn_match = re.search(r"ISBN[^0-9]*(97[89][0-9\- ]{10,20})", text, re.I)
    isbn = book.get("isbn") or (isbn_match[1] if isbn_match else "")
    isbn = normalize_isbn(isbn) if isbn else ""
    release = parse_release_time(book.get("datePublished") or book.get("releaseDate"))
    if release.precision == "unknown":
        match = re.search(r"(?:発売日|発売予定日|刊行日)[：: ]*([0-9]{4}年[0-9]{1,2}月[0-9]{1,2}日)", text)
        if match:
            release = japanese_date(match[1])
    authors = book.get("author") or []
    authors = authors if isinstance(authors, list) else [authors]
    creators = [a.get("name", "") if isinstance(a, dict) else str(a) for a in authors]
    if not creators:
        creators = [clean(x) for x in root.css('[itemprop="author"]::text, .author::text').getall()]
    publisher = book.get("publisher") or {}
    publisher = publisher.get("name", "") if isinstance(publisher, dict) else str(publisher)
    product_id = urlsplit(url).path.rstrip("/").split("/")[-1]
    volume = re.search(r"(?:第\s*)?([0-9０-９]+\s*巻|上|下|前編|後編|外伝|短編集|番外編|side stor(?:y|ies))\s*$", title, re.I)
    volume_label = str(book.get("bookEdition") or (volume[1] if volume else ""))
    book_format = str(book.get("bookFormat", ""))
    edition_format = "ebook" if "ebook" in book_format.casefold() else "audiobook" if "audiobook" in book_format.casefold() else "print"
    edition = SourceEdition(product_id=product_id, isbn=isbn, title=title, volume_label=volume_label, format=edition_format, language=book.get('inLanguage') or 'ja', publisher=publisher or ("KADOKAWA" if provider == "kadokawa" else "Shogakukan"), release=release, url=url)
    return Snapshot(metadata=Metadata(provider=provider, namespace="product", external_id=product_id, title=title, original_title=title, kind="light_novel", creators=[x for x in creators if x], language=edition.language, url=url, extra={"record_scope": "published volume; link to its series through catalogue curation"}), editions=[edition], events=[SourceEvent(external_key=f"volume:{product_id}:{edition.format}:{edition.language}", kind="volume_release", title=title, release=release, region="JP", language=edition.language, verification="reported", url=url, product_id=product_id, locator="Book.datePublished / publisher release field")])


def parse_release_listing(html, base_url, provider):
    selector = Selector(text=html)
    if provider == "kadokawa":
        records = []
        for anchor in selector.css('a[href*="/product/"]'):
            url = urljoin(base_url, anchor.attrib.get("href", ""))
            title = clean(" ".join(anchor.xpath(".//text()").getall()))
            if title and re.search(r"/product/[A-Za-z0-9_-]+/?$", urlsplit(url).path):
                records.append({"title": title, "url": url})
        return list({r['url']: r for r in records}.values())
    # Gagaga listings sometimes omit the year and ISBN. Preserve that uncertainty.
    records = []
    for heading in selector.css("h3"):
        title = clean(" ".join(heading.xpath(".//text()").getall()))
        if not title:
            continue
        siblings = heading.xpath("following-sibling::*[position() <= 3]")
        text = clean(" ".join(siblings.xpath(".//text()").getall()))
        match = re.search(r"ISBN\s*(97[89][0-9\-]{10,17})", text)
        author = re.search(r"著[：:]\s*(.+?)(?:イラスト|ISBN|$)", text)
        records.append({"title": title, "url": base_url, "isbn": normalize_isbn(match[1]) if match else "", "creators": [clean(author[1])] if author else []})
    return records


class PublisherAdapter:
    diff = staticmethod(diff_snapshots)
    def __init__(self, name):
        self.name = name

    def resolve(self, value):
        if self.name == "kadokawa":
            match = re.fullmatch(r"https://(?:www\.)?kadokawa\.co\.jp/product/([A-Za-z0-9_-]+)/?", value)
        else:
            match = re.fullmatch(r"https://www\.shogakukan\.co\.jp/books/([A-Za-z0-9_-]+)/?", value)
        if match:
            return Identity(provider=self.name, namespace="product", external_id=match[1])
        match = re.fullmatch(rf"{self.name}:product:([A-Za-z0-9_-]+)", value)
        return Identity(provider=self.name, namespace="product", external_id=match[1]) if match else None

    def search(self, query, author=""):
        from .scrapy_runner import fetch_html

        url = f"https://www.kadokawa.co.jp/product/search/?{urlencode({'kw': query + ' ' + author})}" if self.name == "kadokawa" else "https://gagagabunko.jp/release/index.html"
        rows = parse_release_listing(fetch_html(url), url, self.name)
        output = []
        for row in rows:
            if self.name == "gagaga" and query and query.casefold() not in row['title'].casefold():
                continue
            product_id = urlsplit(row['url']).path.rstrip("/").split("/")[-1]
            if self.name == "gagaga":
                if not row.get("isbn"):
                    continue
                # Shogakukan's 8-digit product key drops 9784 and the ISBN checksum.
                product_id = shogakukan_product_id(row['isbn'])
                row['url'] = f"https://www.shogakukan.co.jp/books/{product_id}"
            if author and not any(author.casefold() in creator.casefold() for creator in row.get('creators', [])) and self.name == 'gagaga':
                continue
            output.append(Candidate(provider=self.name, namespace="product", external_id=product_id, title=row['title'], creators=row.get("creators", []), kind="light_novel", url=row['url']))
        return output[:20]

    def fetch_snapshot(self, identity):
        from .scrapy_runner import fetch_html

        source_id = identifier(identity.external_id, r"[A-Za-z0-9_-]+")
        url = f"https://www.kadokawa.co.jp/product/{source_id}/" if self.name == "kadokawa" else f"https://www.shogakukan.co.jp/books/{source_id}"
        snapshot = parse_product(fetch_html(url), url, self.name)
        for edition in snapshot.editions:
            if edition.isbn:
                try:
                    enrichment = openbd_lookup(edition.isbn)
                    if enrichment:
                        snapshot.metadata.extra["openbd"] = enrichment
                        if not snapshot.metadata.creators and enrichment.get('author'):
                            snapshot.metadata.creators = [enrichment['author']]
                except AdapterError:
                    snapshot.diagnostics.append("openBD enrichment unavailable; publisher metadata retained")
        return snapshot


def openbd_lookup(isbn):
    result = get_json(f"https://api.openbd.jp/v1/get?isbn={normalize_isbn(isbn)}")
    return result[0].get("summary", {}) if result and result[0] else None


class NDLAdapter:
    name = "ndl"
    diff = staticmethod(diff_snapshots)

    def resolve(self, value):
        match = re.fullmatch(r"https://ndlsearch\.ndl\.go\.jp/(?:en/)?books/([A-Za-z0-9_-]+)/?", value)
        if match:
            return Identity(provider=self.name, namespace="book", external_id=match[1])
        match = re.fullmatch(r"(?:isbn:)?([0-9Xx-]{10,20})", value)
        if match:
            try:
                return Identity(provider=self.name, namespace="isbn", external_id=normalize_isbn(match[1]))
            except AdapterError:
                return None
        match = re.fullmatch(r"ndl:book:([A-Za-z0-9_-]+)", value)
        return Identity(provider=self.name, namespace="book", external_id=match[1]) if match else None

    def search(self, query, author=""):
        escaped = query.replace('"', '').replace('\\', '')
        cql = f'title="{escaped}"' if escaped else ''
        if author:
            cql += (' AND ' if cql else '') + f'creator="{author.replace(chr(34), "")}"'
        return self._search(cql)

    def _search(self, cql):
        url = "https://ndlsearch.ndl.go.jp/api/sru?" + urlencode({"operation": "searchRetrieve", "version": "1.2", "recordSchema": "dcndl", "maximumRecords": 20, "query": cql})
        selector = Selector(text=get_bytes(url).decode("utf-8"), type="xml")
        selector.remove_namespaces()
        output = []
        for record in selector.xpath("//recordData"):
            title = clean(record.xpath(".//title/text()").get())
            about = record.xpath(".//@about").get() or ""
            source_id = about.rstrip("/").split("/")[-1]
            if title and source_id and re.fullmatch(r"[A-Za-z0-9_-]+", source_id):
                output.append(Candidate(provider=self.name, namespace="book", external_id=source_id, title=title, kind="light_novel", creators=record.xpath(".//creator//name/text() | .//creator/text()").getall(), url=f"https://ndlsearch.ndl.go.jp/books/{source_id}"))
        return output

    def fetch_snapshot(self, identity):
        source_id = identifier(identity.external_id, r"[A-Za-z0-9_-]+")
        if identity.namespace == "isbn":
            result = openbd_lookup(source_id)
            if not result:
                raise AdapterError("No openBD record for this ISBN; search by title or author through NDL")
            url = f"https://openbd.jp/"
            value = str(result.get('pubdate') or '')
            release = parse_release_time(value)
            if re.fullmatch(r"[0-9]{6}", value):
                release = parse_release_time(f"{value[:4]}-{value[4:6]}")
            elif re.fullmatch(r"[0-9]{8}", value):
                release = parse_release_time(f"{value[:4]}-{value[4:6]}-{value[6:]}")
            edition = SourceEdition(product_id=source_id, isbn=source_id, title=result['title'], publisher=result.get("publisher", ""), release=release, url=url)
            return Snapshot(metadata=Metadata(provider=self.name, namespace="isbn", external_id=source_id, title=result['title'], kind="light_novel", creators=[result['author']] if result.get("author") else [], language="ja", url=url, extra={"attribution": "openBD"}), editions=[edition], events=[SourceEvent(external_key=f"volume:{source_id}", kind="volume_release", title=result['title'], release=release, region="JP", url=url, product_id=source_id, locator="openBD.summary.pubdate")])
        records = self._search(f'rdf:about="https://ndlsearch.ndl.go.jp/books/{source_id}"')
        if not records:
            # Match by NDL identifier where the SRU server does not index rdf:about.
            records = self._search(f'identifier="{source_id}"')
        candidate = next((r for r in records if r.external_id == source_id), None)
        if not candidate:
            raise AdapterError("NDL record could not be resolved")
        return Snapshot(metadata=Metadata(**candidate.model_dump(), language="ja", extra={"attribution": "NDL Search; preserve the underlying record's reuse conditions"}))
