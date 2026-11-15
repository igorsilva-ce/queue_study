FROM python:3.13-slim

# Copia o binário oficial do uv para instalação rápida
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Cria grupo e usuário sem privilégios de root (UID/GID 1000)
RUN groupadd --system --gid 1000 appgroup \
    && useradd --system --uid 1000 --gid appgroup --create-home --home-dir /home/appuser appuser

# Cria a virtualenv fora de /app para não conflitar com bind mounts do Windows
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Instala as dependências usando o lockfile e prepara o diretório gravável /app/data
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project \
    && mkdir -p /app/data \
    && chown -R appuser:appgroup /opt/venv /app

# Copia o código da aplicação já pertencendo ao usuário sem privilégios
COPY --chown=appuser:appgroup . .

# Remove permissões de administrador (executa como usuário não-root)
USER appuser
