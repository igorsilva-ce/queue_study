# Queue — Estudos de Django, DRF, Celery, RabbitMQ, Redis e Docker

Projeto prático para estudar arquitetura de APIs REST com **Django** e **Django REST Framework**, processamento assíncrono distribuído com **Celery**, **RabbitMQ** (Broker AMQP) e **Redis** (Result Backend), documentação automática **OpenAPI 3 / Swagger** com **`drf-spectacular`**, e boas práticas de segurança com **Docker Secrets** e containers **não-root**.

---

## Arquitetura do Projeto

```text
Cliente HTTP (Swagger / curl)
       │  Authorization: Token <token>
       ▼
[Django + DRF :8000] ──(AMQP :5672)──► [RabbitMQ] ──► Filas ("celery", "alta_prioridade")
       ▲                                    ▲                         │
       │                                    │                         ▼
       │                             [Celery Beat]             [Celery Worker]
       │                                                              │
       └──────────────(GET /api/tasks/{id}/)────── [Redis :6379] ◄────┘
                                                  (Result Backend)
                                                              │
                                                       [Flower :5555]
```

### Papel de cada tecnologia
- **Django + DRF (`web`)**: Recebe requisições HTTP autenticadas por Token, valida os dados via Serializers, publica as tarefas no RabbitMQ e retorna `202 Accepted` com o `task_id`.
- **drf-spectacular (`/api/docs/` e `/api/redoc/`)**: Gera automaticamente o esquema **OpenAPI 3.0** diretamente dos serializers, views, docstrings e decorators `@extend_schema`. Sempre que você modifica um endpoint ou serializer, a documentação se atualiza na hora.
- **RabbitMQ (`rabbitmq`)**: *Message Broker* (protocolo AMQP). Recebe as mensagens das tasks e distribui entre as filas `celery` e `alta_prioridade`.
- **Celery Worker (`worker`)**: Consome as filas do RabbitMQ e executa as funções Python em background (com retries automáticos, `group` paralelo e `chain` sequencial).
- **Celery Beat (`beat`)**: Agendador periódico que envia a task `heartbeat_sistema` a cada 30 segundos.
- **Redis (`redis`)**: *Result Backend* compartilhado entre os containers. Permite consultar o status e o retorno de qualquer `task_id` ou `group_id` via API (`GET /api/tasks/{task_id}/`).
- **Flower (`flower`)**: Interface web para monitorar workers, filas e histórico de tarefas em tempo real.

---

## Como o Redis funciona neste projeto (Result Backend)

Ao estudar Celery com RabbitMQ, é comum se perguntar: *"Se já tenho o RabbitMQ, por que adicionar o Redis?"*

1. **RabbitMQ (Message Broker) vs. Redis (Result Backend)**:
   - **RabbitMQ** é especializado em **mensageria (AMQP)**: garantir que a tarefa chegue ao Worker certo (`celery` ou `alta_prioridade`) e não se perca caso um worker caia.
   - **Redis** é um banco **chave-valor em memória** extremamente rápido, usado aqui como **Result Backend** para guardar o histórico recente de execução e o valor do `return` das tasks.

2. **Por que não usar apenas `rpc://` no RabbitMQ com Django?**
   - O backend `rpc://` cria filas temporárias e exclusivas por processo cliente. Em uma API HTTP, quem recebe o `POST /api/tasks/hello/` pode não ser o mesmo processo/thread que atende o `GET /api/tasks/{task_id}/`.
   - Com o **Redis compartilhado**, qualquer container (`web`, `worker`, `flower`) lê e grava os resultados pelo mesmo `task_id` ou `group_id`.

