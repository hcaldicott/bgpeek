# syntax=docker/dockerfile:1.7
#
# bgpeek — multi-stage build with uv.
# Final image: ~150 MB, non-root, tini, alpine.

# ===== Stage 1: build venv with uv =====
FROM python:3.12-alpine AS builder

RUN apk add --no-cache \
      build-base \
      linux-headers \
      libffi-dev \
      openssl-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY pyproject.toml uv.lock* README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null \
      || uv pip install --python /opt/venv/bin/python --no-cache -r pyproject.toml

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --python /opt/venv/bin/python --no-cache --no-deps -e .

# ===== Stage 2: runtime =====
FROM python:3.12-alpine AS runtime

RUN apk add --no-cache \
      libffi \
      openssl \
      ca-certificates \
      tini \
    && addgroup -g 1000 bgpeek \
    && adduser -u 1000 -G bgpeek -s /bin/sh -D bgpeek

WORKDIR /app

COPY --from=builder --chown=bgpeek:bgpeek /opt/venv /opt/venv
COPY --from=builder --chown=bgpeek:bgpeek /app/src /app/src
COPY --chown=bgpeek:bgpeek pyproject.toml README.md ./
COPY --chown=bgpeek:bgpeek migrations ./migrations

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BGPEEK_HOST=0.0.0.0 \
    BGPEEK_PORT=8000

EXPOSE 8000

USER bgpeek

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python3", "-m", "bgpeek.main"]
