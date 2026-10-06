import hashlib
import re
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from django.conf import settings

from .contracts import AdapterError, Candidate, Identity, Metadata, Snapshot, SourceEvent, SourceRelationship, SourceUnit, diff_snapshots, parse_release_time
from .http import get_json, identifier


def stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


class TMDBAdapter:
    name = "tmdb"
    diff = staticmethod(diff_snapshots)

    def request(self, path):
        if not settings.TMDB_TOKEN:
            raise AdapterError("TMDB requires an operator-configured API read token")
        return get_json(f"https://api.themoviedb.org/3/{path}", headers={"Authorization": f"Bearer {settings.TMDB_TOKEN}"})

    def resolve(self, value):
        match = re.fullmatch(r"(?:https://(?:www\.)?themoviedb\.org/|tmdb:)(movie|tv)[/:]([0-9]+)(?:-[^/?]+)?/?(?:\?[^#]*)?", value)
        return Identity(provider=self.name, namespace=match[1], external_id=match[2]) if match else None

    def search(self, query, author=""):
        results = self.request(f"search/multi?{urlencode({'query': query, 'include_adult': 'false'})}")
        return [Candidate(provider=self.name, namespace=item["media_type"], external_id=str(item["id"]), title=item.get("title") or item.get("name", ""), kind="movie" if item["media_type"] == "movie" else "show", year=(item.get("release_date") or item.get("first_air_date") or "")[:4], url=f"https://www.themoviedb.org/{item['media_type']}/{item['id']}") for item in results.get("results", []) if item.get("media_type") in {"movie", "tv"}][:20]

    def fetch_snapshot(self, identity):
        if identity.namespace not in {"movie", "tv"}:
            raise AdapterError("Unsupported TMDB namespace")
        source_id = identifier(identity.external_id)
        item = self.request(f"{identity.namespace}/{source_id}?append_to_response=external_ids,videos")
        url = f"https://www.themoviedb.org/{identity.namespace}/{source_id}"
        title = item.get("title") or item.get("name")
        if not title:
            raise AdapterError("TMDB returned an invalid catalogue record")
        metadata = Metadata(provider=self.name, namespace=identity.namespace, external_id=source_id, title=title, original_title=item.get("original_title") or item.get("original_name") or title, kind="movie" if identity.namespace == "movie" else "show", summary=item.get("overview") or "", language=item.get("original_language") or "", status=item.get("status") or "", url=url, image_url=f"https://image.tmdb.org/t/p/w342{item['poster_path']}" if item.get("poster_path") else "", extra={"external_ids": item.get("external_ids", {}), "attribution": "TMDB"})
        events = []
        release = item.get("release_date") or item.get("first_air_date")
        if release:
            events.append(SourceEvent(external_key="primary-release", kind="release", title=f"{title} premieres", release=parse_release_time(release), url=url, locator="$.release_date" if identity.namespace == "movie" else "$.first_air_date"))
        if identity.namespace == "movie":
            dates = self.request(f"movie/{source_id}/release_dates")
            metadata.extra['source_payloads'] = {'details': item, 'release_dates': dates}
            labels = {1: "Premiere", 2: "Limited theatrical release", 3: "Theatrical release", 4: "Digital release", 5: "Physical release", 6: "TV release"}
            for region in dates.get("results", []):
                def descriptor(entry):
                    return hashlib.sha256(repr((entry.get('type'), entry.get('iso_639_1'), entry.get('certification'), entry.get('note'))).encode()).hexdigest()[:24]

                counts = Counter(descriptor(entry) for entry in region.get('release_dates', []))
                for entry in region.get("release_dates", []):
                    # TMDB encodes date-only releases as midnight UTC; do not claim an exact time.
                    day = entry.get("release_date", "")[:10]
                    if day:
                        fingerprint = descriptor(entry)
                        suffix = ':' + day if counts[fingerprint] > 1 else ''
                        events.append(SourceEvent(external_key=f"release:{region['iso_3166_1']}:{fingerprint}{suffix}", kind="release", title=f"{title} · {labels.get(entry.get('type'), 'Release')}", release=parse_release_time(day), region=region["iso_3166_1"], language=entry.get("iso_639_1", ""), url=url, locator=f"release_dates / country={region['iso_3166_1']} / type={entry.get('type')}"))
        for video in item.get("videos", {}).get("results", []):
            if video.get("site") == "YouTube" and video.get("type") in {"Trailer", "Teaser"}:
                when = video.get("published_at")
                events.append(SourceEvent(external_key=f"video:{video['id']}", kind="pv", title=video.get("name", "Promotional video"), release=parse_release_time(when), published_at=stamp(when), lifecycle="released", url=f"https://www.youtube.com/watch?v={video['key']}", locator="$.videos.results", verification="reported"))
        providers = self.request(f"{identity.namespace}/{source_id}/watch/providers")
        metadata.extra.setdefault('source_payloads', {'details': item})['watch_providers'] = providers
        now = datetime.now(timezone.utc)
        availability = []
        for country, data in providers.get("results", {}).items():
            for provider in data.get("flatrate", []):
                name = provider.get("provider_name", "")
                availability.append({"region": country, "platform": name})
                events.append(SourceEvent(external_key=f"availability:{country}:{provider['provider_id']}", kind="availability", title=f"First observed available on {name}", summary="Availability observation from TMDB / JustWatch; this is not the original release date.", release=parse_release_time(now.isoformat()), region=country, platform=name, lifecycle="released", url=data.get("link") or url, locator="$.watch.providers"))
        metadata.extra["availability"] = availability
        metadata.extra["availability_attribution"] = "JustWatch"
        return Snapshot(metadata=metadata, events=events)


