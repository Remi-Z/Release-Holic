# Container releases

The [CI and container releases workflow](https://github.com/Remi-Z/Release-Holic/actions/workflows/checks.yml) runs on pushes to `main`, `v*` tags, pull requests, and manual dispatch. Publishing requires successful PostgreSQL/API tests, client typecheck/build, desktop/mobile browser tests, and a complete Docker Compose smoke check. The smoke check exercises authenticated API access, served PWA assets, PostgreSQL migrations, RabbitMQ/Celery communication, the scheduler process, and Chromium inside the worker image.

Two Linux AMD64 images are published to GitHub Container Registry:

| Image | Runtime |
| --- | --- |
| `ghcr.io/remi-z/release-holic-backend` | Django API; also used with Celery worker/beat commands |
| `ghcr.io/remi-z/release-holic-web` | Built Quasar PWA and Nginx reverse proxy |

The images carry OCI source/revision labels, build provenance, and SBOMs. Each successful publication saves a `container-manifest` Actions artifact containing both image digests and the source commit. Versioned GitHub Releases attach `release-manifest.json` for long-term access.

## Tag behavior

| Trigger | Published tags | GitHub Release |
| --- | --- | --- |
| Successful `main` push/manual build | `main`, `sha-FULL_COMMIT` | None |
| `v0.1.0` tag | `v0.1.0`, `0.1.0`, `latest`, `sha-FULL_COMMIT` | Stable |
| `v0.1.0-rc.1` tag | `v0.1.0-rc.1`, `0.1.0-rc.1`, `sha-FULL_COMMIT` | Prerelease |
| Pull request or manual non-main branch | None | None |

Tags must contain three numeric version components, with an optional SemVer prerelease suffix. Leading-zero numeric components and build metadata (`+...`) are rejected. Prereleases never promote `latest`. Versions are selected by the maintainer; the workflow does not invent version bumps.

Create a release from a tested commit:

```sh
git fetch origin
git tag v0.1.0 origin/main
git push origin v0.1.0
```

Use a new version for each release. A rerun refreshes the existing release manifest rather than creating a second release.

## Registry authentication

The publishing job uses `GITHUB_TOKEN` with `packages: write`; the GitHub Release job has `contents: write`. Pull requests do not log in to GHCR or push images. Actions are pinned to verified commit SHAs. No Docker Hub account or custom publish credential is needed.

GHCR packages start private, including packages associated with public repositories. To permit anonymous pulls, open each package's settings on GitHub and change its visibility to public. To keep images private, sign in with a GitHub account that has package read access, using a classic personal access token with `read:packages`:

```sh
docker login ghcr.io --username YOUR_GITHUB_USERNAME
# Paste the token only at Docker's password prompt.
```

An existing package under the same name must grant this repository Actions write access. Newly created workflow packages are associated with the repository through their source labels and publishing identity.

## Deploy without building locally

Copy `.env.example` to `.env`, set a persistent Django secret, and choose `IMAGE_TAG`. The example defaults to development images on `main`; stable releases use their version tag. Use the same tag for backend and web so both components come from the tested revision. Forks can change `BACKEND_IMAGE` and `WEB_IMAGE` to their own GHCR image names.

```sh
docker compose -f compose.images.yaml pull
docker compose -f compose.images.yaml up -d
docker compose -f compose.images.yaml exec api python manage.py createsuperuser
```

Open `http://localhost:8080`. For subsequent updates, select the next tag in `.env`, pull, and run `up -d` again. Compose runs database migrations before starting the API and workers. PostgreSQL and RabbitMQ persist in named volumes. Preserve the database, Django secret, and model encryption key when updating; an older application image may require a database-compatible rollback strategy.

The registry workflow publishes images and releases. Updating a running server remains an explicit deployment action. Public hosting still uses the HTTPS configuration documented in the README.

## Dependencies and diagnostics

The validation jobs require the checked-in `uv.lock` and `package-lock.json`, install their frozen dependencies, and upload those same locks for the Docker builds. CI artifacts also include API test reports/OpenAPI, failed browser traces, and container logs. The release policy's eight stdlib tests verify publication eligibility and stable/prerelease behavior.

Celery 5.6.3 or newer creates exclusive control and event queues for RabbitMQ 4 compatibility. These queues belong to each worker/client connection; ingestion task queues remain durable.
