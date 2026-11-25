#!/bin/sh
# Sobe o site e o agente de IA no mesmo contêiner. Chamado pelo Dockerfile da raiz.
set -e

python manage.py migrate --noinput

# O agente só atende neste contêiner, com um segredo novo a cada partida: não há o que
# configurar, e um valor antigo no painel não atrapalha.
export AGENTE_URL=http://127.0.0.1:8001
AGENTE_SEGREDO="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export AGENTE_SEGREDO

# env -i: o agente recebe só esta lista, sem as chaves do Django nem a do banco (AST06). Vale
# também para o laço que o reinicia se ele cair. Ele só liga depois do primeiro worker do site
# (gunicorn.conf.py): juntos, com 0,1 CPU, atrasariam a volta da hibernação em 20 segundos.
rm -f /tmp/site-pronto
(
    cd /srv/agente
    exec env -i \
        PATH="$PATH" HOME=/tmp PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
        HOST=127.0.0.1 PORT=8001 \
        AGENTE_SEGREDO="$AGENTE_SEGREDO" \
        LLM_MODEL="${LLM_MODEL:-google_genai:gemini-3.8-flash}" \
        GOOGLE_API_KEY="${GOOGLE_API_KEY:-}" \
        EMBEDDING_MODEL="${EMBEDDING_MODEL:-gemini-embedding-2}" \
        EMBEDDING_DIMENSIONS="${EMBEDDING_DIMENSIONS:-768}" \
        PINECONE_API_KEY="${PINECONE_API_KEY:-}" \
        PINECONE_INDEX="${PINECONE_INDEX:-}" \
        PINECONE_NAMESPACE="${PINECONE_NAMESPACE:-}" \
        LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}" \
        LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}" \
        LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-https://us.cloud.langfuse.com}" \
        sh -c 'until [ -e /tmp/site-pronto ]; do sleep 1; done; while :; do .venv/bin/python -m app.main; echo "Agente encerrou; reiniciando em 10 s."; sleep 10; done'
) &

exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 config.wsgi:application
