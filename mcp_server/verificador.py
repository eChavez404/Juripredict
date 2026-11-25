"""Confere, no modo HTTP, se o token recebido foi emitido pelo JuriPredict para este
servidor, perguntando ao servidor de autorização (introspecção, RFC 7662).

A resposta fica num cache curto, para não perguntar a cada chamada. Isso não atrasa a
revogação dos dados: cada consulta das ferramentas passa pela API com o mesmo token, e a
API confere de novo, na hora.
"""

import hashlib
import time

import httpx
from mcp.server.auth.provider import AccessToken

CACHE_VALIDO = 60.0
CACHE_INVALIDO = 10.0
MAX_CACHE = 2000


class _Indisponivel(Exception):
    """O servidor de autorização não respondeu: nega agora, sem guardar a negativa."""


class VerificadorJuriPredict:
    def __init__(self, *, url_introspeccao, segredo, transport=None):
        self._url = url_introspeccao
        self._segredo = segredo
        self._http = httpx.AsyncClient(timeout=10.0, transport=transport)
        self._cache = {}

    async def verify_token(self, token: str) -> AccessToken | None:
        # a chave é o hash: o token em si não fica na memória além do necessário
        chave = hashlib.sha256(token.encode()).hexdigest()
        agora = time.monotonic()
        guardado = self._cache.get(chave)
        if guardado and guardado[0] > agora:
            return guardado[1]
        try:
            acesso = await self._perguntar(token)
        except _Indisponivel:
            return None
        validade = CACHE_VALIDO if acesso else CACHE_INVALIDO
        if acesso and acesso.expires_at:
            validade = min(validade, max(0.0, acesso.expires_at - time.time()))
        if len(self._cache) >= MAX_CACHE:
            self._cache = {k: v for k, v in self._cache.items() if v[0] > agora}
            if len(self._cache) >= MAX_CACHE:
                self._cache.clear()
        self._cache[chave] = (agora + validade, acesso)
        return acesso

    async def _perguntar(self, token):
        try:
            resposta = await self._http.post(
                self._url, data={"token": token}, headers={"Authorization": f"Bearer {self._segredo}"}
            )
        except httpx.HTTPError as exc:
            raise _Indisponivel from exc
        if resposta.status_code != 200:
            raise _Indisponivel
        dados = resposta.json()
        if not dados.get("active"):
            return None
        return AccessToken(
            token=token,
            client_id=dados["client_id"],
            scopes=str(dados.get("scope", "")).split(),
            expires_at=dados.get("exp"),
            resource=dados.get("aud"),
            subject=dados.get("sub"),
            claims={"escritorio_id": dados.get("escritorio_id")},
        )
