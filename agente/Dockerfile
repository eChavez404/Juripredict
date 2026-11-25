# syntax=docker/dockerfile:1
# Agente de IA: serviço interno, chamado só pelo backend com o AGENTE_SEGREDO.
FROM python:3.12-slim

# O bytecode vai pronto na imagem: compilar na partida, com 0,1 CPU, atrasaria a volta da hibernação.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    HOST=0.0.0.0 \
    PORT=8001

WORKDIR /srv
RUN python -m pip install --no-cache-dir uv==0.12.15
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app ./app
RUN .venv/bin/python -m compileall -q app

RUN useradd --system --uid 10001 --no-create-home app
USER app

# Um processo só: os jobs ficam na memória dele.
CMD [".venv/bin/python", "-m", "app.main"]
