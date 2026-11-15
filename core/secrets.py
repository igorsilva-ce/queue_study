import os
from pathlib import Path
from urllib.parse import quote


def load_dotenv(base_dir: Path) -> None:
    """Carrega variáveis de um arquivo .env local sem sobrescrever o ambiente atual."""
    env_path = base_dir / ".env"
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def read_secret(
    env_var: str,
    file_env_var: str,
    secret_name: str,
    base_dir: Path,
    default: str = "",
) -> str:
    """Lê segredos priorizando Docker Secrets, arquivo local em secrets/ e variável de ambiente."""
    candidates = [
        os.getenv(file_env_var, ""),
        f"/run/secrets/{secret_name}",
        str(base_dir / "secrets" / f"{secret_name}.txt"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()

    return os.getenv(env_var, default)


def build_broker_url(base_dir: Path) -> str:
    """Monta a URL AMQP do RabbitMQ sem credenciais fixas no código-fonte."""
    if explicit_url := os.getenv("CELERY_BROKER_URL"):
        return explicit_url

    user = quote(os.getenv("RABBITMQ_USER", "celery_user"), safe="")
    password = quote(
        read_secret(
            env_var="RABBITMQ_PASS",
            file_env_var="RABBITMQ_PASS_FILE",
            secret_name="rabbitmq_password",
            base_dir=base_dir,
        ),
        safe="",
    )
    host = os.getenv("RABBITMQ_HOST", "localhost")
    port = os.getenv("RABBITMQ_PORT", "5672")
    return f"amqp://{user}:{password}@{host}:{port}//"


def _build_redis_url(base_dir: Path, db_env_var: str, default_db: str) -> str:
    """Constrói uma URL Redis autenticada para um índice de banco específico."""
    password = quote(
        read_secret(
            env_var="REDIS_PASS",
            file_env_var="REDIS_PASS_FILE",
            secret_name="redis_password",
            base_dir=base_dir,
        ),
        safe="",
    )
    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    db = os.getenv(db_env_var, default_db)
    auth_part = f":{password}@" if password else ""
    return f"redis://{auth_part}{host}:{port}/{db}"


def build_result_backend(base_dir: Path) -> str:
    """Monta a URL do Redis usada como Result Backend compartilhado do Celery (DB 0)."""
    if explicit_backend := os.getenv("CELERY_RESULT_BACKEND"):
        return explicit_backend
    return _build_redis_url(base_dir, db_env_var="REDIS_DB", default_db="0")


def build_cache_url(base_dir: Path) -> str:
    """Monta a URL do Redis usada como Cache do Django e DRF (DB 1)."""
    if explicit_cache := os.getenv("DJANGO_CACHE_URL"):
        return explicit_cache
    return _build_redis_url(base_dir, db_env_var="REDIS_CACHE_DB", default_db="1")
