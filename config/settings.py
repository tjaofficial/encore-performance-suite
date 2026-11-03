import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/

SECRET_KEY = os.getenv("SECRET_KEY")
DEBUG = os.getenv("DEBUG", "False") == "True"

# Allow large internal Studio Director onboarding review submissions while
# keeping a finite ceiling. Can be overridden per environment if needed.
DATA_UPLOAD_MAX_NUMBER_FIELDS = int(
    os.getenv(
        "DATA_UPLOAD_MAX_NUMBER_FIELDS",
        "20000",
    )
)

def env_list(name, default=""):
    return [
        value.strip()
        for value in os.getenv(name, default).split(",")
        if value.strip()
    ]


ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost",
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "",
)


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "rest_framework",
    "studios.apps.StudiosConfig",
    "accounts",
    "families",
    "students",
    "instructors",
    "classes",
    "enrollments",
    "scheduling.apps.SchedulingConfig",
    "dashboard.apps.DashboardConfig",
    "attendance.apps.AttendanceConfig",
    "billing.apps.BillingConfig",
    "evaluations.apps.EvaluationsConfig",
    "resources.apps.ResourcesConfig",
    "performance.apps.PerformanceConfig",
    "communications.apps.CommunicationsConfig",
    "reports.apps.ReportsConfig",
    "registration_portal.apps.RegistrationPortalConfig",
    "marketing.apps.MarketingConfig",
    "tasks.apps.TasksConfig",
    "timekeeping.apps.TimekeepingConfig",
    "costumes.apps.CostumesConfig",
    "support_center.apps.SupportCenterConfig",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "communications.context_processors.workspace_notifications",
                "billing.context_processors.subscription_context",
                "studios.context_processors.studio_branding",
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

if os.getenv("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "encore"),
            "USER": os.getenv("DB_USER", "encore"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "db"),
            "PORT": os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE": int(
                os.getenv("DB_CONN_MAX_AGE", "60")
            ),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = "America/Detroit"
USE_TZ = True
USE_I18N = True


STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/login/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    (
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "config.email_backend.SESEmailBackend"
    ),
)

REGISTRATION_START_LIMIT_PER_HOUR = int(
    os.getenv("REGISTRATION_START_LIMIT_PER_HOUR", "20")
)
REGISTRATION_EMAIL_SESSION_LIMIT_PER_HOUR = int(
    os.getenv("REGISTRATION_EMAIL_SESSION_LIMIT_PER_HOUR", "5")
)
REGISTRATION_VERIFICATION_EMAIL_LIMIT_PER_HOUR = int(
    os.getenv("REGISTRATION_VERIFICATION_EMAIL_LIMIT_PER_HOUR", "4")
)
REGISTRATION_EMAIL_VERIFICATION_MAX_AGE_SECONDS = int(
    os.getenv("REGISTRATION_EMAIL_VERIFICATION_MAX_AGE_SECONDS", "3600")
)

AWS_SES_REGION = os.getenv(
    "AWS_SES_REGION",
    "us-east-2",
)

AWS_ACCESS_KEY_ID = os.getenv(
    "AWS_ACCESS_KEY_ID",
)

AWS_SECRET_ACCESS_KEY = os.getenv(
    "AWS_SECRET_ACCESS_KEY",
)

AWS_SESSION_TOKEN = os.getenv(
    "AWS_SESSION_TOKEN",
)

SES_CONFIGURATION_SET = os.getenv(
    "SES_CONFIGURATION_SET",
    "encore-main",
)

EMAIL_FROM_ADDRESS = os.getenv(
    "EMAIL_FROM_ADDRESS",
    "no-reply@encoreperformancesuite.com",
)

EMAIL_FROM_NAME = os.getenv(
    "EMAIL_FROM_NAME",
    "Encore Performance Suite",
)

EMAIL_REPLY_TO = os.getenv(
    "EMAIL_REPLY_TO",
    "info@encoreperformancesuite.com",
)

DEFAULT_FROM_EMAIL = (
    f"{EMAIL_FROM_NAME} <{EMAIL_FROM_ADDRESS}>"
)


ENCORE_ONBOARDING_EMAIL = os.getenv(
    "ENCORE_ONBOARDING_EMAIL",
    "info@encoreperformancesuite.com",
)

STRIPE_SECRET_KEY = os.getenv(
    "STRIPE_SECRET_KEY",
    "",
)

STRIPE_PUBLISHABLE_KEY = os.getenv(
    "STRIPE_PUBLISHABLE_KEY",
    "",
)

STRIPE_WEBHOOK_SECRET = os.getenv(
    "STRIPE_WEBHOOK_SECRET",
    "",
)

ENCORE_SUBSCRIPTION_GRACE_DAYS = int(
    os.getenv(
        "ENCORE_SUBSCRIPTION_GRACE_DAYS",
        "7",
    )
)


STRIPE_CONNECT_WEBHOOK_SECRET = os.getenv(
    "STRIPE_CONNECT_WEBHOOK_SECRET",
    "",
)

ENCORE_BASE_URL = os.getenv(
    "ENCORE_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = (
    "HTTP_X_FORWARDED_PROTO",
    "https",
)

SECURE_SSL_REDIRECT = (
    os.getenv(
        "SECURE_SSL_REDIRECT",
        "False",
    )
    == "True"
)

SESSION_COOKIE_SECURE = (
    os.getenv(
        "SESSION_COOKIE_SECURE",
        "False" if DEBUG else "True",
    )
    == "True"
)

CSRF_COOKIE_SECURE = (
    os.getenv(
        "CSRF_COOKIE_SECURE",
        "False" if DEBUG else "True",
    )
    == "True"
)


ENCORE_PUBLIC_BASE_URL = os.getenv(
    "ENCORE_PUBLIC_BASE_URL",
    "http://127.0.0.1:8000" if DEBUG else "https://encoreperformancesuite.com",
).rstrip("/")

ENCORE_OWNER_EMAIL_VERIFICATION_MAX_AGE_SECONDS = int(
    os.getenv("ENCORE_OWNER_EMAIL_VERIFICATION_MAX_AGE_SECONDS", "86400")
)

ENCORE_OWNER_VERIFICATION_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("ENCORE_OWNER_VERIFICATION_RESEND_COOLDOWN_SECONDS", "60")
)


# Test-mode Connect accounts must be explicitly paired to each studio.
# Example .env: STRIPE_TEST_CONNECTED_ACCOUNTS={"pizza-moves":"acct_TEST_ACCOUNT_ID"}
# This is ignored whenever a live Stripe secret key is configured.
STRIPE_TEST_CONNECTED_ACCOUNTS = os.getenv("STRIPE_TEST_CONNECTED_ACCOUNTS", "{}")
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"