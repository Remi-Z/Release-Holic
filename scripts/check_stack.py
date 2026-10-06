"""Exercise the packaged API, web server, broker, worker, and browser in CI."""
import json
import os
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

COMPOSE = ["docker", "compose", "-f", "compose.images.yaml"]
ORIGIN = os.environ.get("STACK_ORIGIN", "http://127.0.0.1:8080")


def request(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    payload = json.dumps(data).encode() if data is not None else None
    with urlopen(Request(ORIGIN + path, data=payload, headers=headers), timeout=5) as response:
        return response.read()


def main():
    deadline = time.monotonic() + 180
    while True:
        try:
            assert json.loads(request("/api/health"))["ok"]
            assert b"Release-Holic" in request("/")
            break
        except (URLError, OSError, AssertionError, ValueError):
            if time.monotonic() >= deadline:
                raise RuntimeError("The packaged stack did not become healthy")
            time.sleep(2)
    assert request("/icons/icon-192.png").startswith(b"\x89PNG")
    assert request("/service-worker.js")
    assert request("/static/admin/css/base.css")
    subprocess.run(COMPOSE + ["exec", "-T", "api", "python", "manage.py", "check"], check=True)
    create_account = "from django.contrib.auth import get_user_model; user, _ = get_user_model().objects.get_or_create(username='release-holic-ci'); user.set_password('ci-only-container-test'); user.save()"
    subprocess.run(COMPOSE + ["exec", "-T", "api", "python", "manage.py", "shell", "-c", create_account], check=True)
    login = json.loads(request("/api/auth/login", {"username": "release-holic-ci", "password": "ci-only-container-test"}))
    assert isinstance(json.loads(request("/api/library", token=login["token"])), list)
    ping = "from config.celery import app; replies = app.control.ping(timeout=10); assert replies and all(reply.get(next(iter(reply)), {}).get('ok') == 'pong' for reply in replies), 'No healthy worker replied'"
    subprocess.run(COMPOSE + ["exec", "-T", "api", "python", "-c", ping], check=True)
    browser_check = """from playwright.sync_api import sync_playwright
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_content('<h1>Packaged worker browser</h1>')
    assert page.locator('h1').inner_text() == 'Packaged worker browser'
    browser.close()
"""
    subprocess.run(COMPOSE + ["exec", "-T", "worker", "python", "-"], input=browser_check, text=True, check=True)
    running = subprocess.check_output(COMPOSE + ["ps", "--status", "running", "--services"], text=True).splitlines()
    assert {"api", "worker", "scheduler", "web", "db", "rabbitmq"}.issubset(running), "A required service stopped"
    print("Packaged API, web/PWA, PostgreSQL, RabbitMQ, Celery, and Chromium checks passed.")


if __name__ == "__main__":
    main()