class TVmazeAdapter:
    name = "tvmaze"
    diff = staticmethod(diff_snapshots)

    def resolve(self, value):
        match = re.fullmatch(r"(?:https://(?:www\.)?tvmaze\.com/shows/|tvmaze:(?:show:)?)([0-9]+)(?:/[^?]*)?(?:\?[^#]*)?", value)
        return Identity(provider=self.name, namespace="show", external_id=match[1]) if match else None

    def search(self, query, author=""):
        results = get_json(f"https://api.tvmaze.com/search/shows?q={quote(query)}")
        return [Candidate(provider=self.name, namespace="show", external_id=str(item['show']['id']), title=item['show']['name'], kind="show", year=(item['show'].get("premiered") or "")[:4], url=item['show']['url']) for item in results][:20]

    def fetch_snapshot(self, identity):
        source_id = identifier(identity.external_id)
        show = get_json(f"https://api.tvmaze.com/shows/{source_id}")
        episodes = get_json(f"https://api.tvmaze.com/shows/{source_id}/episodes?specials=1")
        from parsel import Selector

        channel = show.get("webChannel") or show.get("network") or {}
        country = channel.get("country") or {}
        metadata = Metadata(provider=self.name, namespace="show", external_id=source_id, title=show['name'], kind="show", url=show['url'], language=show.get("language") or "", status=show.get("status") or "", summary=" ".join(Selector(text=show.get("summary") or "").xpath("//text()").getall()), image_url=(show.get("image") or {}).get("medium") or "", extra={"external_ids": show.get("externals", {}), "attribution": "TVmaze · CC BY-SA", "platform": channel.get("name") or "", "source_payloads": {"show": show, "episodes": episodes}})
        units, events = [], []
        for index, episode in enumerate(episodes):
            when = episode.get("airstamp") or episode.get("airdate")
            release = parse_release_time(when)
            season = f"S{episode['season']:02}" if episode.get('season') is not None else 'Season TBA'
            number = f"E{episode['number']:02}" if episode.get('number') is not None else 'Special' if 'special' in episode.get('type', '') else 'Episode number TBA'
            label = f"{season} {number}"
            unit = SourceUnit(external_id=str(episode['id']), kind="episode", title=episode.get("name") or label, label=label, ordinal=index, url=episode['url'], release=release)
            units.append(unit)
            events.append(SourceEvent(external_key=f"episode:{episode['id']}", kind="episode_release", title=f"{label} · {unit.title}", release=release, region=country.get("code", ""), platform=channel.get("name", ""), url=episode['url'], unit_id=unit.external_id, locator="$.episodes[*].airstamp"))
        return Snapshot(metadata=metadata, units=units, events=events)

    def web_schedule(self, day, country=None):
        # Omitted country includes both global and local web channels. Empty means global only.
        params = {"date": day.isoformat()}
        if country is not None:
            params["country"] = country
        return get_json(f"https://api.tvmaze.com/schedule/web?{urlencode(params)}")


