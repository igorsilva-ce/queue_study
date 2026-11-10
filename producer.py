from celery import chain, group

from tasks import (
    enviar_email_urgente,
    extrair_dados,
    hello_world,
    processar_pagamento,
    salvar_dados,
    somar,
    transformar_dados,
)


def main() -> None:
    print("=== 1. Hello World Básico ===")
    res_hello = hello_world.delay("World")
    print(f"Task ID: {res_hello.id} -> Retorno: {res_hello.get(timeout=10)}\n")

    print("=== 2. Múltiplas Filas (Alta Prioridade) ===")
    res_email = enviar_email_urgente.delay("igor@exemplo.com", "Código de acesso: 9482")
    print(f"Fila 'alta_prioridade' -> Retorno: {res_email.get(timeout=10)}\n")

    print("=== 3. Retries Automáticos (Tolerância a Falhas) ===")
    res_pagto = processar_pagamento.delay(pedido_id=101, falhas_simuladas=2)
    print(f"Aguardando retries... -> Retorno: {res_pagto.get(timeout=15)}\n")

    print("=== 4. Workflow Group (Execução em Paralelo) ===")
    tarefas_paralelas = group(somar.s(2, 3), somar.s(10, 20), somar.s(50, 50))
    res_group = tarefas_paralelas.apply_async()
    print(f"Resultados paralelos: {res_group.get(timeout=10)}\n")

    print("=== 5. Workflow Chain (Pipeline Sequencial ETL) ===")
    pipeline = chain(
        extrair_dados.s("API_Vendas"),
        transformar_dados.s(),
        salvar_dados.s(),
    )
    res_chain = pipeline.apply_async()
    print(f"Resultado final da Chain: {res_chain.get(timeout=10)}")


if __name__ == "__main__":
    main()
