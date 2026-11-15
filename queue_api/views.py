from celery import chain, group
from celery.result import AsyncResult, GroupResult
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.celery import app as celery_app

from .serializers import (
    AuthTokenRequestSerializer,
    AuthTokenResponseSerializer,
    EtlPipelineRequestSerializer,
    GroupQueuedResponseSerializer,
    GroupStatusResponseSerializer,
    HealthResponseSerializer,
    HelloTaskRequestSerializer,
    ParallelSumRequestSerializer,
    PaymentTaskRequestSerializer,
    TaskCatalogResponseSerializer,
    TaskQueuedResponseSerializer,
    TaskStatusResponseSerializer,
    UrgentEmailRequestSerializer,
)
from .tasks import (
    enviar_email_urgente,
    extrair_dados,
    hello_world,
    processar_pagamento,
    salvar_dados,
    somar,
    transformar_dados,
)


def _queued_response(task_id: str, queue: str) -> Response:
    """Padroniza a resposta 202 Accepted ao publicar uma tarefa no RabbitMQ."""
    return Response(
        {"task_id": task_id, "queue": queue, "status": "QUEUED"},
        status=status.HTTP_202_ACCEPTED,
    )


class HealthCheckView(APIView):
    """Endpoint público para verificação de saúde (healthcheck) do serviço Django."""

    permission_classes = (AllowAny,)

    @extend_schema(
        tags=["Sistema"],
        summary="Healthcheck da API",
        responses={200: HealthResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response({"status": "ok", "service": "queue-api"})


class AuthTokenView(APIView):
    """Autentica um usuário Django e retorna seu Token DRF."""

    permission_classes = (AllowAny,)

    @extend_schema(
        tags=["Autenticação"],
        summary="Obter Token de Autenticação",
        description=(
            "Valida usuário e senha no Django (hash PBKDF2) e devolve um Token DRF "
            "para uso no header `Authorization: Token <seu_token>`."
        ),
        request=AuthTokenRequestSerializer,
        responses={
            200: AuthTokenResponseSerializer,
            401: OpenApiResponse(description="Credenciais inválidas."),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = AuthTokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Credenciais inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key})


class HelloTaskView(APIView):
    """Enfileira a tarefa básica Hello World na fila padrão do RabbitMQ."""

    @extend_schema(
        tags=["Tasks"],
        summary="Enfileirar Hello World",
        request=HelloTaskRequestSerializer,
        responses={202: TaskQueuedResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = HelloTaskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        async_result = hello_world.delay(serializer.validated_data["name"])
        return _queued_response(async_result.id, "celery")


class UrgentEmailTaskView(APIView):
    """Enfileira um e-mail urgente na fila dedicada `alta_prioridade`."""

    @extend_schema(
        tags=["Tasks"],
        summary="Enfileirar E-mail Urgente (Alta Prioridade)",
        request=UrgentEmailRequestSerializer,
        responses={202: TaskQueuedResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = UrgentEmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        async_result = enviar_email_urgente.delay(
            serializer.validated_data["destinatario"],
            serializer.validated_data["assunto"],
        )
        return _queued_response(async_result.id, "alta_prioridade")


class PaymentTaskView(APIView):
    """Enfileira processamento de pagamento com simulação de retries automáticos."""

    @extend_schema(
        tags=["Tasks"],
        summary="Enfileirar Pagamento com Retries",
        request=PaymentTaskRequestSerializer,
        responses={202: TaskQueuedResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = PaymentTaskRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        async_result = processar_pagamento.delay(
            pedido_id=serializer.validated_data["pedido_id"],
            falhas_simuladas=serializer.validated_data["falhas_simuladas"],
        )
        return _queued_response(async_result.id, "celery")


class ParallelSumTaskView(APIView):
    """Dispara múltiplas somas em paralelo usando Celery `group`."""

    @extend_schema(
        tags=["Workflows"],
        summary="Executar Somas em Paralelo (Group)",
        request=ParallelSumRequestSerializer,
        responses={202: GroupQueuedResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = ParallelSumRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pares = serializer.validated_data["pares"]
        group_result = group(somar.s(par["a"], par["b"]) for par in pares).apply_async()
        group_result.save()

        return Response(
            {
                "group_id": group_result.id,
                "children_task_ids": [child.id for child in group_result.results],
                "status": "QUEUED",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class EtlPipelineTaskView(APIView):
    """Dispara um pipeline sequencial (Extract -> Transform -> Load) via Celery `chain`."""

    @extend_schema(
        tags=["Workflows"],
        summary="Executar Pipeline ETL Sequencial (Chain)",
        request=EtlPipelineRequestSerializer,
        responses={202: TaskQueuedResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = EtlPipelineRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        pipeline = chain(
            extrair_dados.s(serializer.validated_data["fonte"]),
            transformar_dados.s(),
            salvar_dados.s(),
        )
        async_result = pipeline.apply_async()
        return _queued_response(async_result.id, "celery")


class TaskCatalogView(APIView):
    """Retorna o catálogo de tasks e filas usando cache de página no Redis (60s)."""

    permission_classes = (AllowAny,)

    @method_decorator(cache_page(60))
    @extend_schema(
        tags=["Monitoramento"],
        summary="Catálogo de Filas e Tasks (Cacheado no Redis)",
        description=(
            "Demonstra o decorator `@cache_page(60)` do Django armazenando a resposta "
            "completa no Redis (DB 1) por 60 segundos."
        ),
        responses={200: TaskCatalogResponseSerializer},
    )
    def get(self, request: Request) -> Response:
        return Response(
            {
                "cache_ttl_segundos": 60,
                "filas": ["celery", "alta_prioridade"],
                "tasks": [
                    {
                        "nome": "queue_api.tasks.hello_world",
                        "fila": "celery",
                        "endpoint": "/api/tasks/hello/",
                        "descricao": "Tarefa assíncrona básica Hello World.",
                    },
                    {
                        "nome": "queue_api.tasks.enviar_email_urgente",
                        "fila": "alta_prioridade",
                        "endpoint": "/api/tasks/email-urgente/",
                        "descricao": "Roteamento para fila de alta prioridade.",
                    },
                    {
                        "nome": "queue_api.tasks.processar_pagamento",
                        "fila": "celery",
                        "endpoint": "/api/tasks/pagamento/",
                        "descricao": "Simulação de retries automáticos em falhas.",
                    },
                    {
                        "nome": "queue_api.tasks.somar",
                        "fila": "celery",
                        "endpoint": "/api/tasks/workflows/soma-paralela/",
                        "descricao": "Execução paralela com Celery group.",
                    },
                    {
                        "nome": "queue_api.tasks.extrair_dados -> transformar_dados -> salvar_dados",
                        "fila": "celery",
                        "endpoint": "/api/tasks/workflows/pipeline-etl/",
                        "descricao": "Pipeline sequencial ETL com Celery chain.",
                    },
                ],
            }
        )


class TaskStatusView(APIView):
    """Consulta o status e o resultado de uma task usando cache Redis para tasks finalizadas."""

    @extend_schema(
        tags=["Monitoramento"],
        summary="Consultar Status de uma Task (com Cache Redis)",
        description=(
            "Consulta o status no Result Backend (Redis DB 0). Quando a tarefa finaliza, "
            "a resposta é salva no Redis Cache (DB 1) por 5 minutos, retornando header "
            "`X-Cache: HIT` nas leituras seguintes."
        ),
        responses={200: TaskStatusResponseSerializer},
    )
    def get(self, request: Request, task_id: str) -> Response:
        cache_key = f"task_status:{task_id}"
        cached_payload = cache.get(cache_key)
        if cached_payload is not None:
            response = Response({**cached_payload, "cached": True})
            response["X-Cache"] = "HIT"
            return response

        async_result = AsyncResult(task_id, app=celery_app)
        ready = async_result.ready()
        successful = async_result.successful() if ready else None

        result_value = None
        error_value = None
        if ready:
            if async_result.failed():
                error_value = str(async_result.result)
            else:
                result_value = async_result.result

        payload = {
            "task_id": task_id,
            "status": async_result.status,
            "ready": ready,
            "successful": successful,
            "result": result_value,
            "error": error_value,
            "cached": False,
        }
        if ready:
            cache.set(cache_key, payload, timeout=300)

        response = Response(payload)
        response["X-Cache"] = "MISS"
        return response


class GroupStatusView(APIView):
    """Consulta o andamento agregado de um workflow `group` no Redis."""

    @extend_schema(
        tags=["Monitoramento"],
        summary="Consultar Status de um Group",
        responses={
            200: GroupStatusResponseSerializer,
            404: OpenApiResponse(description="Grupo não encontrado no backend."),
        },
    )
    def get(self, request: Request, group_id: str) -> Response:
        group_result = GroupResult.restore(group_id, app=celery_app)
        if group_result is None:
            return Response(
                {"detail": "Grupo não encontrado no result backend."},
                status=status.HTTP_404_NOT_FOUND,
            )

        ready = group_result.ready()
        results = (
            group_result.get(disable_sync_subtasks=False, propagate=False)
            if ready
            else None
        )
        return Response(
            {
                "group_id": group_id,
                "ready": ready,
                "completed_count": group_result.completed_count(),
                "total": len(group_result.results),
                "results": results,
            }
        )
