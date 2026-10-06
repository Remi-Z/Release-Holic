# Validation record

Implemented acceptance suites:

- `tests/test_contracts.py`: 29 runnable pure domain cases for precision, timezone requirements, invalid model dates, large string identifiers, snapshot identity, duplicate ingestion, additions/edits/reordering, incomplete indexes, confirmed removals/reappearance, and ISBNs.
- `tests/test_parsers.py`: Kakuyomu scoped indexes, declared coverage, pagination, selector drift, episode-to-work resolution, publisher edition/precision parsing, and optional enrichment outage.
- `tests/test_catalogues.py`: TMDB date/availability interpretation and stable regional identities, TVmaze special numbering, and Bangumi coverage/relationship direction.
- `tests/test_api.py`: real Django database/API tests for duplicate events/imports, postponed release revisions, timezone-equivalent polls, display-timezone day boundaries, separate announcement/release facts, regional overlap, TBA, ambiguous matches, franchise/relationship expansion, correction persistence, adapter failure retention, reviewed claim scope/one-time decisions, fabricated evidence, encrypted credentials, usage limits, invalid model output, and URL/redirect isolation.
- `apps/web/tests/app.spec.ts`: controlled API fixtures in desktop/mobile Playwright projects for partial-date presentation, evidence inspection, ambiguous candidate selection, viewport fit, and mobile navigation. These are browser UI tests, not live ingestion tests.

## GitHub Actions verification

CI verification on 2026-10-06 ([Actions run](https://github.com/Remi-Z/Release-Holic/actions/runs/37505245404)) passed these checks:

- All **68 backend acceptance tests** using Python 3.12 and PostgreSQL 17, including stored HTML parsers and mocked provider integrations.
- Django system checks, `makemigrations --check --dry-run`, and an actual PostgreSQL migration.
- Regenerated JSON Schema/TypeScript contracts with no drift, plus OpenAPI export.
- Client typecheck, SPA build, and PWA build using Node 22.
- All **six Playwright cases** across desktop Chromium and a mobile Chromium viewport.
- All **eight release-policy tests**, covering trusted refs, main builds, version tags, prereleases, invalid tags, and output injection.
- Both Linux AMD64 Docker image builds and the complete packaged stack smoke check: served PWA assets, PostgreSQL migrations, an authenticated API request, RabbitMQ/Celery communication, the scheduler process, and headless Chromium running as the worker's non-root user.

The backend and client install from committed `uv.lock` and `package-lock.json`. Docker builds receive the same locks used by the test jobs.

## Local checks and remaining validation

The implementation environment passed the 29 pure domain cases, Python compilation, generated-contract/schema checks, JSON/TOML parsing, Docker Compose configuration, release-policy tests, and source whitespace checks. Its configured package-registry proxy returned 503 errors, so the full dependency/runtime checks above were executed on GitHub runners.

Live Kakuyomu/publisher/press layouts, NDL resolution, and optional model providers remain unverified. Capture current fixtures through permitted collection and run a bounded extraction test with a configured model. Fixture tests do not establish live source compatibility. Mobile/desktop native packaging also needs the relevant platform toolchains. Check source agreements for the intended deployment.
