# Estudos de Python, Celery e RabbitMQ

Projeto prático para estudar mensageria assíncrona com **Python 3.13**, **Celery**, **RabbitMQ** e **Flower**, gerenciado com **uv** e **Docker Compose**.

## Arquitetura do Projeto

```text
[producer.py] ──(AMQP :5672)──► [RabbitMQ] ──► Filas ("celery", "alta_prioridade")
                                    ▲                         │
[Celery Beat] ──(a cada 30s)────────┘                         ▼
                                                       [Celery Worker]
                                                              │
                                                       [Flower :5555]
```

---

## Segurança implementada (Pronto para GitHub)

- **Container sem privilégios de root (`USER appuser`)**: O `Dockerfile` cria um usuário e grupo de sistema (`UID/GID 1000`) sem permissões de administrador.
- **Hardening no Docker Compose**:
  - `security_opt: [no-new-privileges:true]` bloqueia escalação de privilégios.
  - `cap_drop: [ALL]` remove todas as Linux capabilities desnecessárias dos containers Python.
  - Volumes montados como somente leitura (`:/app:ro`).
  - Portas expostas apenas na interface local (`127.0.0.1`), impedindo acesso externo na rede local.
- **Gerenciamento de Segredos (Docker Secrets + `.env`)**:
  - Nenhuma senha está fixa no código ou no `docker-compose.yml`.
  - O arquivo `.env` e a pasta `secrets/` estão no `.gitignore` e `.dockerignore`.
  - Os containers `worker`, `beat` e `flower` leem a senha montada via **Docker Secrets** em `/run/secrets/rabbitmq_password`.

---

## Configuração Inicial de Segredos

1. Copie o arquivo de exemplo para criar seu `.env` local:
```powershell
Copy-Item .env.example .env
```
2. Crie o arquivo de secret do Docker com a mesma senha configurada em `RABBITMQ_PASS`:
```powershell
New-Item -ItemType Directory -Force -Path secrets | Out-Null
Set-Content -NoNewline -Path secrets/rabbitmq_password.txt -Value "sua_senha_forte_aqui"
```

---

## Como Executar (Via Docker Compose)

### 1. Subir todos os serviços (RabbitMQ + Worker + Beat + Flower)
```powershell
docker compose up -d --build
```

Painéis web disponíveis localmente:
- **RabbitMQ Management**: http://localhost:15672 (credenciais definidas no seu `.env`)
- **Flower (Monitoramento do Celery)**: http://localhost:5555

### 2. Disparar as tarefas de teste
```powershell
uv run python producer.py
```

Para acompanhar os logs do Worker e do Beat em tempo real:
```powershell
docker compose logs -f worker beat
```

### 3. Parar os serviços
```powershell
docker compose down
```

---

## Qualidade de Código e Testes

```powershell
# Executar testes unitários (modo eager)
uv run python -m unittest -v

# Verificar lint e formatação com Ruff
uv run ruff check .
uv run ruff format --check .
```
