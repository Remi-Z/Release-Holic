import ipaddress
import re
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from django.conf import settings

from .contracts import AdapterError, TransientAdapterError

SOURCE_HOSTS = {
    "api.themoviedb.org", "www.themoviedb.org", "api.tvmaze.com", "www.tvmaze.com",
    "api.bgm.tv", "bgm.tv", "bangumi.tv", "kakuyomu.jp", "www.kadokawa.co.jp",
    "kadokawa.co.jp", "gagagabunko.jp", "www.shogakukan.co.jp", "ndlsearch.ndl.go.jp",
    "api.openbd.jp", "openbd.jp", "www.youtube.com", "youtube.com",
    "www.apple.com", "media.netflix.com", "about.netflix.com", "press.disneyplus.com",
    "press.disneyplus.disney.com", "thewaltdisneycompany.com", "www.disneyplus.com",
}
MODEL_HOSTS = {"api.openai.com", "api.anthropic.com", "generativelanguage.googleapis.com", "openrouter.ai"}


def safe_url(value: str, *, model: bool = False) -> str:
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise AdapterError("Invalid source URL") from exc
    if parsed.username or parsed.password or not host or parsed.fragment:
        raise AdapterError("Use a canonical URL without credentials or fragments")
    if model and parsed.query:
        raise AdapterError("Use a model base endpoint without query parameters; enter credentials separately")
    if not model and host == 'kakuyomu.jp' and re.search(r'/episodes/[0-9]+(?:[/.]|$)', unquote(parsed.path)):
        raise AdapterError("Kakuyomu chapter bodies are outside collection scope; use the work metadata URL")
    local = host in {"localhost", "127.0.0.1", "::1"}
    if model and local and settings.ALLOW_LOCAL_MODELS:
        if parsed.scheme not in {"http", "https"}:
            raise AdapterError("Unsupported model protocol")
        return value
    if parsed.scheme != "https" or port not in {None, 443}:
        raise AdapterError("Public sources must use HTTPS on the standard port")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise AdapterError("IP-address source URLs are not supported")
    allowed = (MODEL_HOSTS | settings.ALLOWED_MODEL_HOSTS) if model else (SOURCE_HOSTS | settings.ALLOWED_SOURCE_HOSTS)
    if host not in allowed:
        raise AdapterError("This source host is not enabled on this server")
    return value


def get_bytes(url: str, *, headers: dict | None = None, max_bytes: int = 3_000_000) -> bytes:
    current = safe_url(url)
    request_headers = {"User-Agent": settings.USER_AGENT, **(headers or {})}
    original_host = urlsplit(current).hostname
    try:
        with httpx.Client(timeout=20, follow_redirects=False) as client:
            for _ in range(5):
                with client.stream("GET", current, headers=request_headers) as response:
                    if response.is_redirect:
                        current = safe_url(urljoin(current, response.headers.get("location", "")))
                        if urlsplit(current).hostname != original_host:
                            request_headers = {"User-Agent": settings.USER_AGENT}
                        continue
                    response.raise_for_status()
                    output = bytearray()
                    for chunk in response.iter_bytes():
                        output.extend(chunk)
                        if len(output) > max_bytes:
                            raise AdapterError("Source response exceeded the size limit")
                    return bytes(output)
    except httpx.HTTPStatusError as exc:
        error = TransientAdapterError if exc.response.status_code == 429 or exc.response.status_code >= 500 else AdapterError
        raise error(f"Source returned HTTP {exc.response.status_code}; retry later") from exc
    except httpx.HTTPError as exc:
        raise TransientAdapterError("Source could not be reached; last successful data is retained") from exc
    raise AdapterError("Too many source redirects")


def get_json(url: str, *, headers: dict | None = None):
    import json

    try:
        return json.loads(get_bytes(url, headers=headers))
    except (ValueError, UnicodeError) as exc:
        raise AdapterError("Source returned invalid JSON") from exc


def identifier(value: str, pattern: str = r"[0-9]+") -> str:
    if not re.fullmatch(pattern, value):
        raise AdapterError("Invalid provider identifier")
    return value
