# Validation record

Implemented acceptance suites:

- `tests/test_contracts.py`: 29 runnable pure domain cases for precision, timezone requirements, invalid model dates, large string identifiers, snapshot identity, duplicate ingestion, additions/edits/reordering, incomplete indexes, confirmed removals/reappearance, and ISBNs.
- `tests/test_parsers.py`: Kakuyomu scoped indexes, declared coverage, pagination, selector drift, episode-to-work resolution, publisher edition/precision parsing, and optional enrichment outage.
- `tests/test_catalogues.py`: TMDB date/availability interpretation and stable regional identities, TVmaze special numbering, and Bangumi coverage/relationship direction.
- `tests/test_api.py`: real Django database/API tests for duplicate events/imports, postponed release revisions, timezone-equivalent polls, display-timezone day boundaries, separate announcement/release facts, regional overlap, TBA, ambiguous matches, franchise/relationship expansion, correction persistence, adapter failure retention, reviewed claim scope/one-time decisions, fabricated evidence, encrypted credentials, usage limits, invalid model output, and URL/redirect isolation.
- `apps/web/tests/app.spec.ts`: controlled API fixtures in desktop/mobile Playwright projects for partial-date presentation, evidence inspection, ambiguous candidate selection, viewport fit, and mobile navigation. These are browser UI tests, not live ingestion tests.

The pure domain suite passed in the implementation environment using Python 3.12 and Pydantic 2.13.4. The API JSON Schema and TypeScript model contract were generated from the same runtime.

Python compilation passed for the backend, migration, tests, and scripts. The installed Playwright Babel parser accepted the TypeScript scripts and Vue directive/interpolation expressions: **25 files / 519 syntax checks**, with balanced Vue template tags. This checks syntax only; it cannot establish Vue/Quasar types, resolved imports, rendering, or runtime behavior.

The generated JSON Schema validates as Draft 2020-12, all 40 definition references resolve, and regenerating the contracts produces no changes. Static comparison confirms that the initial migration includes the field names from all 20 models; this does not replace Django's migration checks. `docker compose config --quiet`, JSON/TOML parsing, and source whitespace checks also pass. No application containers were started.

Requests to both PyPI and npm failed through the configured proxy with **503 Service Unavailable**. Django, Scrapy, Parsel, Quasar, and Vue dependencies therefore could not be installed. The API/database suite, parser suite, typecheck/build, browser tests, container runtime, and native packaging remain unexecuted. The initial migration is supplied, but `makemigrations --check` and an actual database migration still need to run.

Before considering the application production-verified, execute the README check commands, commit resolved lockfiles, boot the complete stack, and capture current Kakuyomu/publisher/press fixtures from permitted live collection. Verify source terms for the intended deployment. Optional local/hosted model providers also need a bounded real extraction test with a configured model.
