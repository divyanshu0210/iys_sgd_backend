web: sh -c "
  python manage.py migrate --noinput --skip-checks &&
  python manage.py collectstatic --noinput --clear || true &&
  python manage.py shell -c \"
from django.contrib.auth import get_user_model
import os
User = get_user_model()
username = os.getenv('DJANGO_SUPERUSER_USERNAME')
email = os.getenv('DJANGO_SUPERUSER_EMAIL', '')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD')
if username and password:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        print('Superuser created:', username)
    else:
        print('Superuser already exists:', username)
else:
    print('Missing DJANGO_SUPERUSER_USERNAME or DJANGO_SUPERUSER_PASSWORD')
\" || true &&
  gunicorn iys_sgd_backend.wsgi:application --bind 0.0.0.0:\${PORT:-8000} --workers 3 --timeout 120
"