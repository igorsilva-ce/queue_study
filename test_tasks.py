import unittest

from celery import chain, group
from celery.exceptions import Retry

from tasks import (
    app,
    enviar_email_urgente,
    extrair_dados,
    heartbeat_sistema,
    hello_world,
    processar_pagamento,
    salvar_dados,
    somar,
    transformar_dados,
)


class CeleryTasksTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Executa as tasks de forma síncrona em memória durante os testes unitários
        app.conf.task_always_eager = True
        app.conf.task_eager_propagates = True

    def test_hello_world(self) -> None:
        result = hello_world.delay("Teste")
        self.assertEqual(result.get(), "Hello, Teste!")

    def test_alta_prioridade(self) -> None:
        result = enviar_email_urgente.delay("dev@teste.com", "Alerta")
        self.assertIn("dev@teste.com", result.get())

    def test_retry_disparo_e_recuperacao(self) -> None:
        # Na 1ª tentativa (retries=0) com falhas_simuladas=2, deve acionar Retry
        with self.assertRaises(Retry):
            processar_pagamento.delay(pedido_id=99, falhas_simuladas=2)

        # Na 3ª tentativa (retries=2), o pagamento deve ser aprovado
        result = processar_pagamento.apply(
            kwargs={"pedido_id": 99, "falhas_simuladas": 2},
            retries=2,
        )
        self.assertEqual(
            result.get(),
            "Pagamento do pedido #99 aprovado na tentativa 3!",
        )

    def test_group_paralelo(self) -> None:
        fluxo = group(somar.s(1, 2), somar.s(3, 4))
        self.assertEqual(fluxo.apply_async().get(), [3, 7])

    def test_chain_sequencial(self) -> None:
        fluxo = chain(
            extrair_dados.s("CSV"),
            transformar_dados.s(),
            salvar_dados.s(),
        )
        self.assertEqual(
            fluxo.apply_async().get(),
            "Pipeline concluído para 'CSV' com total=120",
        )

    def test_heartbeat(self) -> None:
        self.assertIn("OK", heartbeat_sistema.delay().get())


if __name__ == "__main__":
    unittest.main()
