from rest_framework import serializers


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField(help_text="Status operacional da API.")
    service = serializers.CharField(help_text="Identificador do serviço.")


class AuthTokenRequestSerializer(serializers.Serializer):
    username = serializers.CharField(help_text="Nome de usuário cadastrado no Django.")
    password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
        help_text="Senha do usuário (verificada contra hash PBKDF2).",
    )


class AuthTokenResponseSerializer(serializers.Serializer):
    token = serializers.CharField(
        help_text="Token DRF para enviar no header 'Authorization: Token <token>'."
    )


class HelloTaskRequestSerializer(serializers.Serializer):
    name = serializers.CharField(
        default="World",
        max_length=100,
        help_text="Nome usado na saudação processada pelo worker.",
    )


class UrgentEmailRequestSerializer(serializers.Serializer):
    destinatario = serializers.EmailField(help_text="E-mail do destinatário.")
    assunto = serializers.CharField(
        max_length=200,
        help_text="Assunto da mensagem roteada para a fila 'alta_prioridade'.",
    )


class PaymentTaskRequestSerializer(serializers.Serializer):
    pedido_id = serializers.IntegerField(
        min_value=1,
        help_text="Identificador numérico do pedido.",
    )
    falhas_simuladas = serializers.IntegerField(
        default=2,
        min_value=0,
        max_value=3,
        help_text="Quantidade de falhas simuladas (0 a 3) para testar retries automáticos.",
    )


class SumPairSerializer(serializers.Serializer):
    a = serializers.IntegerField(help_text="Primeiro operando.")
    b = serializers.IntegerField(help_text="Segundo operando.")


class ParallelSumRequestSerializer(serializers.Serializer):
    pares = SumPairSerializer(
        many=True,
        allow_empty=False,
        help_text="Lista de pares {a, b} que serão somados em paralelo via Celery group.",
    )


class EtlPipelineRequestSerializer(serializers.Serializer):
    fonte = serializers.CharField(
        max_length=100,
        default="API_Vendas",
        help_text="Nome da fonte de dados processada pela chain ETL.",
    )


class TaskQueuedResponseSerializer(serializers.Serializer):
    task_id = serializers.UUIDField(help_text="ID único da tarefa no Celery.")
    queue = serializers.CharField(help_text="Nome da fila RabbitMQ de destino.")
    status = serializers.CharField(
        help_text="Estado inicial após publicação no broker."
    )


class GroupQueuedResponseSerializer(serializers.Serializer):
    group_id = serializers.UUIDField(
        help_text="ID único do grupo de tarefas paralelas."
    )
    children_task_ids = serializers.ListField(
        child=serializers.UUIDField(),
        help_text="IDs individuais das subtarefas executadas em paralelo.",
    )
    status = serializers.CharField(
        help_text="Estado inicial após publicação no broker."
    )


class TaskStatusResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField(help_text="ID da tarefa consultada.")
    status = serializers.CharField(
        help_text="Estado atual no backend (PENDING, STARTED, RETRY, SUCCESS, FAILURE)."
    )
    ready = serializers.BooleanField(help_text="Indica se a tarefa já finalizou.")
    successful = serializers.BooleanField(
        allow_null=True,
        help_text="True se concluiu sem erros, False se falhou, null se pendente.",
    )
    result = serializers.JSONField(
        allow_null=True,
        help_text="Valor retornado pela tarefa quando finalizada com sucesso.",
    )
    error = serializers.CharField(
        allow_null=True,
        help_text="Descrição do erro caso a tarefa tenha falhado.",
    )


class GroupStatusResponseSerializer(serializers.Serializer):
    group_id = serializers.CharField(help_text="ID do grupo consultado.")
    ready = serializers.BooleanField(
        help_text="Indica se todas as subtarefas terminaram."
    )
    completed_count = serializers.IntegerField(
        help_text="Total de subtarefas concluídas."
    )
    total = serializers.IntegerField(
        help_text="Quantidade total de subtarefas no grupo."
    )
    results = serializers.JSONField(
        allow_null=True,
        help_text="Lista consolidada de resultados quando todas as subtarefas terminam.",
    )
