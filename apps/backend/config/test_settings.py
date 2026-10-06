import os

os.environ.setdefault("DEBUG", "1")
from .settings import *  # noqa: E402,F403

test_database_url = os.environ.get("TEST_DATABASE_URL", "")
DATABASES = {"default": dj_database_url.parse(test_database_url, conn_max_age=0)} if test_database_url else {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
