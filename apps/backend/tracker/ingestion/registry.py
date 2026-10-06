from django.conf import settings

from .books import NDLAdapter, PublisherAdapter
from .catalogues import BangumiAdapter, TMDBAdapter, TVmazeAdapter
from .contracts import AdapterError
from .kakuyomu import KakuyomuAdapter

ADAPTERS = {adapter.name: adapter for adapter in [TMDBAdapter(), TVmazeAdapter(), BangumiAdapter(), KakuyomuAdapter(), PublisherAdapter("kadokawa"), PublisherAdapter("gagaga"), NDLAdapter()]}


def adapter_for(provider):
    if provider not in ADAPTERS:
        raise AdapterError("Unsupported metadata provider")
    return ADAPTERS[provider]


def resolve(value):
    for adapter in ADAPTERS.values():
        identity = adapter.resolve(value.strip())
        if identity:
            return identity
    raise AdapterError("Use a supported work URL, ISBN, or namespaced provider identifier")


def capabilities():
    policies = {
        "tmdb": "TMDB attribution required. Commercial use requires a commercial agreement; availability credits JustWatch.",
        "tvmaze": "TVmaze data is CC BY-SA; preserve attribution and applicable ShareAlike conditions.",
        "bangumi": "Review Bangumi data-use terms for your deployment.",
        "kakuyomu": "Metadata only. Collection obeys robots rules; review permissions for hosted/commercial aggregation.",
        "kadokawa": "Publisher metadata only; source pages remain linked and attributed.",
        "gagaga": "Published editions and release lists; upcoming titles and dates can change.",
        "ndl": "Bibliographic enrichment. Underlying provider licences and openBD usage conditions apply.",
    }
    return [{"provider": name, "status": "needs_credentials" if name == "tmdb" and not settings.TMDB_TOKEN else "ready", "policy": policies[name]} for name in ADAPTERS]
