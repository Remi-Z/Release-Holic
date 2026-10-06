"""Run each crawl in a fresh process; a Twisted reactor cannot be restarted in Celery."""
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit

from .contracts import AdapterError, TransientAdapterError
from .http import safe_url


async def abort_browser_request(request):
    if request.resource_type in {"image", "media", "font"}:
        return True
    try:
        safe_url(request.url)
        return False
    except AdapterError:
        return True


class SafeRequests:
    def process_request(self, request, spider):
        # Redirects and robots requests pass this gate before network access.
        safe_url(request.url)


def fetch_html(url: str, *, render: bool = False) -> str:
    safe_url(url)
    try:
        result = subprocess.run([sys.executable, "-m", "tracker.ingestion.scrapy_runner", url, "render" if render else "http"], capture_output=True, text=True, timeout=100, check=False)
        payload = json.loads(result.stdout)
    except subprocess.TimeoutExpired as exc:
        raise TransientAdapterError("Website collection timed out") from exc
    except ValueError as exc:
        raise AdapterError("Website collection returned invalid output") from exc
    if result.returncode or payload.get("error"):
        error = TransientAdapterError if payload.get("retryable") else AdapterError
        raise error(payload.get("error", "Website collection failed"))
    return payload["html"]


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    import scrapy
    from scrapy.crawler import CrawlerProcess
    from scrapy.exceptions import IgnoreRequest
    from scrapy_playwright.page import PageMethod
    from django.conf import settings

    url, mode = safe_url(sys.argv[1]), sys.argv[2]
    result = {"error": "No valid page returned. Robots rules, permissions, or source availability may prevent collection."}

    class MetadataSpider(scrapy.Spider):
        name = "metadata"

        async def start(self):
            meta = {}
            if mode == "render":
                meta = {"playwright": True, "playwright_page_methods": [PageMethod("wait_for_timeout", 500), PageMethod("evaluate", "async () => { for (let i=0;i<30;i++) { const buttons=[...document.querySelectorAll('button')]; const next=buttons.find(b=>/もっと見る|続きを表示/.test(b.textContent) && !b.disabled && b.closest('#table-of-contents, .widget-toc, #workEpisodes, [data-testid=table-of-contents]')); if (!next) break; next.click(); await new Promise(r=>setTimeout(r,300)); } }")]}
            yield scrapy.Request(url, callback=self.parse, errback=self.failed, meta=meta)

        def parse(self, response):
            safe_url(response.url)
            result.clear()
            result["html"] = response.text

        def failed(self, failure):
            if isinstance(failure.value, AdapterError):
                result['error'], result['retryable'] = str(failure.value), False
                return
            result["error"] = "Website could not be collected; last successful state is retained"
            response = getattr(failure.value, 'response', None)
            result['retryable'] = not isinstance(failure.value, IgnoreRequest) and (response is None or response.status == 429 or response.status >= 500)

    launch_options = {"headless": True}
    proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
    if proxy:
        parsed_proxy = urlsplit(proxy)
        launch_options['proxy'] = {'server': f'{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port or 8080}'}
        if parsed_proxy.username:
            launch_options['proxy'].update(username=parsed_proxy.username, password=parsed_proxy.password or '')
    process = CrawlerProcess({
        "USER_AGENT": settings.USER_AGENT,
        "ROBOTSTXT_OBEY": True, "COOKIES_ENABLED": False,
        "CONCURRENT_REQUESTS": 1, "DOWNLOAD_DELAY": 2,
        "DOWNLOAD_TIMEOUT": 25, "DOWNLOAD_MAXSIZE": 3_000_000,
        "REDIRECT_ENABLED": True, "REDIRECT_MAX_TIMES": 5, "RETRY_TIMES": 1, "LOG_LEVEL": "ERROR",
        "DOWNLOADER_MIDDLEWARES": {"tracker.ingestion.scrapy_runner.SafeRequests": 50},
        "DOWNLOADER_CLIENTCONTEXTFACTORY": "scrapy.core.downloader.contextfactory.BrowserLikeContextFactory",
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {"https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler", "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler"},
        "PLAYWRIGHT_LAUNCH_OPTIONS": launch_options,
        "PLAYWRIGHT_ABORT_REQUEST": "tracker.ingestion.scrapy_runner.abort_browser_request",
        "PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT": 25000,
    })
    process.crawl(MetadataSpider)
    process.start()
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
