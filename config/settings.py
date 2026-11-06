import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "development-only-change-before-production-not-a-secret"
    else:
        raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY ou use DJANGO_DEBUG=1 apenas em desenvolvimento.")
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h]
INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "passport",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [], "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
if os.environ.get("DB_ENGINE", "postgres") == "sqlite":
    if not DEBUG:
        raise ImproperlyConfigured("SQLite está restrito ao desenvolvimento.")
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "passaporte"),
        "USER": os.environ.get("POSTGRES_USER", "passaporte"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "development-only-password"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "55432"),
    }}
    if not DEBUG and DATABASES["default"]["PASSWORD"] == "development-only-password":
        raise ImproperlyConfigured("Defina a senha do PostgreSQL antes do uso fora de desenvolvimento.")
LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Fortaleza"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "staff_login"
LOGIN_REDIRECT_URL = "staff_home"
LOGOUT_REDIRECT_URL = "home"
# Eventos de segurança (bloqueios e desbloqueios) vão para a saída do processo; nunca contêm PIN,
# senha, nome de usuário, contato ou endereço de rede. Destino e retenção em produção ainda a definir.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"security": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"security": {"class": "logging.StreamHandler", "formatter": "security"}},
    "loggers": {"passport.security": {"handlers": ["security"], "level": "INFO", "propagate": False}},
}
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
