# syntax=docker/dockerfile:1
# VeritelexAI backend — one image, two Cloud Run services (VTX_ROLE=api | worker).

FROM python:3.13-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app

FROM python:3.13-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8080
RUN useradd --system --uid 10001 --no-create-home vtx
WORKDIR /app
COPY --from=build --chown=vtx:vtx /app /app
USER vtx
EXPOSE 8080
# Cloud Run terminates TLS; trust its proxy headers only.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