3. **Ciclo de vida e chaves armazenadas no Redis** (`core/settings.py`):
   - `CELERY_TASK_TRACK_STARTED = True`: grava o estado `STARTED` no Redis assim que o Worker pega a tarefa.
   - `CELERY_RESULT_EXTENDED = True`: inclui metadados (nome da task, argumentos e fila) no JSON salvo no Redis.
   - `CELERY_RESULT_EXPIRES = 3600`: aplica **TTL de 1 hora** em cada chave, evitando que o Redis cresça indefinidamente em memória.
   - Padrão das chaves criadas:
     - `celery-task-meta-<task_id>` (resultado e estado de uma tarefa individual)
     - `celery-taskset-meta-<group_id>` (estado consolidado de um `group` salvo com `.save()`)
   - **Estados possíveis**: `PENDING` $\rightarrow$ `STARTED` $\rightarrow$ `RETRY` (se houver tentativa repetida) $\rightarrow$ `SUCCESS` ou `FAILURE`.

4. **Segurança e Persistência do Redis no Docker (`docker-compose.yml`)**:
   - Autenticação obrigatória via `--requirepass` lendo o Docker Secret `/run/secrets/redis_password`.
   - Persistência ativada com AOF (`--appendonly yes`) no volume nomeado `redis_data`.
   - Porta `6379` exposta apenas em `127.0.0.1`.

5. **Inspecionando o Redis na prática (para estudos)**:
```powershell
# Listar todas as chaves de tarefas gravadas pelo Celery
docker compose exec redis sh -c 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli KEYS "celery-task*"'

# Ler o JSON completo salvo para uma task específica (substitua pelo task_id)
docker compose exec redis sh -c 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli GET "celery-task-meta-SEU_TASK_ID"'

# Ver quanto tempo falta (TTL em segundos) para a chave expirar automaticamente
docker compose exec redis sh -c 'REDISCLI_AUTH="$(cat /run/secrets/redis_password)" redis-cli TTL "celery-task-meta-SEU_TASK_ID"'
```

---

## Segurança e Armazenamento de Segredos (Pronto para GitHub)

Nenhuma senha, chave secreta ou token está chumbado no código-fonte ou versionado no Git:

1. **Docker Secrets (`/run/secrets/`) + `.env`**:
   - Todos os segredos locais ficam na pasta `secrets/` e no arquivo `.env`, ambos bloqueados no `.gitignore` e `.dockerignore`.
   - O módulo `core/secrets.py` lê automaticamente `/run/secrets/<nome>` dentro dos containers (e `secrets/<nome>.txt` / `.env` localmente).
2. **Tokens e Senhas na API**:
   - Senhas de usuário do Django são armazenadas com hash **PBKDF2** no SQLite (nunca em texto puro).
   - A autenticação nos endpoints de tarefas usa `TokenAuthentication` (`Authorization: Token <token>`).
   - O comando `python manage.py bootstrap_api_user` provisiona automaticamente o usuário inicial e seu token lendo os Docker Secrets na inicialização do container `web`.
3. **Hardening de Containers**:
   - `Dockerfile` cria o usuário não-root `appuser` (`UID/GID 1000`) e executa com `USER appuser`.
   - `docker-compose.yml` aplica `user: "1000:1000"`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, código montado como somente leitura (`:/app:ro`) e portas restritas a `127.0.0.1`.

---

## Configuração Inicial (Antes de Subir o Docker)

1. Copie o arquivo de exemplo para criar seu `.env`:
```powershell
Copy-Item .env.example .env
```

2. Crie os arquivos de segredos na pasta `secrets/` (ajuste as senhas e garanta que `rabbitmq_password.txt` e `redis_password.txt` tenham os mesmos valores definidos no `.env`):
```powershell
New-Item -ItemType Directory -Force -Path secrets | Out-Null
Set-Content -NoNewline -Path secrets/rabbitmq_password.txt -Value "sua_senha_forte_rabbitmq"
Set-Content -NoNewline -Path secrets/redis_password.txt -Value "sua_senha_forte_redis"
Set-Content -NoNewline -Path secrets/django_secret_key.txt -Value "sua_chave_secreta_django_longa_e_aleatoria"
Set-Content -NoNewline -Path secrets/api_demo_password.txt -Value "sua_senha_usuario_api"
Set-Content -NoNewline -Path secrets/api_auth_token.txt -Value "seu_token_hex_40_caracteres"
```
*(Dica: você pode gerar tokens seguros com `uv run python -c "import secrets; print(secrets.token_urlsafe(32))"`.)*

