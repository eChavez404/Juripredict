"""Auditoria dos acessos feitos com token de API.

Roda DEPOIS da view porque só então o DRF sabe quem é a pessoa e qual token ela usou.
Registra cada consulta (e cada tentativa negada) no log do escritório, o que permite
responder "o que o agente leu, quando e com qual credencial".

Grava só o caminho e os NOMES dos filtros, nunca os valores: uma busca por nome de
cliente não pode virar dado pessoal dentro da própria auditoria.
"""

import logging
import re

from auditlog.services import registrar_evento_auditoria
from organizations.models import MembroEscritorio

from .authentication import e_token_api

logger = logging.getLogger(__name__)

PREFIXO_API = "/api/v1/"
SINGULAR = {"processos": "processo", "eventos": "evento"}
ID_ESCRITORIO = re.compile(r"^[0-9a-fA-F-]{32,36}$")


def _recurso(caminho):
    """``processos/7/andamentos/`` -> (``processo``, ``7``, ``andamentos``)."""
    partes = [p for p in caminho.removeprefix(PREFIXO_API).split("/") if p]
    tipo = SINGULAR.get(partes[0], partes[0]) if partes else "api"
    recurso_id = partes[1] if len(partes) > 1 and partes[1].isdigit() else "lista"
    sub = partes[2] if len(partes) > 2 else ""
    return tipo, recurso_id, sub


class AuditoriaTokenApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resposta = self.get_response(request)
        token = getattr(request, "auth", None)
        if not e_token_api(token):
            token = getattr(request, "token_api_negado", None)
        if e_token_api(token):
            try:
                self._registrar(request, resposta, token)
            except Exception:  # auditar não pode derrubar a resposta já pronta
                logger.exception("Falha ao auditar acesso por token de API")
        return resposta

    def _registrar(self, request, resposta, token):
        usuario = token.usuario
        bruto = request.headers.get("X-Escritorio-ID", "")
        membro = None
        if ID_ESCRITORIO.match(bruto):
            membro = (
                MembroEscritorio.objects.filter(
                    usuario=usuario, escritorio_id=bruto, status=MembroEscritorio.Status.ATIVO
                )
                .select_related("escritorio")
                .first()
            )
        tipo, recurso_id, sub = _recurso(request.path)
        negado = resposta.status_code >= 400
        if membro is None:
            # sem escritório válido não há log de escritório onde gravar
            if negado:
                logger.warning(
                    "Token de API %s: acesso negado sem escritório válido (%s %s, HTTP %s)",
                    token.prefixo, request.method, request.path, resposta.status_code,
                )
            return
        if tipo == "auth":
            return  # a consulta de sessão que o MCP faz para achar o escritório é ruído
        registrar_evento_auditoria(
            escritorio=membro.escritorio,
            ator=usuario,
            acao="token_api.negado" if negado else "token_api.leitura",
            recurso_tipo=tipo,
            recurso_id=recurso_id,
            alteracoes={
                "credencial": token.prefixo,
                "metodo": request.method,
                "caminho": request.path.removeprefix(PREFIXO_API),
                "subrecurso": sub,
                "status": resposta.status_code,
                "filtros": sorted(request.GET.keys()),
            },
        )
