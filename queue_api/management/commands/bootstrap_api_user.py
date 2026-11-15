import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from core.secrets import read_secret


class Command(BaseCommand):
    """Cria ou atualiza o usuário inicial da API e seu Token a partir de Docker Secrets."""

    help = "Provisiona usuário padrão e Token DRF lendo secrets sem expor credenciais."

    def handle(self, *args: object, **options: object) -> None:
        username = os.getenv("API_DEMO_USER", "api_student")
        password = read_secret(
            env_var="API_DEMO_PASSWORD",
            file_env_var="API_DEMO_PASSWORD_FILE",
            secret_name="api_demo_password",
            base_dir=settings.BASE_DIR,
        )
        token_key = read_secret(
            env_var="API_AUTH_TOKEN",
            file_env_var="API_AUTH_TOKEN_FILE",
            secret_name="api_auth_token",
            base_dir=settings.BASE_DIR,
        )

        if not password:
            self.stdout.write(
                self.style.WARNING(
                    "API_DEMO_PASSWORD não definido; usuário inicial não alterado."
                )
            )
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(username=username)
        user.set_password(password)
        user.save()

        if token_key:
            Token.objects.filter(user=user).exclude(key=token_key).delete()
            Token.objects.get_or_create(user=user, defaults={"key": token_key})
        else:
            Token.objects.get_or_create(user=user)

        action = "criado" if created else "sincronizado"
        self.stdout.write(
            self.style.SUCCESS(
                f"Usuário '{username}' e token DRF {action} com sucesso."
            )
        )
