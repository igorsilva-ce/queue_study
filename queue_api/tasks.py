import time
from typing import Any

from celery import Task, shared_task


# 1. Conceito Básico: Tarefa assíncrona simples
@shared_task
def hello_world(name: str) -> str:
    """Simula uma tarefa simples em background retornando uma saudação."""
    print(f"[Worker] Tarefa recebida para '{name}'. Processando...")
    time.sleep(1)
    mensagem = f"Hello, {name}!"
    print(f"[Worker] Tarefa finalizada: {mensagem}")
    return mensagem


# 2. Retries Automáticos: Resiliência contra falhas temporárias
@shared_task(bind=True, max_retries=3)
def processar_pagamento(self: Task, pedido_id: int, falhas_simuladas: int = 2) -> str:
    """Processa um pagamento com reenvio automático em falhas temporárias."""
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
@shared_task(queue="alta_prioridade")
def enviar_email_urgente(destinatario: str, assunto: str) -> str:
    """Envia uma notificação roteada para a fila de alta prioridade."""
    mensagem = f"E-mail urgente enviado para {destinatario}: '{assunto}'"
    print(f"[Worker - Alta Prioridade] {mensagem}")
    return mensagem


# 4. Workflows (Canvas): Tarefas combináveis com group (paralelo) e chain (sequencial)
@shared_task
def somar(a: int, b: int) -> int:
    """Soma dois inteiros para demonstração de execução paralela com group."""
    resultado = a + b
    print(f"[Worker] Calculando {a} + {b} = {resultado}")
    return resultado


@shared_task
def extrair_dados(fonte: str) -> dict[str, Any]:
    """Primeira etapa do pipeline ETL (Extract)."""
    print(f"[Worker - Chain 1/3] Extraindo dados de '{fonte}'...")
    return {"fonte": fonte, "valores": [10, 20, 30]}


@shared_task
def transformar_dados(dados: dict[str, Any]) -> dict[str, Any]:
    """Segunda etapa do pipeline ETL (Transform)."""
    print("[Worker - Chain 2/3] Transformando dados...")
    valores_dobrados = [v * 2 for v in dados["valores"]]
    return {**dados, "valores": valores_dobrados, "total": sum(valores_dobrados)}


@shared_task
def salvar_dados(dados: dict[str, Any]) -> str:
    """Terceira etapa do pipeline ETL (Load)."""
    resumo = f"Pipeline concluído para '{dados['fonte']}' com total={dados['total']}"
    print(f"[Worker - Chain 3/3] {resumo}")
    return resumo


# 5. Celery Beat: Tarefa periódica disparada automaticamente pelo agendador
@shared_task
def heartbeat_sistema() -> str:
    """Tarefa periódica disparada automaticamente pelo Celery Beat."""
    status = "Sistema operacional - verificação periódica OK"
    print(f"[Worker - Beat] {status}")
    return status