---

## Executando o Ambiente Completo com Docker Compose

### 1. Subir todos os serviços
```powershell
docker compose up -d --build
```

Interfaces disponíveis localmente (`127.0.0.1`):
- **Swagger UI (Documentação interativa da API)**: http://localhost:8000/api/docs/
- **ReDoc**: http://localhost:8000/api/redoc/
- **OpenAPI Schema JSON/YAML**: http://localhost:8000/api/schema/
- **Flower (Monitoramento Celery)**: http://localhost:5555
- **RabbitMQ Management**: http://localhost:15672

### 2. Testando a API autenticada

1. **Obter o Token** (ou usar diretamente o token definido em `secrets/api_auth_token.txt`):
```powershell
curl.exe -X POST http://localhost:8000/api/auth/token/ `
  -H "Content-Type: application/json" `
  -d "{\"username\": \"api_student\", \"password\": \"SUA_SENHA_DE_API_DEMO_PASSWORD\"}"
```

2. **Enfileirar uma tarefa Hello World**:
```powershell
curl.exe -X POST http://localhost:8000/api/tasks/hello/ `
  -H "Authorization: Token SEU_TOKEN_AQUI" `
  -H "Content-Type: application/json" `
  -d "{\"name\": \"Igor\"}"
```
A API responderá `202 Accepted` com um `task_id`.

3. **Consultar o resultado no Redis via API**:
```powershell
curl.exe http://localhost:8000/api/tasks/SEU_TASK_ID_AQUI/ `
  -H "Authorization: Token SEU_TOKEN_AQUI"
```

4. **Testando pelo Swagger UI**:
   - Abra http://localhost:8000/api/docs/.
   - Clique em **Authorize**, digite `Token SEU_TOKEN_AQUI` (ou use `POST /api/auth/token/` para pegar o token) e execute qualquer endpoint diretamente pelo navegador.

### 3. Principais Endpoints Disponíveis
| Método | Rota | Autenticação | Descrição |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/health/` | Pública | Healthcheck da API |
| `POST` | `/api/auth/token/` | Pública | Troca usuário/senha por Token DRF |
| `GET` | `/api/docs/` | Pública | Swagger UI gerado via `drf-spectacular` |
| `POST` | `/api/tasks/hello/` | Token | Enfileira `hello_world` na fila padrão `celery` |
| `POST` | `/api/tasks/email-urgente/` | Token | Enfileira na fila `alta_prioridade` |
| `POST` | `/api/tasks/pagamento/` | Token | Demonstra retries automáticos em falhas |
| `POST` | `/api/tasks/workflows/soma-paralela/` | Token | Dispara `group` paralelo e salva `group_id` |
| `POST` | `/api/tasks/workflows/pipeline-etl/` | Token | Dispara `chain` sequencial (ETL) |
| `GET` | `/api/tasks/{task_id}/` | Token | Consulta status/resultado da task no Redis |
| `GET` | `/api/tasks/groups/{group_id}/` | Token | Consulta status agregado de um `group` |

### 4. Logs e Encerramento
```powershell
# Acompanhar logs em tempo real
docker compose logs -f web worker beat

# Parar os serviços
docker compose down
```

---

## Qualidade de Código, Testes e CI

```powershell
# Lint e formatação (Ruff)
uv run ruff check .
uv run ruff format --check .

# Validação Django e Schema OpenAPI
uv run python manage.py check
uv run python manage.py spectacular --validate --fail-on-warn --file NUL

# Testes Django/DRF e Celery (em memória, sem precisar de broker externo)
uv run python manage.py test
uv run python -m unittest test_tasks.py -v
```
