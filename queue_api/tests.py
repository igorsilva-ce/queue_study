import os
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase


class QueueApiTestCase(APITestCase):
    """Testes da API DRF, autenticação por Token, documentação OpenAPI e despacho Celery."""

    def setUp(self) -> None:
        cache.clear()
        self.user_model = get_user_model()
        self.password = "StrongTestPass_2026!"
        self.user = self.user_model.objects.create_user(
            username="tester",
            password=self.password,
        )
        self.token = Token.objects.create(user=self.user)

    def _authenticate(self) -> None:
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_health_check_publico(self) -> None:
        response = self.client.get(reverse("health-check"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "ok")

    def test_openapi_schema_e_swagger_publicos(self) -> None:
        schema_resp = self.client.get(reverse("schema"))
        self.assertEqual(schema_resp.status_code, status.HTTP_200_OK)
        self.assertIn("Queue API", schema_resp.content.decode("utf-8"))

        docs_resp = self.client.get(reverse("swagger-ui"))
        self.assertEqual(docs_resp.status_code, status.HTTP_200_OK)

        redoc_resp = self.client.get(reverse("redoc"))
        self.assertEqual(redoc_resp.status_code, status.HTTP_200_OK)

    def test_endpoint_protegido_exige_token(self) -> None:
        response = self.client.post(
            reverse("task-hello"), {"name": "Igor"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_auth_token_login_valido_e_invalido(self) -> None:
        ok_resp = self.client.post(
            reverse("auth-token"),
            {"username": "tester", "password": self.password},
            format="json",
        )
        self.assertEqual(ok_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(ok_resp.data["token"], self.token.key)

        bad_resp = self.client.post(
            reverse("auth-token"),
            {"username": "tester", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(bad_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("queue_api.views.hello_world.delay")
    def test_enfileirar_hello_world(self, mock_delay: MagicMock) -> None:
        mock_delay.return_value = MagicMock(id="11111111-1111-1111-1111-111111111111")
        self._authenticate()

        response = self.client.post(
            reverse("task-hello"),
            {"name": "Django"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["queue"], "celery")
        self.assertEqual(response.data["status"], "QUEUED")
        mock_delay.assert_called_once_with("Django")

    @patch("queue_api.views.enviar_email_urgente.delay")
    def test_enfileirar_email_alta_prioridade(self, mock_delay: MagicMock) -> None:
        mock_delay.return_value = MagicMock(id="22222222-2222-2222-2222-222222222222")
        self._authenticate()

        response = self.client.post(
            reverse("task-urgent-email"),
            {"destinatario": "igor@exemplo.com", "assunto": "Alerta"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["queue"], "alta_prioridade")
        mock_delay.assert_called_once_with("igor@exemplo.com", "Alerta")

    @patch("queue_api.views.processar_pagamento.delay")
    def test_enfileirar_pagamento(self, mock_delay: MagicMock) -> None:
        mock_delay.return_value = MagicMock(id="33333333-3333-3333-3333-333333333333")
        self._authenticate()

        response = self.client.post(
            reverse("task-payment"),
            {"pedido_id": 42, "falhas_simuladas": 1},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        mock_delay.assert_called_once_with(pedido_id=42, falhas_simuladas=1)

    @patch("queue_api.views.group")
    def test_enfileirar_soma_paralela(self, mock_group: MagicMock) -> None:
        child1 = MagicMock(id="44444444-4444-4444-4444-444444444441")
        child2 = MagicMock(id="44444444-4444-4444-4444-444444444442")
        mock_group_result = MagicMock(
            id="44444444-4444-4444-4444-444444444440",
            results=[child1, child2],
        )
        mock_group.return_value.apply_async.return_value = mock_group_result
        self._authenticate()

        response = self.client.post(
            reverse("workflow-parallel-sum"),
            {"pares": [{"a": 1, "b": 2}, {"a": 5, "b": 5}]},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["group_id"], mock_group_result.id)
        self.assertEqual(len(response.data["children_task_ids"]), 2)
        mock_group_result.save.assert_called_once()

    @patch("queue_api.views.chain")
    def test_enfileirar_pipeline_etl(self, mock_chain: MagicMock) -> None:
        mock_chain.return_value.apply_async.return_value = MagicMock(
            id="55555555-5555-5555-5555-555555555555"
        )
        self._authenticate()

        response = self.client.post(
            reverse("workflow-etl-pipeline"),
            {"fonte": "CSV_Teste"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["status"], "QUEUED")

    @patch("queue_api.views.AsyncResult")
    def test_consultar_status_task_com_cache(
        self, mock_async_result: MagicMock
    ) -> None:
        mock_instance = MagicMock(status="SUCCESS")
        mock_instance.ready.return_value = True
        mock_instance.successful.return_value = True
        mock_instance.failed.return_value = False
        mock_instance.result = "Hello, Django!"
        mock_async_result.return_value = mock_instance
        self._authenticate()

        url = reverse("task-status", args=["abc-123"])
        first_resp = self.client.get(url)
        self.assertEqual(first_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(first_resp.data["status"], "SUCCESS")
        self.assertEqual(first_resp.data["result"], "Hello, Django!")
        self.assertFalse(first_resp.data["cached"])
        self.assertEqual(first_resp.headers["X-Cache"], "MISS")

        # Segunda leitura deve vir do cache sem consultar o AsyncResult novamente
        second_resp = self.client.get(url)
        self.assertEqual(second_resp.status_code, status.HTTP_200_OK)
        self.assertTrue(second_resp.data["cached"])
        self.assertEqual(second_resp.headers["X-Cache"], "HIT")
        self.assertEqual(mock_async_result.call_count, 1)

    def test_catalogo_tasks_cacheado(self) -> None:
        response = self.client.get(reverse("task-catalog"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["cache_ttl_segundos"], 60)
        self.assertIn("alta_prioridade", response.data["filas"])

    def test_bootstrap_api_user_command_com_secret_file(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            pass_file = Path(tmp_dir) / "pass.txt"
            token_file = Path(tmp_dir) / "token.txt"
            pass_file.write_text("BootstrapPass_999!", encoding="utf-8")
            token_file.write_text(
                "0123456789abcdef0123456789abcdef01234567", encoding="utf-8"
            )

            env_overrides = {
                "API_DEMO_USER": "boot_user",
                "API_DEMO_PASSWORD_FILE": str(pass_file),
                "API_AUTH_TOKEN_FILE": str(token_file),
            }
            with patch.dict(os.environ, env_overrides):
                out = StringIO()
                call_command("bootstrap_api_user", stdout=out)

        user = self.user_model.objects.get(username="boot_user")
        self.assertTrue(user.check_password("BootstrapPass_999!"))
        token = Token.objects.get(user=user)
        self.assertEqual(token.key, "0123456789abcdef0123456789abcdef01234567")
