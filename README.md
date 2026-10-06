# Release-Holic

[![CI and container releases](https://github.com/Remi-Z/Release-Holic/actions/workflows/checks.yml/badge.svg)](https://github.com/Remi-Z/Release-Holic/actions/workflows/checks.yml)

An evidence-backed timeline for TV series, movies, Japanese anime, web novels, and published light novels. Follow stories, keep private watching/reading progress, inspect source evidence, and review uncertain announcements before adding them to your timeline.

The repository contains a Quasar/Vue/TypeScript client, a Django 5.2 + Django Ninja API, PostgreSQL data models, and independently running Celery ingestion workers and scheduler. RabbitMQ carries jobs; Scrapy collects publisher and Kakuyomu metadata; PydanticAI provides optional bring-your-own-model extraction.

## Start with Docker

```sh
cp -n .env.example .env
# Set DJANGO_SECRET_KEY to a persistent random value in .env.
# Configure TMDB_TOKEN if you want TMDB catalogue and regional availability data.
docker compose up --build -d
docker compose exec api python manage.py createsuperuser
```

Open **http://localhost:8080** and sign in with the account you created. The same server exposes **/api/docs** for the typed API and **/admin/** for catalogue curation. The database migration runs before the API and workers start. Only one scheduler should run.

You can explore the interface with explicitly fictional data:

```sh
docker compose exec api python manage.py seed_demo --user YOUR_USERNAME
```

This creates seven labelled demo stories, account-private illustrative events, and a review example. It creates no password and makes no factual release claims.

The default configuration is for a personal server on local HTTP. For a public HTTPS deployment, set `DEBUG=0`, configure `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`, and place the web container behind your HTTPS reverse proxy. Keep the Django secret and optional `MODEL_ENCRYPTION_KEY` stable so saved model credentials remain decryptable.

## Prebuilt images and automatic releases

GitHub Actions tests the backend against PostgreSQL, builds the SPA/PWA, runs desktop/mobile browser checks, then starts the complete container stack before publishing two Linux AMD64 images:

- `ghcr.io/remi-z/release-holic-backend` — API, ingestion worker, and scheduler.
- `ghcr.io/remi-z/release-holic-web` — the built PWA and Nginx proxy.

Successful `main` builds publish `:main` and `:sha-COMMIT`. A tag such as `v0.1.0` publishes `:v0.1.0`, `:0.1.0`, `:latest`, and a GitHub Release with image digests. Prerelease tags such as `v0.1.0-rc.1` never update `:latest`. Pull requests run validation without publishing. The workflow uses its repository-scoped `GITHUB_TOKEN`; no registry secret needs to be added.

To run the prebuilt images:

```sh
cp -n .env.example .env
# Set your persistent secret and desired IMAGE_TAG in .env.
docker compose -f compose.images.yaml pull
docker compose -f compose.images.yaml up -d
docker compose -f compose.images.yaml exec api python manage.py createsuperuser
```

New GHCR packages start private; use an account with package read access to log in, or set the packages public in GitHub for anonymous pulls. See [container release instructions](docs/container-releases.md) for version tags, registry access, and deployment updates.

## Local development

Use Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22.13+, and Docker for PostgreSQL/RabbitMQ.

```sh
cp -n .env.example .env
docker compose up -d db rabbitmq
cd apps/backend
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python -m playwright install chromium
uv run python manage.py runserver 127.0.0.1:8000
```

In separate terminals, from `apps/backend`:

```sh
uv run celery -A config worker --loglevel=INFO --concurrency=2
uv run celery -A config beat --loglevel=INFO --schedule=/tmp/release-holic-beat
```

From `apps/web`:

```sh
ELECTRON_SKIP_BINARY_DOWNLOAD=1 npm ci
npm run dev
```

Open **http://localhost:9000**. The dev server proxies the API and Django administration. Monitoring continues on the worker even when no client is open.

## What is implemented

- A responsive desktop timeline/mobile agenda with virtualized event cards, separate TBA items, date-basis selection, regional/platform/media/verification/progress filters, and private saved views.
- A catalogue with application-owned UUIDs, namespaced external IDs, creators, franchises, works, source-numbered chapters/episodes, distinct book editions, and typed relationships.
- Separate documents, claims, events, and revisions. Announcement publication and projected release are separate calendar facts. Year/month windows retain their precision, changes retain earlier values, and streaming availability is labelled as an observation.
- URL/identifier resolution and title/author candidate search. Ambiguous results require an explicit selection; Japanese matching normalizes text while preserving display text.
- Private follows, related-work expansion, progress, model settings, feed subscriptions, source submissions, and review decisions. Canonical catalogue curation requires a staff account. Curated titles/aliases/franchise assignments and validated event corrections survive refreshes, and event corrections retain revision history.
- TMDB, TVmaze, Bangumi, Kakuyomu, KADOKAWA, Gagaga/Shogakukan, NDL Search, and openBD clients/parsers, plus official Apple/Netflix/Disney press monitors, RSS/Atom, and YouTube channel feeds.
- A Kakuyomu metadata/chapter-index adapter with static pagination, optional browser rendering, completeness checks, change classification, last-good-state preservation, and removal confirmation across two complete snapshots. Novel bodies are never collected; author schedules remain expectations.
- PydanticAI extraction for OpenAI-compatible/OpenAI, Anthropic, Google, and Ollama endpoints. Credentials are encrypted and omitted from responses; input/output/daily limits are enforced. Extracted claims need exact supporting excerpts and enter the account's review queue.
- Celery retries for transient catalogue outages/rate limits, per-source leases, source health, job status, migration/seed commands, container services, generated API model types, and CI acceptance checks.
- PWA configuration and Electron/Capacitor source configurations using the shared client. Native binaries still require their platform toolchains and packaging validation.

## Sources and models

Configure `TMDB_TOKEN` as an API **read access token**. Other initial catalogue sources use public endpoints; `BANGUMI_TOKEN` is optional. Add exact domains to `ALLOWED_SOURCE_HOSTS` for additional RSS/article hosts. Browser rendering also restricts request hosts, so a site's script CDN may need an explicit entry after investigation.

In **Sources**, add a press-page or channel/RSS monitor for a selected story, or submit an article. Press/channel monitors match titles and aliases; generic feeds are explicitly assigned to the selected story. New proposals appear in **Review queue**. Reviewed claims remain private to your account. Use Django administration to curate shared franchise and relationship records, including unresolved relationships and separate volumes/editions.

In **Settings**, select a model provider, endpoint, exact model ID, and credential. OpenAI-compatible endpoints normally end in `/v1`. Google's SDK uses `https://generativelanguage.googleapis.com` and does not accept a custom endpoint. Additional model hosts need `ALLOWED_MODEL_HOSTS`. Loopback model endpoints require `ALLOW_LOCAL_MODELS=1`; `localhost` means the **worker machine**, so a laptop model needs a local worker or a reachable endpoint. Extraction makes at most one agent model invocation per charged daily slot and does not call external tools.

Library and source rights are separate. TMDB requires attribution and commercial arrangements for commercial use; TVmaze requires attribution and ShareAlike compliance. Bangumi and publisher/NDL records retain their source identifiers and require deployment-specific data-use review. AniList is excluded. See [source notes](docs/sources.md).

## Checks and contracts

```sh
cd apps/backend
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
uv run python ../../scripts/generate_contracts.py
uv run python manage.py export_openapi
```

```sh
cd apps/web
npm run typecheck
npm run build
npm run build:pwa
npx playwright install chromium
npm run test:e2e
```

Browser acceptance tests use controlled API fixtures to verify the UI on desktop and mobile. Django tests exercise real database operations and API authorization; adapter tests use stored HTML and mocked provider responses. Live credentials are not required for the fixture suite. CI runs both suites, checks generated contracts and migrations for drift, and validates the packaged stack. It supplies the dependency locks used by the tests to both Docker builds.

The release policy checks run with the Python standard library:

```sh
python -m unittest discover -s scripts/tests -v
```

The pure date/identity/chapter-reconciliation suite also runs without Django:

```sh
PYTHONPATH=apps/backend python -m unittest discover -s apps/backend/tests -p test_contracts.py
```

`packages/contracts/schema.json` and `apps/web/src/api/contracts.ts` are generated from the backend's Pydantic API models. `/api/openapi.json` exposes the live route contract; `export_openapi` saves it when Django dependencies are installed.

## Mobile and desktop

Set `API_BASE_URL` to the reachable HTTPS API, including `/api`, when building a client outside the same web origin. Set `CORS_ALLOWED_ORIGINS` on the backend for the client origin. Android/Capacitor normally uses `http://localhost` and iOS uses `capacitor://localhost`. A packaged Electron file origin is `null`; set `ALLOW_ELECTRON_FILE_ORIGIN=1` explicitly for deployments using that packaging mode, or serve the desktop client from your application origin. Authentication uses bearer tokens, not cross-origin cookies.

```sh
cd apps/web
npm run build:pwa
# For desktop, install the Electron binary if you skipped it during web setup:
npm rebuild electron
API_BASE_URL=https://YOUR_SERVER/api npm run dev:electron
API_BASE_URL=https://YOUR_SERVER/api npm run build:electron
```

```sh
cd apps/web/src-capacitor
npm install
npx cap add android
# On macOS with Xcode: npx cap add ios
cd ..
API_BASE_URL=https://YOUR_SERVER/api npm run dev:android
API_BASE_URL=https://YOUR_SERVER/api npm run build:android
# On macOS: npm run dev:ios / npm run build:ios
```

Android needs its SDK/JDK, iOS needs macOS/Xcode, and desktop packaging needs the target OS's tooling. Signing/store distribution is outside this repository's current setup.

## Validation status

GitHub Actions passed **68 backend acceptance tests against PostgreSQL**, Django checks and migrations, generated-contract drift checks, the Quasar typecheck and SPA/PWA builds, **six desktop/mobile browser tests**, **eight release-policy tests**, and the **complete packaged container stack check**. Both dependency lockfiles are committed. Details and run links are tracked in [validation notes](docs/validation.md).

Kakuyomu selectors/pagination, publisher layouts, press monitors, NDL resolution, model-provider integration, and native packaging still need live validation. Fixture coverage does not establish that current websites still use those layouts.
