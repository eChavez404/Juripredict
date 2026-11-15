# syntax=docker/dockerfile:1
# Servidor MCP no modo HTTP: o conector remoto, autorizado por OAuth no JuriPredict.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY server.py cliente_api.py verificador.py ./

RUN useradd --system --uid 10001 --no-create-home app
USER app

CMD ["python", "server.py"]
