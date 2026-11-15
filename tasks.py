"""Módulo de compatibilidade que reexporta a instância Celery e as tasks do Django."""

from core.celery import app
from queue_api.tasks import (
    enviar_email_urgente,
    extrair_dados,
    heartbeat_sistema,
    hello_world,
    processar_pagamento,
    salvar_dados,
    somar,
    transformar_dados,
)

__all__ = [
    "app",
    "enviar_email_urgente",
    "extrair_dados",
    "heartbeat_sistema",
    "hello_world",
    "processar_pagamento",
    "salvar_dados",
    "somar",
    "transformar_dados",
]
