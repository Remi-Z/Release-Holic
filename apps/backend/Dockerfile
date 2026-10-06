# syntax=docker/dockerfile:1.7
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv
# The optional proxy CA is supplied by the build environment, never copied from .env.
RUN --mount=type=secret,id=proxy_ca,required=false \
    if [ -s /run/secrets/proxy_ca ]; then cp /run/secrets/proxy_ca /usr/local/share/ca-certificates/session-proxy.crt; update-ca-certificates; fi
COPY apps/backend ./
RUN --mount=type=cache,target=/tmp/uv-cache \
    UV_NATIVE_TLS=true uv sync --no-dev
# Install a real browser only in the worker image too; API and worker share one image.
RUN if [ -s /usr/local/share/ca-certificates/session-proxy.crt ]; then export NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/session-proxy.crt; fi; \
    .venv/bin/python -m playwright install --with-deps chromium
RUN DEBUG=1 .venv/bin/python manage.py collectstatic --noinput
RUN useradd --create-home app && chown -R app:app /app /root/.cache/ms-playwright \
    && mv /root/.cache/ms-playwright /home/app/ms-playwright
ENV PATH="/app/.venv/bin:$PATH" PLAYWRIGHT_BROWSERS_PATH=/home/app/ms-playwright
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120", "--access-logfile", "-"]
