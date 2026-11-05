"""Configuração do Django orientada por variáveis de ambiente."""

import logging
import os
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BASE_DIR / ".env", override=True)


def env_bool(name: str, default: bool = False) -> bool:
    """Converte uma variável de ambiente comum para booleano."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    """Lê uma lista separada por vírgulas, removendo itens vazios."""
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


IS_RENDER = env_bool("RENDER")
DEBUG = env_bool("DJANGO_DEBUG", not IS_RENDER)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")

if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY é obrigatória quando DJANGO_DEBUG=false.")
    SECRET_KEY = "django-insecure-juripredict-local-development-only"

FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY")
if not FIELD_ENCRYPTION_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY é obrigatória quando DJANGO_DEBUG=false.")
    FIELD_ENCRYPTION_KEY = SECRET_KEY

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
FLY_APP_NAME = os.getenv("FLY_APP_NAME", "").strip()
if FLY_APP_NAME:
    fly_hostname = f"{FLY_APP_NAME}.fly.dev"
    if fly_hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(fly_hostname)
RENDER_EXTERNAL_HOSTNAME = os.getenv("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "storages",
    "organizations",
    "auditlog",
    "accounts",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
]
if not DEBUG:
    MIDDLEWARE.append("whitenoise.middleware.WhiteNoiseMiddleware")
MIDDLEWARE += [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "accounts.middleware.AuditoriaTokenApiMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "frontend_dist"],
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

WSGI_APPLICATION = "config.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_HOST = os.getenv("DB_HOST") or os.getenv("SUPABASE_DB_HOST")
DB_NAME = os.getenv("DB_NAME") or os.getenv("SUPABASE_DB_NAME", "juripredict_db")
DB_USER = os.getenv("DB_USER") or os.getenv("SUPABASE_DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("SUPABASE_DB_PASSWORD", "")
DB_PORT = os.getenv("DB_PORT") or os.getenv("SUPABASE_DB_PORT", "5432")

if DATABASE_URL:
    database = urlparse(DATABASE_URL)
    if database.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured("DATABASE_URL deve usar o esquema postgres ou postgresql.")
    query = parse_qs(database.query)
    database_options = {
        key: values[-1]
        for key, values in query.items()
        if key in {"sslmode", "sslcert", "sslkey", "sslrootcert"} and values
    }
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(database.path.lstrip("/")),
            "USER": unquote(database.username or ""),
            "PASSWORD": unquote(database.password or ""),
            "HOST": database.hostname or "",
            "PORT": str(database.port or 5432),
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "0")),
            "DISABLE_SERVER_SIDE_CURSORS": True,
            "OPTIONS": database_options,
        }
    }
elif DB_HOST:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": DB_NAME,
            "USER": DB_USER,
            "PASSWORD": DB_PASSWORD,
            "HOST": DB_HOST,
            "PORT": DB_PORT,
            "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60")),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Só nos testes: PBKDF2 com centenas de milhares de iterações transforma cada
# create_user num custo de ~0,3 s. Produção e desenvolvimento seguem com o padrão.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_ROOT = BASE_DIR / "frontend_dist"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# E-mail transacional (convite, recuperação de senha, lembrete de prazo).
# Com EMAIL_HOST definido usa SMTP, que serve a qualquer provedor (Resend,
# SendGrid, Amazon SES...). Sem ele, cai no console: aceitável em desenvolvimento,
# mas em produção significa que NENHUM e-mail sai, e por isso avisa no log.
EMAIL_HOST = os.getenv("EMAIL_HOST", "").strip()
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_TIMEOUT = 10
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    if not DEBUG:
        logging.getLogger(__name__).warning(
            "EMAIL_HOST não configurado: e-mails vão para o console e não chegam "
            "a ninguém. Defina EMAIL_HOST antes de aceitar usuários reais."
        )
DEFAULT_FROM_EMAIL = os.getenv(
    "DEFAULT_FROM_EMAIL", "JuriPredict <nao-responda@juripredict.local>"
)

# Base dos links enviados por e-mail.
FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    f"https://{RENDER_EXTERNAL_HOSTNAME}" if RENDER_EXTERNAL_HOSTNAME else "http://localhost:5173",
).rstrip("/")

# Validade dos links. O de recuperação de senha é curto de propósito.
PASSWORD_RESET_TIMEOUT = int(os.getenv("PASSWORD_RESET_TIMEOUT", "3600"))
CONVITE_VALIDADE_DIAS = int(os.getenv("CONVITE_VALIDADE_DIAS", "7"))

# Monitoramento de erros. Só liga com SENTRY_DSN: sem ele nada sai da aplicação.
# O conteúdo das requisições NUNCA é enviado: o que trafega aqui é CPF, dado de
# cliente e de processo, e não pode parar num serviço de terceiros.
SENTRY_DSN = os.getenv("SENTRY_DSN", "").strip()
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development" if DEBUG else "production"),
        send_default_pii=False,
        max_request_body_size="never",
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0")),
    )

# Quantos processos concluídos uma taxa precisa ter para ser exibida. Abaixo
# disso a taxa é suprimida, com o motivo: 1 favorável em 1 processo daria "100%".
JURIMETRIA_PISO_AMOSTRA = int(os.getenv("JURIMETRIA_PISO_AMOSTRA", "10"))

# Teto de anexos por processo: evita que uma conta encha o storage sem querer.
DOCUMENTOS_MAX_POR_PROCESSO = int(os.getenv("DOCUMENTOS_MAX_POR_PROCESSO", "50"))
# Tamanho máximo dos arquivos enviados (petição inicial e anexos).
UPLOAD_MAX_BYTES = int(os.getenv("UPLOAD_MAX_MB", "10")) * 1024 * 1024

# Quanto antes do prazo o lembrete sai. O agendador roda de hora em hora.
LEMBRETE_ANTECEDENCIA_HORAS = int(os.getenv("LEMBRETE_ANTECEDENCIA_HORAS", "24"))

# Chave pública do DataJud (wiki do CNJ). Sem ela o acompanhamento fica desligado.
DATAJUD_API_KEY = os.getenv("DATAJUD_API_KEY", "")
# Tokens de API (agentes/MCP): validade padrão e quantos podem estar ativos por pessoa.
API_TOKEN_VALIDADE_DIAS = int(os.getenv("API_TOKEN_VALIDADE_DIAS", "90"))
API_TOKEN_MAX_ATIVOS = int(os.getenv("API_TOKEN_MAX_ATIVOS", "5"))
VERIFICACAO_EMAIL_HORAS = int(os.getenv("VERIFICACAO_EMAIL_HORAS", "72"))
# Versão vigente dos Termos de Uso e da Política de Privacidade. Mudou o texto,
# muda a versão: o cadastro grava qual versão cada usuário aceitou.
TERMOS_VERSAO = os.getenv("TERMOS_VERSAO", "2026-10")

CORS_ALLOW_ALL_ORIGINS = env_bool("CORS_ALLOW_ALL_ORIGINS", DEBUG)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
if FLY_APP_NAME:
    fly_origin = f"https://{FLY_APP_NAME}.fly.dev"
    if fly_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(fly_origin)
if RENDER_EXTERNAL_HOSTNAME:
    render_origin = f"https://{RENDER_EXTERNAL_HOSTNAME}"
    if render_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(render_origin)

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "accounts.authentication.TokenApiAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # Atrás de proxy (Render, Fly) o IP real vem no X-Forwarded-For. Sem isto,
    # todo mundo parece vir do mesmo endereço e o limite vira global.
    "NUM_PROXIES": int(os.getenv("NUM_PROXIES", "0" if DEBUG else "1")),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/day",
        # 1000/dia esgotava com uso normal: cada tela do SPA faz várias chamadas.
        "user": "20000/day",
        # Endpoints públicos têm escopo próprio, em vez do limite anônimo global.
        "login": "60/min",
        "login_conta": "10/min",
        "refresh": "300/hour",
        "registro": "5/hour",
        "convite": "20/hour",
        "recuperacao_senha": "10/hour",
        "conta_sensivel": "10/hour",
        "andamentos": "30/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "JuriPredict API",
    "DESCRIPTION": (
        "API REST do JuriPredict: gestão de clientes, processos e agenda, com jurimetria "
        "da carteira, isolamento por escritório e controle de acesso por papel.\n\n"
        "Erros são devolvidos em JSON: 400 (dados inválidos), 401 (credencial ausente, inválida "
        "ou expirada), 403 (papel sem a capacidade exigida), 404 (recurso inexistente ou de outro "
        "escritório), 409 (exclusão de cliente com processos), 429 (limite de requisições) e "
        "503 (DataJud sem chave configurada)."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "StatusProcessoEnum": "api.models.Processo.STATUS_CHOICES",
        "StatusMembroEnum": "organizations.models.MembroEscritorio.Status",
    },
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "config.openapi.adicionar_cabecalho_escritorio",
    ],
}

SIMPLE_JWT = {
    # O access token não pode ser revogado, só expira. Curto, limita o que um
    # token vazado permite; o app renova sozinho, então a pessoa não percebe.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    # Cada renovação emite um refresh novo e invalida o anterior; um refresh
    # roubado e usado depois do dono deixa de funcionar. O logout e a troca de
    # senha por recuperação revogam o refresh no servidor.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

if env_bool("USE_R2_STORAGE"):
    required_r2_settings = {
        "AWS_ACCESS_KEY_ID": os.getenv("AWS_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "AWS_STORAGE_BUCKET_NAME": os.getenv("AWS_STORAGE_BUCKET_NAME"),
        "AWS_S3_ENDPOINT_URL": os.getenv("AWS_S3_ENDPOINT_URL"),
    }
    missing = [name for name, value in required_r2_settings.items() if not value]
    if missing:
        raise ImproperlyConfigured(f"Configuração R2 incompleta: {', '.join(missing)}")

    globals().update(required_r2_settings)
    AWS_S3_REGION_NAME = os.getenv("AWS_S3_REGION_NAME", "auto")
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage"},
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        },
    }
