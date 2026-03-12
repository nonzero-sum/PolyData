FROM python:3.14-alpine
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONPATH=/app/src

RUN apk add --no-cache \
    build-base \
    git \
    gdal-dev \
    geos-dev \
    proj-dev

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

ENTRYPOINT ["sh", "/app/entrypoint.sh"]
CMD ["uv", "run", "--no-sync", "gunicorn", "--bind", ":8000", "main.wsgi:application", "--workers", "8", "--timeout", "0"]