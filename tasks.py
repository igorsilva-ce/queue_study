import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from celery import Celery, Task
from kombu import Queue

BASE_DIR = Path(__file__).resolve().parent


def _carregar_dotenv() -> None:
    """Carrega variáveis do arquivo .env local caso ainda não estejam no ambiente."""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _obter_senha_broker() -> str:
    """Prioriza Docker Secrets (/run/secrets/...) -> arquivo local de secret -> variável de ambiente."""
    secret_file = os.getenv("RABBITMQ_PASS_FILE", "/run/secrets/rabbitmq_password")
    secret_path = Path(secret_file)
    if secret_path.is_file():
        return secret_path.read_text(encoding="utf-8").strip()

    local_secret = BASE_DIR / "secrets" / "rabbitmq_password.txt"
    if local_secret.is_file():
        return local_secret.read_text(encoding="utf-8").strip()

    return os.getenv("RABBITMQ_PASS", "")


def _construir_broker_url() -> str:
    """Monta a URL AMQP sem expor credenciais fixas no código-fonte."""
    _carregar_dotenv()
    if explicit_url := os.getenv("CELERY_BROKER_URL"):
        return explicit_url

    user = quote(os.getenv("RABBITMQ_USER", "celery_user"), safe="")
    password = quote(_obter_senha_broker(), safe="")
    host = os.getenv("RABBITMQ_HOST", "localhost")
    port = os.getenv("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@{host}:{port}//"


BROKER_URL = _construir_broker_url()
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

app = Celery(
    "hello_tasks",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

# Configuração de múltiplas filas e agendamentos periódicos (Celery Beat)
app.conf.update(
    task_default_queue="celery",
    task_queues=(
        Queue("celery"),
        Queue("alta_prioridade"),
    ),
    beat_schedule={
        "heartbeat-a-cada-30-segundos": {
            "task": "tasks.heartbeat_sistema",
            "schedule": 30.0,
        },
    },
    timezone="America/Sao_Paulo",
)


# 1. Conceito Básico: Tarefa assíncrona simples
@app.task
def hello_world(name: str) -> str:
    print(f"[Worker] Tarefa recebida para '{name}'. Processando...")
    time.sleep(1)
    mensagem = f"Hello, {name}!"
    print(f"[Worker] Tarefa finalizada: {mensagem}")
    return mensagem


# 2. Retries Automáticos: Resiliência contra falhas temporárias
@app.task(bind=True, max_retries=3)
def processar_pagamento(self: Task, pedido_id: int, falhas_simuladas: int = 2) -> str:
    tentativa = self.request.retries + 1
    print(f"[Worker] Processando pedido #{pedido_id} (Tentativa {tentativa})...")

    if self.request.retries < falhas_simuladas:
        erro = ConnectionError(f"Gateway indisponível na tentativa {tentativa}")
        print(f"[Worker] Erro: {erro}. Reagendando retry em 1s...")
        raise self.retry(exc=erro, countdown=1)

    resultado = f"Pagamento do pedido #{pedido_id} aprovado na tentativa {tentativa}!"
    print(f"[Worker] {resultado}")
    return resultado


# 3. Múltiplas Filas: Roteamento dedicado para tarefas urgentes
@app.task(queue="alta_prioridade")
def enviar_email_urgente(destinatario: str, assunto: str) -> str:
    mensagem = f"E-mail urgente enviado para {destinatario}: '{assunto}'"
    print(f"[Worker - Alta Prioridade] {mensagem}")
    return mensagem


# 4. Workflows (Canvas): Tarefas combináveis com group (paralelo) e chain (sequencial)
@app.task
def somar(a: int, b: int) -> int:
    resultado = a + b
    print(f"[Worker] Calculando {a} + {b} = {resultado}")
    return resultado


@app.task
def extrair_dados(fonte: str) -> dict[str, Any]:
    print(f"[Worker - Chain 1/3] Extraindo dados de '{fonte}'...")
    return {"fonte": fonte, "valores": [10, 20, 30]}


@app.task
def transformar_dados(dados: dict[str, Any]) -> dict[str, Any]:
    print("[Worker - Chain 2/3] Transformando dados...")
    valores_dobrados = [v * 2 for v in dados["valores"]]
    return {**dados, "valores": valores_dobrados, "total": sum(valores_dobrados)}


@app.task
def salvar_dados(dados: dict[str, Any]) -> str:
    resumo = f"Pipeline concluído para '{dados['fonte']}' com total={dados['total']}"
    print(f"[Worker - Chain 3/3] {resumo}")
    return resumo


# 5. Celery Beat: Tarefa periódica disparada automaticamente pelo agendador
@app.task
def heartbeat_sistema() -> str:
    status = "Sistema operacional - verificação periódica OK"
    print(f"[Worker - Beat] {status}")
    return status
