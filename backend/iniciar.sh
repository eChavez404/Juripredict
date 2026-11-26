#!/bin/sh
# Sobe tudo no mesmo contêiner: nginx (porta pública), site, agente de IA e servidor MCP.
# Só o nginx é acessível de fora. Chamado pelo Dockerfile da raiz.
set -e

python manage.py migrate --noinput

segredo() { python -c 'import secrets; print(secrets.token_urlsafe(32))'; }

# Endereços internos e segredos novos a cada partida: não há o que configurar, e um valor
# antigo no painel da hospedagem não atrapalha.
AGENTE_URL=http://127.0.0.1:8001
AGENTE_SEGREDO="$(segredo)"
OAUTH_SEGREDO_INTROSPECCAO="$(segredo)"
export AGENTE_URL AGENTE_SEGREDO OAUTH_SEGREDO_INTROSPECCAO

# O endereço público do site é também o do conector MCP e o do emissor dos tokens.
BASE="${FRONTEND_URL:-${RENDER_EXTERNAL_HOSTNAME:+https://$RENDER_EXTERNAL_HOSTNAME}}"
BASE="${BASE%/}"
if [ -n "$BASE" ]; then
    OAUTH_EMISSOR="$BASE"
    OAUTH_RECURSOS="$BASE/mcp"
    export OAUTH_EMISSOR OAUTH_RECURSOS
fi
# O MCP consulta a API por dentro, sem sair para a internet.
DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:+$DJANGO_ALLOWED_HOSTS,}127.0.0.1"
export DJANGO_ALLOWED_HOSTS

# env -i: cada processo recebe só a própria lista, sem as chaves do Django nem a do banco
# (AST06). Eles só ligam depois do primeiro worker do site (gunicorn.conf.py): juntos, com
# 0,1 CPU, atrasariam a volta da hibernação.
rm -f /tmp/site-pronto
LIMPO="env -i PATH=$PATH HOME=/tmp PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1"
MANTER="sh /app/backend/manter.sh"

sed "s/__PORTA__/${PORT:-8080}/" /app/backend/nginx.conf > /tmp/nginx.conf
$LIMPO $MANTER nginx -e stderr -c /tmp/nginx.conf &

(
    cd /srv/agente
    exec $LIMPO \
        HOST=127.0.0.1 PORT=8001 \
        AGENTE_SEGREDO="$AGENTE_SEGREDO" \
        LLM_MODEL="${LLM_MODEL:-google_genai:gemini-3.5-flash-lite}" \
        LLM_FALLBACK_MODEL="${LLM_FALLBACK_MODEL:-google_genai:gemini-3.1-flash-lite}" \
        GOOGLE_API_KEY="${GOOGLE_API_KEY:-}" \
        EMBEDDING_MODEL="${EMBEDDING_MODEL:-gemini-embedding-2}" \
        EMBEDDING_DIMENSIONS="${EMBEDDING_DIMENSIONS:-768}" \
        PINECONE_API_KEY="${PINECONE_API_KEY:-}" \
        PINECONE_INDEX="${PINECONE_INDEX:-}" \
        PINECONE_NAMESPACE="${PINECONE_NAMESPACE:-}" \
        LANGFUSE_PUBLIC_KEY="${LANGFUSE_PUBLIC_KEY:-}" \
        LANGFUSE_SECRET_KEY="${LANGFUSE_SECRET_KEY:-}" \
        LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-https://us.cloud.langfuse.com}" \
        $MANTER .venv/bin/python -m app.main
) &

if [ -n "$BASE" ]; then
    (
        cd /srv/mcp
        exec $LIMPO \
            HOST=127.0.0.1 PORT=8002 \
            JURIPREDICT_MCP_URL="$BASE/mcp" \
            JURIPREDICT_EMISSOR="$BASE" \
            JURIPREDICT_API_URL=http://127.0.0.1:8000/api/v1 \
            JURIPREDICT_INTROSPECCAO_URL=http://127.0.0.1:8000/oauth/introspeccao \
            JURIPREDICT_SEGREDO_INTROSPECCAO="$OAUTH_SEGREDO_INTROSPECCAO" \
            $MANTER .venv/bin/python server.py
    ) &
fi

exec gunicorn --bind 127.0.0.1:8000 --workers "${WEB_CONCURRENCY:-2}" --timeout 60 config.wsgi:application
