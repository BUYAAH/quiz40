import os
from pathlib import Path

from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Local/production secrets live in a .env file next to manage.py (not committed to
# git). Loading it here is a no-op if the file doesn't exist, so dev without a
# .env still works with the defaults below.
load_dotenv(BASE_DIR / '.env')

# Production is selected by setting PRODUCTION=1 in the environment (via the
# .env file). Doing nothing gives the safe dev defaults.
PRODUCTION = os.environ.get('PRODUCTION') == '1'

# SECURITY WARNING: keep the secret key used in production secret!
if PRODUCTION:
    SECRET_KEY = os.environ['SECRET_KEY']
else:
    SECRET_KEY = 'django-insecure-$e7)a4_sj431m@#&q9-47r7*-y1f-r2ld@=&wyp3675-0le7tb'

DEBUG = not PRODUCTION

if PRODUCTION:
    ALLOWED_HOSTS = ['rethrow.dk', 'www.rethrow.dk']
else:
    ALLOWED_HOSTS = []


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'accounts',
    'core',
    'pages',
]

AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/quiz/vaert/'

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
        'DIRS': ["templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
# MySQL in production (PythonAnywhere's network storage makes SQLite locking
# unreliable under concurrent writes), SQLite for local dev.

if PRODUCTION:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'NAME': os.environ['DB_NAME'],          # e.g. 'username$quiz'
            'USER': os.environ['DB_USER'],
            'PASSWORD': os.environ['DB_PASSWORD'],
            'HOST': os.environ['DB_HOST'],          # e.g. 'username.mysql.pythonanywhere-services.com'
            'OPTIONS': {'charset': 'utf8mb4'},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'Europe/Copenhagen'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
# collectstatic's output (production only) — separate from STATICFILES_DIRS above,
# which holds the source files (vendored Bootstrap/htmx, quiz.css).
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (uploaded MP3 clips and interlude images).
# In production these are served by PythonAnywhere's static file mappings.
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
