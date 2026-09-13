"""Impostazioni comuni. Tutto ciò che varia per ambiente arriva da variabili d'ambiente (12-factor)."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    LOG_LEVEL=(str, "INFO"),
)
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.gis",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "drf_spectacular",
    "corsheaders",
    "channels",
    # SAFE
    "safe.apps.core",
    "safe.apps.tenancy",
    "safe.apps.authn",
    "safe.apps.authz",
    "safe.apps.lookups",
    "safe.apps.org",
    "safe.apps.territory",
    "safe.apps.rescue",
    "safe.apps.devices",
    "safe.apps.crypto",
    "safe.apps.jobs",
    "safe.apps.audit",
    "safe.apps.stats",
    "safe.apps.maps",
    "safe.apps.reports",
    "safe.apps.exports",
]

AUTH_USER_MODEL = "org.AppUser"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "safe.apps.core.middleware.SecurityHeadersMiddleware",
    "safe.apps.tenancy.middleware.TenantMiddleware",
]

ROOT_URLCONF = "safe.urls"
WSGI_APPLICATION = "safe.wsgi.application"
ASGI_APPLICATION = "safe.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "safe" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

# --- Database: PostGIS ---------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ENGINE"] = "django.contrib.gis.db.backends.postgis"
DATABASES["default"]["CONN_MAX_AGE"] = 60
# La transazione per richiesta è aperta dal TenantMiddleware (SET LOCAL app.company_id per RLS)
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Redis: cache, Celery, Channels -------------------------------------------
REDIS_URL = env("REDIS_URL")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "safe",
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "safe.apps.exports.*": {"queue": "exports"},
    "safe.apps.reports.*": {"queue": "pdf"},
}
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TIMEZONE = "UTC"
CELERY_BEAT_SCHEDULE = {
    "auto-lock-events": {"task": "safe.apps.rescue.auto_lock_events", "schedule": 900.0},
    "cleanup-expired-jobs": {"task": "safe.apps.jobs.cleanup_expired", "schedule": 86400.0},
    "retention-run": {"task": "safe.apps.rescue.retention_run", "schedule": 86400.0},
}
CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {"hosts": [REDIS_URL]}}
}

# --- REST framework ------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["safe.apps.authn.drf.OIDCAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["safe.apps.authz.drf.HasPermission"],
    "DEFAULT_PAGINATION_CLASS": "safe.apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "safe.apps.core.exceptions.exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "600/min",
        "identity": "30/min",
        "recovery": "5/hour",
        "invite": "30/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SAFE API",
    "VERSION": "1.0.0",
    "DESCRIPTION": "API della piattaforma SAFE per incidenti su piste da sci.",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_EXPOSE_HEADERS = ["Content-Disposition"]
CORS_ALLOW_CREDENTIALS = False

# --- OIDC ----------------------------------------------------------------------
OIDC_ISSUER = env("OIDC_ISSUER")
OIDC_AUDIENCE = env("OIDC_AUDIENCE", default="safe-api")
OIDC_JWKS_URL = env("OIDC_JWKS_URL", default=f"{OIDC_ISSUER}/protocol/openid-connect/certs")
OIDC_JWKS_CACHE_SECONDS = 3600

# --- Keycloak Admin API (inviti, disattivazione) e URL pubblici ---------------------------------
KEYCLOAK_ADMIN_URL = env("KEYCLOAK_ADMIN_URL", default="http://keycloak:8080")
KEYCLOAK_REALM = env("KEYCLOAK_REALM", default="safe")
KEYCLOAK_ADMIN_CLIENT_ID = env("KEYCLOAK_ADMIN_CLIENT_ID", default="safe-admin")
KEYCLOAK_ADMIN_CLIENT_SECRET = env("KEYCLOAK_ADMIN_CLIENT_SECRET", default="")
KEYCLOAK_WEB_CLIENT_ID = env("KEYCLOAK_WEB_CLIENT_ID", default="safe-web")
WEB_BASE_URL = env("PUBLIC_WEB_URL", default="http://localhost:4200")
PUBLIC_API_URL = env("PUBLIC_API_URL", default="http://localhost:8000/api/v1")

# --- Identità visiva nei PDF (stesse variabili della SPA: BRAND_NAME, BRAND_LOGO_URL) --------------
# BRAND_LOGO_URL è un percorso relativo alla SPA ("brand/ski-civetta.png"); il file viene cercato in
# BRAND_DIR (in produzione la cartella dei loghi del tema Keycloak montata in /app/brand).
# Vuoto = simbolo "S" e scritta SAFE.
BRAND_NAME = env("BRAND_NAME", default="") or "SAFE"
BRAND_LOGO_URL = env("BRAND_LOGO_URL", default="")
BRAND_DIR = env("BRAND_DIR", default="")

# --- Cartografia (Mapbox): stili per ambiente; il token pubblico sta nella config del client -----
MAP_STYLES = {
    "winter": env("MAPBOX_STYLE_WINTER", default="mapbox://styles/mapbox/light-v11"),
    "summer": env("MAPBOX_STYLE_SUMMER", default="mapbox://styles/mapbox/outdoors-v12"),
    "satellite": env("MAPBOX_STYLE_SATELLITE", default="mapbox://styles/mapbox/satellite-streets-v12"),
}
MAPBOX_TOKEN = env("MAPBOX_SECRET_TOKEN", default="") or env(
    "MAPBOX_TOKEN", default=""
)  # immagini statiche per i PDF

# --- Object storage (MinIO / S3) ---------------------------------------------------------------
S3_ENDPOINT_URL = env("S3_ENDPOINT_URL", default="http://minio:9000")
S3_ACCESS_KEY = env("S3_ACCESS_KEY", default="safe")
S3_SECRET_KEY = env("S3_SECRET_KEY", default="safe-secret")
S3_BUCKET = env("S3_BUCKET", default="safe-files")
S3_REGION = env("S3_REGION", default="eu-central-1")

# --- Internazionalizzazione ----------------------------------------------------
LANGUAGE_CODE = "it"
LANGUAGES = [("it", "Italiano"), ("en", "English"), ("de", "Deutsch")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Logging: JSON strutturato, mai corpi di richiesta, mai dati personali ------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"},
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL")},
    "loggers": {
        "django.request": {"level": "WARNING"},
        "django.db.backends": {"level": "WARNING"},
    },
}
