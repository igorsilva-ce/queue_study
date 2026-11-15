from celery import chain, group
from celery.result import AsyncResult, GroupResult
from django.contrib.auth import authenticate
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


class TaskStatusView(APIView):
    """Consulta o status e o resultado de uma task pelo seu `task_id` no Redis."""

    @extend_schema(
        tags=["Monitoramento"],
        summary="Consultar Status de uma Task",
        responses={200: TaskStatusResponseSerializer},
    )
    def get(self, request: Request, task_id: str) -> Response:
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

        return Response(
            {
                "task_id": task_id,
                "status": async_result.status,
                "ready": ready,
                "successful": successful,
                "result": result_value,
                "error": error_value,
            }
        )


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
