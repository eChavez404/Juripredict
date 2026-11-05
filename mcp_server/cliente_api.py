"""Cliente HTTP da API do JuriPredict, com um token de API do próprio usuário.

O servidor MCP não toca o banco nem reimplementa regra nenhuma: tudo passa pela API,
então o agente enxerga exatamente o que o usuário enxerga (escritório, limites de
requisição), e cada consulta entra na auditoria do escritório. O token só dá leitura,
em rotas fixas, e é revogável no app a qualquer momento.
"""

import os

import httpx
from mcp.server.mcpserver.exceptions import ToolError

TIMEOUT = 30.0


class ErroApi(ToolError):
    """Falha com mensagem segura para o agente: nunca traz token ou URL.

    É um ``ToolError``: o SDK entrega a mensagem ao agente. Qualquer outra exceção
    chegaria só como "Error executing tool", sem dizer o que houve.
    """


class ClienteApi:
    def __init__(self, *, base_url, token, escritorio_id=None, transport=None):
        self._token = token
        self._escritorio_id = escritorio_id or None
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/", timeout=TIMEOUT, transport=transport
        )

    @classmethod
    def do_ambiente(cls):
        faltando = [
            nome for nome in ("JURIPREDICT_API_URL", "JURIPREDICT_TOKEN")
            if not os.environ.get(nome)
        ]
        if faltando:
            raise ErroApi("Variáveis de ambiente ausentes: " + ", ".join(faltando))
        return cls(
            base_url=os.environ["JURIPREDICT_API_URL"],
            token=os.environ["JURIPREDICT_TOKEN"],
            escritorio_id=os.environ.get("JURIPREDICT_ESCRITORIO_ID"),
        )

    def _escolher_escritorio(self):
        """Sem escritório configurado, só vale se a conta tiver exatamente um ativo."""
        sessao = self._requisitar("auth/me/", com_escritorio=False)
        ativos = [
            m["escritorio"]["id"]
            for m in sessao.get("memberships", [])
            if m.get("status") == "ATIVO"
        ]
        if len(ativos) != 1:
            raise ErroApi(
                "A conta pertence a mais de um escritório (ou a nenhum): "
                "defina JURIPREDICT_ESCRITORIO_ID."
            )
        self._escritorio_id = str(ativos[0])

    def _requisitar(self, caminho, *, params=None, com_escritorio=True):
        cabecalhos = {"Authorization": f"Bearer {self._token}"}
        if com_escritorio:
            cabecalhos["X-Escritorio-ID"] = self._escritorio_id
        try:
            resposta = self._http.get(caminho, params=params, headers=cabecalhos)
        except httpx.HTTPError as exc:
            raise ErroApi("Não foi possível falar com a API do JuriPredict.") from exc
        if resposta.status_code == 401:
            raise ErroApi(
                "Token recusado: está inválido, expirado ou foi revogado. "
                "Gere outro em Configurações > Acesso por agentes."
            )
        if resposta.status_code == 404:
            raise ErroApi("Não encontrado neste escritório.")
        if resposta.status_code == 403:
            raise ErroApi("Sem permissão para esta consulta.")
        if resposta.status_code == 429:
            raise ErroApi("Limite de requisições atingido. Tente novamente mais tarde.")
        if resposta.status_code >= 400:
            raise ErroApi(f"A API recusou a consulta (HTTP {resposta.status_code}).")
        return resposta.json()

    def get(self, caminho, params=None):
        if self._escritorio_id is None:
            self._escolher_escritorio()
        limpos = {k: v for k, v in (params or {}).items() if v not in (None, "")}
        return self._requisitar(caminho, params=limpos)