class BangumiAdapter:
    name = "bangumi"
    diff = staticmethod(diff_snapshots)

    def request(self, path):
        headers = {"Authorization": f"Bearer {settings.BANGUMI_TOKEN}"} if settings.BANGUMI_TOKEN else None
        return get_json(f"https://api.bgm.tv/v0/{path}", headers=headers)

    def resolve(self, value):
        match = re.fullmatch(r"(?:https://(?:bgm|bangumi)\.tv/subject/|bangumi:(?:subject:)?)([0-9]+)/?", value)
        return Identity(provider=self.name, namespace="subject", external_id=match[1]) if match else None

    def search(self, query, author=""):
        # The legacy search is a public GET endpoint; v0 search uses POST.
        result = get_json(f"https://api.bgm.tv/search/subject/{quote(query)}?type=2&responseGroup=small&max_results=20")
        return [Candidate(provider=self.name, namespace="subject", external_id=str(item['id']), title=item.get("name") or item.get("name_cn"), kind="anime", url=f"https://bgm.tv/subject/{item['id']}") for item in result.get("list", [])]

    def fetch_snapshot(self, identity):
        source_id = identifier(identity.external_id)
        subject = self.request(f"subjects/{source_id}")
        if subject.get("type") not in {1, 2}:
            raise AdapterError("This Bangumi subject is not anime or a book")
        kind = "anime" if subject['type'] == 2 else "light_novel"
        aliases = [subject.get("name_cn", "")] if subject.get("name_cn") else []
        metadata = Metadata(provider=self.name, namespace="subject", external_id=source_id, title=subject['name'], original_title=subject['name'], aliases=aliases, kind=kind, url=f"https://bgm.tv/subject/{source_id}", summary=subject.get("summary") or "", language="ja", image_url=(subject.get("images") or {}).get("medium") or "", extra={"infobox": subject.get("infobox", []), "source_payloads": {"subject": subject, "episode_pages": []}})
        units, events = [], []
        complete = True
        if kind == "anime":
            declared_total = None
            for offset in range(0, 5000, 100):
                page = self.request(f"episodes?subject_id={source_id}&limit=100&offset={offset}")
                metadata.extra['source_payloads']['episode_pages'].append(page)
                data = page.get("data", [])
                if not isinstance(page.get('total'), int) or page['total'] < 0:
                    complete = False
                    break
                declared_total = page['total']
                for episode in data:
                    release = parse_release_time(episode.get("airdate"))
                    label = str(episode.get("sort", episode.get("ep", "")))
                    units.append(SourceUnit(external_id=str(episode['id']), kind="episode", title=episode.get("name") or episode.get("name_cn") or f"Episode {label}", label=label, ordinal=len(units), url=f"https://bgm.tv/ep/{episode['id']}", release=release))
                    events.append(SourceEvent(external_key=f"episode:{episode['id']}", kind="episode_release", title=f"Episode {label} · {units[-1].title}", release=release, region="JP", language="ja", url=units[-1].url, unit_id=units[-1].external_id, locator="$.episodes.data[*].airdate"))
                if len(units) >= declared_total:
                    break
                if not data or offset == 4900:
                    complete = False
                    break
            complete = complete and declared_total is not None and len(units) == declared_total
        relations = self.request(f"subjects/{source_id}/subjects")
        relation_kinds = {"前传": ("sequel_to", False), "续集": ("sequel_to", True), "原作": ("adaptation_of", False), "本篇": ("part_of", False), "外传": ("spinoff_of", True)}
        relationships = [SourceRelationship(target=Identity(provider=self.name, namespace="subject", external_id=str(r['id'])), kind=relation_kinds[r['relation']][0], reverse=relation_kinds[r['relation']][1]) for r in relations if r.get("relation") in relation_kinds]
        metadata.extra["related_subjects"] = relations
        metadata.extra['source_payloads']['relationships'] = relations
        if subject.get("date"):
            events.append(SourceEvent(external_key="primary-release", kind="release", title=f"{metadata.title} releases", release=parse_release_time(subject['date']), region="JP", url=metadata.url, locator="$.date"))
        return Snapshot(metadata=metadata, units=units, events=events, relationships=relationships, complete=complete, diagnostics=[] if complete else ["Episode index was incomplete"])
