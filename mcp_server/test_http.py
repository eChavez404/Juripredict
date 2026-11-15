"""Modo HTTP com OAuth: o servidor só atende com token emitido para ele, e as ferramentas
consultam a API com o token e o escritório de quem autorizou."""

import asyncio
import time
import unittest
from urllib.parse import parse_qs

import httpx
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.transport_security import TransportSecuritySettings
from starlette.testclient import TestClient

import server
from verificador import VerificadorJuriPredict

EMISSOR = "https://app.exemplo.invalid"
URL_MCP = "http://testserver/mcp"
SEGREDO = "segredo-de-introspeccao"
ESC = "22222222-2222-2222-2222-222222222222"
TOKEN = "jp_token-oauth-de-teste"
ACEITA = {"Accept": "application/json, text/event-stream"}


def _introspeccao(aud=URL_MCP):
    """Servidor de autorização de mentira: só conhece TOKEN, emitido para ``aud``."""
    chamadas = []

    def tratar(request):
        chamadas.append(request)
        if request.headers.get("Authorization") != f"Bearer {SEGREDO}":
            return httpx.Response(401)
        token = parse_qs(request.content.decode())["token"][0]
        if token != TOKEN:
            return httpx.Response(200, json={"active": False})
        return httpx.Response(200, json={
            "active": True, "client_id": "claude", "scope": "leitura", "sub": "1",
            "exp": int(time.time()) + 3600, "aud": aud, "escritorio_id": ESC,
        })

    return httpx.MockTransport(tratar), chamadas


def _verificador(**extra):
    transporte, chamadas = _introspeccao(**extra)
    verificador = VerificadorJuriPredict(
        url_introspeccao=f"{EMISSOR}/oauth/introspeccao", segredo=SEGREDO, transport=transporte
    )
    return verificador, chamadas


def _rpc(metodo, params=None, id_=1):
    return {"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params or {}}


class VerificadorTests(unittest.TestCase):
    def test_token_valido_vira_acesso_com_recurso_e_escritorio_e_fica_em_cache(self):
        verificador, chamadas = _verificador()

        acesso = asyncio.run(verificador.verify_token(TOKEN))
        asyncio.run(verificador.verify_token(TOKEN))

        self.assertEqual((acesso.client_id, acesso.scopes, acesso.resource), ("claude", ["leitura"], URL_MCP))
        self.assertEqual(acesso.claims["escritorio_id"], ESC)
        self.assertEqual(len(chamadas), 1)

    def test_token_desconhecido_e_servidor_fora_do_ar_negam(self):
        verificador, _ = _verificador()
        self.assertIsNone(asyncio.run(verificador.verify_token("jp_outro")))

        def fora_do_ar(request):
            raise httpx.ConnectError("sem rede")

        caido = VerificadorJuriPredict(
            url_introspeccao=f"{EMISSOR}/oauth/introspeccao", segredo=SEGREDO,
            transport=httpx.MockTransport(fora_do_ar),
        )
        self.assertIsNone(asyncio.run(caido.verify_token(TOKEN)))
        self.assertEqual(caido._cache, {})  # a negativa por queda não fica guardada


class ServidorHttpTests(unittest.TestCase):
    def _app(self, **extra):
        verificador, _ = _verificador(**extra)
        opcoes = server.autenticacao_oauth(url_mcp=URL_MCP, emissor=EMISSOR, segredo=SEGREDO)
        opcoes["token_verifier"] = verificador
        return server.criar_servidor(**opcoes).streamable_http_app(
            stateless_http=True,
            json_response=True,
            transport_security=TransportSecuritySettings(allowed_hosts=["testserver"]),
        )

    def setUp(self):
        self.consultas = []

        def api(request):
            self.consultas.append(request)
            return httpx.Response(200, json={"urgentes": 1})

        server._http = httpx.Client(base_url="http://api/api/v1/", transport=httpx.MockTransport(api))

    def tearDown(self):
        server._http = None

    def test_publica_os_metadados_apontando_para_o_juripredict(self):
        with TestClient(self._app()) as cliente:
            dados = cliente.get("/.well-known/oauth-protected-resource/mcp").json()

        self.assertEqual(dados["resource"], URL_MCP)
        self.assertEqual([url.rstrip("/") for url in dados["authorization_servers"]], [EMISSOR])
        self.assertEqual(dados["scopes_supported"], ["leitura"])

    def test_sem_token_responde_401_com_o_caminho_dos_metadados(self):
        with TestClient(self._app()) as cliente:
            resposta = cliente.post("/mcp", json=_rpc("tools/list"), headers=ACEITA)

        self.assertEqual(resposta.status_code, 401)
        self.assertIn("resource_metadata", resposta.headers["www-authenticate"])
        self.assertEqual(self.consultas, [])

    def test_token_emitido_para_outro_recurso_e_recusado(self):
        with TestClient(self._app(aud="https://outro.exemplo.invalid/mcp")) as cliente:
            resposta = cliente.post(
                "/mcp", json=_rpc("tools/list"), headers={**ACEITA, "Authorization": f"Bearer {TOKEN}"}
            )

        self.assertEqual(resposta.status_code, 401)

    def test_ferramenta_consulta_a_api_com_o_token_e_o_escritorio_de_quem_autorizou(self):
        # o cliente MCP do próprio SDK, como um cliente real, falando com o app em memória
        async def conversar():
            app = self._app()
            async with app.router.lifespan_context(app):
                async with httpx2.AsyncClient(
                    transport=httpx2.ASGITransport(app=app),
                    headers={"Authorization": f"Bearer {TOKEN}"},
                ) as http:
                    async with streamable_http_client(URL_MCP, http_client=http) as (leitura, escrita):
                        async with ClientSession(leitura, escrita) as sessao:
                            await sessao.initialize()
                            ferramentas = await sessao.list_tools()
                            return ferramentas, await sessao.call_tool("pendencias", {})

        ferramentas, resultado = asyncio.run(conversar())

        self.assertEqual(len(ferramentas.tools), len(server.FERRAMENTAS))
        self.assertFalse(resultado.is_error, resultado)
        self.assertIn("urgentes", resultado.content[0].text)
        consulta = self.consultas[-1]
        self.assertEqual(consulta.url.path, "/api/v1/pendencias/")
        self.assertEqual(consulta.headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(consulta.headers["X-Escritorio-ID"], ESC)

if __name__ == "__main__":
    unittest.main()
