import os
import secrets
import sys
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from kombu import Queue

from .secrets import build_broker_url, build_result_backend, load_dotenv, read_secret

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR)

DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() in {"1", "true", "yes"}

_secret_key = read_secret(
    env_var="DJANGO_SECRET_KEY",
    file_env_var="DJANGO_SECRET_KEY_FILE",
    secret_name="django_secret_key",
    base_dir=BASE_DIR,
)
if not _secret_key:
    if DEBUG or "test" in sys.argv or "spectacular" in sys.argv:
        # Chave efêmera apenas para testes/geração de schema em CI sem segredos locais
        _secret_key = secrets.token_urlsafe(48)
    else:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY não definida. Configure via Docker Secret ou .env."
        )

SECRET_KEY = _secret_key

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,web").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "queue_api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

DB_DIR = Path(os.getenv("DJANGO_DB_DIR", str(BASE_DIR / "data")))
if not DB_DIR.exists():
    DB_DIR.mkdir(parents=True, exist_ok=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DB_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Queue API — Django, DRF, Celery & RabbitMQ",
    "DESCRIPTION": (
        "API REST para disparo e consulta de tarefas assíncronas usando Celery, "
        "RabbitMQ (Broker AMQP) e Redis (Result Backend). A documentação OpenAPI "
        "é gerada automaticamente a partir dos serializers, views e decorators."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    "COMPONENT_SPLIT_REQUEST": True,
}

# Configurações do Celery (carregadas automaticamente pelo namespace CELERY)
CELERY_BROKER_URL = build_broker_url(BASE_DIR)
CELERY_RESULT_BACKEND = build_result_backend(BASE_DIR)
CELERY_TASK_DEFAULT_QUEUE = "celery"
CELERY_TASK_QUEUES = (
    Queue("celery"),
    Queue("alta_prioridade"),
)
CELERY_BEAT_SCHEDULE = {
    "heartbeat-a-cada-30-segundos": {
        "task": "queue_api.tasks.heartbeat_sistema",
        "schedule": 30.0,
    },
}
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
# Registra o estado STARTED no Redis enquanto o worker executa a tarefa
CELERY_TASK_TRACK_STARTED = True
# Salva metadados extras no Redis (nome da task, args, fila) para depuração
CELERY_RESULT_EXTENDED = True
# Define TTL de 1 hora (3600s) para expirar resultados antigos no Redis automaticamente
CELERY_RESULT_EXPIRES = 3600
