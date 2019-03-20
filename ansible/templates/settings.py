"""
Django settings for privacymail project.

Generated by 'django-admin startproject' using Django 2.0.4.

For more information on this file, see
https://docs.djangoproject.com/en/2.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/2.0/ref/settings/
"""

import os
import raven
from raven.transport.requests import RequestsHTTPTransport





# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/2.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = '{{ lookup('passwordstore', 'privacymail/django-secret-key' )}}'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['beta.privacymail.info']


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django_countries',
    'django_cron',
    'widget_tweaks',
    'mailfetcher',
    'util',
    'identity',
    'fontawesome',
    'bootstrap_themes',
    'raven.contrib.django.raven_compat',
    'django_extensions',
    'silk'
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'silk.middleware.SilkyMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'privacymail.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'privacymail.wsgi.application'


# Database
# https://docs.djangoproject.com/en/2.0/ref/settings/#databases

#DATABASES = {
#    'default': {
#        'ENGINE': 'django.db.backends.sqlite3',
#        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#    }
#}

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': 'privacymail',
        'USER': '{{ lookup('passwordstore', 'privacymail/postgres-user' )}}',
        'PASSWORD': '{{ lookup('passwordstore', 'privacymail/postgres-password' )}}',
        'HOST': 'localhost',
        'PORT': '',
        'CONN_MAX_AGE': None,
    }
}

# Caching
CACHES = {
    'default': {
        "BACKEND": 'django.core.cache.backends.db.DatabaseCache',
        "LOCATION": 'pmail_cache',
        "TIMEOUT": None,  # Cache does not automatically expire
        "MAX_ENTRIES": 10000,  # Allow a lot of entries in the cache to avoid culling
    }
}

# Password validation
# https://docs.djangoproject.com/en/2.0/ref/settings/#auth-password-validators

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
# https://docs.djangoproject.com/en/2.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/2.0/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = 'static/'

CRON_CLASSES = [
    "mailfetcher.cron.ImapFetcher",
    "mailfetcher.analyser_cron.Analyser",
]

OPENWPM_PATH = '/home/privacymail/privacymail/privacymail/runopenwpm.py'
# Change these in runopenwpm.py as well, if you want to change them
OPENWPM_DATA_DIR = '/home/privacymail/openwpm/data/'
OPENWPM_LOG_DIR = '/home/privacymail/openwpm/log/'

#URL on which the server is reached
SYSTEM_ROOT_URL = 'https://beta.privacymail.info'

# Mail credentials

MAILCREDENTIALS = [
    {
        'MAILHOST': 'mail.newsletterme.de',
        'MAILUSERNAME': '{{ lookup('passwordstore', 'privacymail/email/newsletterme/user' )}}',
        'MAILPASSWORD': '{{ lookup('passwordstore', 'privacymail/email/newsletterme/pass' )}}',
        'DOMAIN': 'newsletterme.de',
    },
    {
        'MAILHOST': 'mail.privacyletter.de',
        'MAILUSERNAME': '{{ lookup('passwordstore', 'privacymail/email/privacyletter/user' )}}',
        'MAILPASSWORD': '{{ lookup('passwordstore', 'privacymail/email/privacyletter/pass' )}}',
        'DOMAIN': 'privacyletter.de',
    },
    {
        'MAILHOST': 'mail.privacy-mail.org',
        'MAILUSERNAME': '{{ lookup('passwordstore', 'privacymail/email/privacy-mail/user' )}}',
        'MAILPASSWORD': '{{ lookup('passwordstore', 'privacymail/email/privacy-mail/pass' )}}',
        'DOMAIN': 'privacy-mail.org',
    },
]

DEVELOP_ENVIRONMENT = False
RUN_OPENWPM = True
# Also click one link per mail, to analyze the resulting connection for PII leakages.
# Warning! Detection of unsubscribe links cannot be guaranteed!
VISIT_LINKS = True

# How many links to skip at the beginning and end of a mail, as they may are more likely to be unsubscribe links.
NUM_LINKS_TO_SKIP = 6

# Dictionary of fragments, for which links are scanned to determine, wether they are unsubscribe links.
UNSUBSCRIBE_LINK_DICT = ['sub',  # unsubscribe, subscribtion
                         'abmelden',  # unsubscribe german
                         'stop',
                         'rem',  # remove
                         'abbes',  # abbestellen german
                         'here',  # german
                         'hier',  # German
                         'annu',  # annulla italian, annuler french
                         'canc',  # cancel and cancellarsi italian
                         'disdici',  # italian
                         #'qui',  # here in italian
                         #'ici',  # here in french
                         'dés',  # french
                         'abonn',  # abonn french
                         'retiré'  # french
                        ]

# Number of mails to be processed per batch by the cronjob.
CRON_MAILQUEUE_SIZE = 30

# Number of retries
OPENWPM_RETRIES = 5

OPENWPM_TIMEOUT = 35
# Number of threads used to call openWPM
NUMBER_OF_THREADS = 6

OPENWPM_FAIL_INCREASE = 1

# Don't fetch new mails or run openwpm. Just reanalyze the eresources in the db.
REANALYZE_ERESOURCES = False

EVALUATE = False

LOCALHOST_URL = 'localhost.privacymail.info:5000'


# Django Mail
SERVER_EMAIL = "admin@privacymail.info"
ADMINS = [{{ lookup('passwordstore', 'privacymail/admin/contacts' )}}]
REMINDER_MAIL_THRESHOLD_IN_HOURS = 24


DISABLE_ADMIN_MAILS = True
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_USE_TLS = True
EMAIL_HOST = 'mail.newsletterme.de'
EMAIL_PORT = 587
EMAIL_HOST_USER = '{{ lookup('passwordstore', 'privacymail/admin/send-user' )}}'
EMAIL_HOST_PASSWORD = '{{ lookup('passwordstore', 'privacymail/admin/send-pass' )}}'
# For debugging you may use the console backend
# EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Profiling
SILKY_PYTHON_PROFILER = True

RAVEN_CONFIG = {
    'dsn': '{{ lookup('passwordstore', 'privacymail/raven-dsn') }}',
    # If you are using git, you can also automatically configure the
    # release based on the git info.
    'release': raven.fetch_git_sha(os.path.abspath(os.pardir)),
    'transport': RequestsHTTPTransport,
}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'root': {
        'level': 'WARNING',
        'handlers': ['sentry'],
    },
    'formatters': {
        'verbose': {
            'format': ('%(levelname)s %(asctime)s %(module)s %(process)d '
                       '%(thread)d %(message)s')
        },
        'console': {
            'format': '[%(asctime)s][%(levelname)s] '
                      '%(message)s',
            'datefmt': '%H:%M:%S',
        },

    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'console'
        },
        'sentry': {
            'level': 'DEBUG',
            'class': ('raven.contrib.django.raven_compat.handlers.'
                      'SentryHandler'),
        },
    },
    'loggers': {
        'mailfetcher': {
            'level': 'DEBUG',
            'handlers': ['sentry'],
            'propagate': False
        },
        'identity': {
            'level': "DEBUG",
            'handlers': ['sentry'],
            'propagate': False
        },
        'OpenWPM.automation.MPLogger': {
            'level': 'ERROR',
            'handlers': ['console'],
            'propagate': False
        },
    }
}
