from .base import *

INSTALLED_APPS += [
    'django.contrib.admin',
    'nested_admin',

]

ROOT_URLCONF = "iys_sgd_backend.urls_admin"

WSGI_APPLICATION = "iys_sgd_backend.wsgi_admin.application"
