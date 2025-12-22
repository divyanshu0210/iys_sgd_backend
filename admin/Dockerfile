FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ../ ./

CMD python manage.py migrate && \
    python manage.py collectstatic --noinput && \
    gunicorn iys_sgd_backend.wsgi_admin:application \
    --bind 0.0.0.0:8080 \
    --workers 1 \
    --threads 2 \
    --timeout 120
