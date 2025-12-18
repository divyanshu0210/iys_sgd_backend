import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "iys_sgd_backend.settings.api",
)

application = get_wsgi_application()
