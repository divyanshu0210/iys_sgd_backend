# your_app/management/__init__.py          (empty file)
# your_app/management/commands/__init__.py  (empty file)
# your_app/management/commands/create_superuser.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

User = get_user_model()

class Command(BaseCommand):
    help = 'Create a superuser non-interactively if it does not exist'

    def handle(self, *args, **options):
        if not User.objects.filter(is_superuser=True).exists():
            username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
            email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
            password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')

            if not password:
                self.stdout.write(self.style.ERROR('Error: DJANGO_SUPERUSER_PASSWORD is not set'))
                return

            User.objects.create_superuser(
                username=username,
                email=email,
                password=password
            )
            self.stdout.write(self.style.SUCCESS(f'Superuser created: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS('Superuser already exists'))