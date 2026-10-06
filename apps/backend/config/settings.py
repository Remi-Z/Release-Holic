import base64
import hashlib
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR.parent.parent / ".env")
DEBUG = os.getenv("DEBUG", "0") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY; see .env.example")
    SECRET_KEY = "local-development-only-release-holic"

ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "corsheaders", "tracker",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request", "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    if not DEBUG:
        raise ImproperlyConfigured("Set DATABASE_URL to your PostgreSQL database")
    database_url = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {"default": dj_database_url.parse(database_url, conn_max_age=60)}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if x]
CORS_ALLOWED_ORIGINS = [x for x in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if x]
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOWED_ORIGIN_REGEXES = [r'^null$'] if os.getenv('ALLOW_ELECTRON_FILE_ORIGIN', '0') == '1' else []

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://localhost//")
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_TASK_TIME_LIMIT = 180
CELERY_TASK_SOFT_TIME_LIMIT = 150
CELERY_TASK_ALWAYS_EAGER = os.getenv("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# RabbitMQ 4 disallows non-durable, non-exclusive transient queues. Control
# and event queues belong to one worker/client connection; task queues stay durable.
CELERY_CONTROL_QUEUE_EXCLUSIVE = True
CELERY_EVENT_QUEUE_EXCLUSIVE = True
CELERY_TASK_PUBLISH_RETRY_POLICY = {"max_retries": 2, "interval_start": 0, "interval_step": 0.2, "interval_max": 0.5}
CELERY_BROKER_CONNECTION_TIMEOUT = 3
CELERY_BEAT_SCHEDULE = {"refresh-followed-works": {"task": "tracker.tasks.schedule_refreshes", "schedule": 900.0}}

TMDB_TOKEN = os.getenv("TMDB_TOKEN", "")
BANGUMI_TOKEN = os.getenv("BANGUMI_TOKEN", "")
USER_AGENT = os.getenv("USER_AGENT", "Release-Holic/0.1 (+https://github.com/Remi-Z/Release-Holic)")
ALLOWED_SOURCE_HOSTS = {x.strip().lower() for x in os.getenv("ALLOWED_SOURCE_HOSTS", "").split(",") if x.strip()}
ALLOWED_MODEL_HOSTS = {x.strip().lower() for x in os.getenv("ALLOWED_MODEL_HOSTS", "").split(",") if x.strip()}
ALLOW_LOCAL_MODELS = os.getenv("ALLOW_LOCAL_MODELS", "0") == "1"
MODEL_ENCRYPTION_KEY = os.getenv("MODEL_ENCRYPTION_KEY") or base64.urlsafe_b64encode(hashlib.sha256(SECRET_KEY.encode()).digest()).decode()
