web: sh -c "\
  python manage.py migrate --noinput && \
  python manage.py collectstatic --noinput && \
  python manage.py shell -c \"from django.contrib.auth import get_user_model; \
  import os; \
  User = get_user_model(); \
  username=os.environ.get('DJANGO_SUPERUSER_USERNAME'); \
  email=os.environ.get('DJANGO_SUPERUSER_EMAIL'); \
  password=os.environ.get('DJANGO_SUPERUSER_PASSWORD'); \
  User.objects.filter(username=username).exists() or \
  User.objects.create_superuser(username=username, email=email, password=password)\" && \
  gunicorn iys_sgd_backend.wsgi:application --bind 0.0.0.0:$PORT"
