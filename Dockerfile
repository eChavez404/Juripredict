# syntax=docker/dockerfile:1

FROM node:24-alpine AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_URL=/api/v1
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build


FROM python:3.12-slim AS agente-build

# O bytecode vai pronto na imagem: compilar na partida, com 0,1 CPU, atrasaria o agente.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

# O mesmo caminho da imagem final: o ambiente virtual guarda caminhos absolutos.
WORKDIR /srv/agente
RUN python -m pip install --no-cache-dir uv==0.12.15
COPY agente/pyproject.toml agente/uv.lock ./
RUN uv sync --locked --no-dev --python /usr/local/bin/python
COPY agente/app ./app
RUN .venv/bin/python -m compileall -q app


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend-build /build/frontend/dist ./juripredict/frontend_dist
COPY --from=agente-build /srv/agente /srv/agente

WORKDIR /app/backend/juripredict
RUN DJANGO_DEBUG=true \
    DJANGO_SECRET_KEY=collectstatic-build-only \
    FIELD_ENCRYPTION_KEY=collectstatic-build-only \
    python manage.py collectstatic --noinput

# O processo web não precisa de root. Se alguém explorar uma falha na aplicação,
# o estrago fica limitado a um usuário sem privilégios. A pasta de mídia é a
# única que a aplicação grava (uploads, quando o R2 está desligado).
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir -p /app/backend/juripredict/media \
    && chown -R app:app /app/backend/juripredict/media
USER app

EXPOSE 8080

CMD ["sh", "/app/backend/iniciar.sh"]
