"""Cliente do agente de IA (pasta agente/ na raiz), um serviço interno.

O navegador nunca fala com o agente: passa por aqui, com login, papel e limite de
requisições. O agente não recebe usuário, escritório nem token, só o caso e o segredo.
Só stdlib, como o cliente do DataJud.
"""

import json
from http.client import HTTPException
from urllib import error, request

from django.conf import settings
from rest_framework.exceptions import APIException, NotFound

# Abaixo dos 15 s do frontend. O agente responde na hora: a análise corre depois, por consulta.
TIMEOUT_SEGUNDOS = 10
# Curta, para não prender um worker do gunicorn enquanto o agente liga: quem insiste é a página.
TIMEOUT_OPCOES_SEGUNDOS = 3
NAO_ENCONTRADA = "Análise não encontrada. Envie o caso de novo."


class AgenteIndisponivel(APIException):
    status_code = 502
    default_detail = "O agente de IA não respondeu. Tente novamente mais tarde."


class AgenteNaoConfigurado(APIException):
    status_code = 503
    default_detail = "O agente de IA não está configurado neste ambiente."


class CasoRecusado(APIException):
    status_code = 400
    default_detail = "O agente não aceitou o caso. Confira os campos do formulário."


def _chamar(caminho, corpo=None, timeout=TIMEOUT_SEGUNDOS):
    if not settings.AGENTE_URL or not settings.AGENTE_SEGREDO:
        raise AgenteNaoConfigurado
    requisicao = request.Request(
        f"{settings.AGENTE_URL}/api/v1/{caminho}",
        data=None if corpo is None else json.dumps(corpo).encode(),
        headers={
            "Authorization": f"Bearer {settings.AGENTE_SEGREDO}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(requisicao, timeout=timeout) as resposta:
            return json.loads(resposta.read().decode())
    except error.HTTPError as exc:
        # Sem repassar o corpo: o 422 do agente devolve o que foi enviado, com o relato.
        if exc.code == 422:
            raise CasoRecusado from None
        if exc.code == 404 and caminho.startswith("analyses/"):
            raise NotFound(NAO_ENCONTRADA) from None
        # Segredo diferente nos dois lados, ou endereço errado: esperar não resolve.
        if exc.code in (401, 404):
            raise AgenteNaoConfigurado from None
        raise AgenteIndisponivel from None
    except (OSError, HTTPException, ValueError):
        raise AgenteIndisponivel from None


def _analise(job):
    return {campo: job.get(campo) for campo in ("status", "step", "result", "error")}


def opcoes():
    return _chamar("options", timeout=TIMEOUT_OPCOES_SEGUNDOS)


def iniciar(caso):
    job = _chamar("analyses", {campo: valor for campo, valor in caso.items() if valor})
    return job["job_id"], _analise(job)


def consultar(job_id):
    return _analise(_chamar(f"analyses/{job_id}"))
