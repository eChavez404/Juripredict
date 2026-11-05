import json
import unittest

import httpx

import server
from cliente_api import ClienteApi, ErroApi

ESC = "11111111-1111-1111-1111-111111111111"
TOKEN = "jp_token-super-secreto-123"


def _api(rotas, *, escritorio=ESC):
    """Cliente contra uma API de mentira. `rotas` mapeia 'GET caminho' -> resposta."""
    chamadas = []

    def tratar(request):
        chamadas.append(request)
        resposta = rotas[f"{request.method} {request.url.path}"]
        if callable(resposta):
            resposta = resposta(request)
        if isinstance(resposta, httpx.Response):
            return resposta
        return httpx.Response(200, json=resposta)

    cliente = ClienteApi(
        base_url="http://api/api/v1", token=TOKEN, escritorio_id=escritorio,
        transport=httpx.MockTransport(tratar),
    )
    cliente.chamadas = chamadas
    return cliente


LOGIN = {}  # token de API: não há login nem renovação


class ClienteApiTests(unittest.TestCase):
    def test_manda_o_token_e_o_escritorio_em_cada_consulta_sem_fazer_login(self):
        api = _api({"GET /api/v1/processos/": []})

        api.get("processos/")
        api.get("processos/")

        self.assertEqual(len(api.chamadas), 2)
        for consulta in api.chamadas:
            self.assertEqual(consulta.headers["Authorization"], f"Bearer {TOKEN}")
            self.assertEqual(consulta.headers["X-Escritorio-ID"], ESC)
            self.assertEqual(consulta.method, "GET")

    def test_token_recusado_explica_como_gerar_outro_sem_repetir_o_token(self):
        api = _api({"GET /api/v1/processos/": httpx.Response(401, text=TOKEN)})

        with self.assertRaises(ErroApi) as contexto:
            api.get("processos/")

        self.assertIn("revogado", str(contexto.exception))
        self.assertIn("Acesso por agentes", str(contexto.exception))
        self.assertNotIn(TOKEN, str(contexto.exception))
        self.assertEqual(len(api.chamadas), 1)  # sem repetir em laço

    def test_escritorio_unico_e_descoberto_pela_sessao(self):
        sessao = {"memberships": [
            {"status": "ATIVO", "escritorio": {"id": ESC}},
            {"status": "SUSPENSO", "escritorio": {"id": "outro"}},
        ]}
        api = _api({"GET /api/v1/auth/me/": sessao, "GET /api/v1/processos/": []}, escritorio=None)

        api.get("processos/")

        self.assertEqual(api.chamadas[-1].headers["X-Escritorio-ID"], ESC)
        # a descoberta do escritório não pode mandar o cabeçalho que ainda não existe
        me = next(c for c in api.chamadas if c.url.path.endswith("/auth/me/"))
        self.assertNotIn("X-Escritorio-ID", me.headers)

    def test_varios_escritorios_exigem_escolha_explicita(self):
        sessao = {"memberships": [
            {"status": "ATIVO", "escritorio": {"id": "a"}}, {"status": "ATIVO", "escritorio": {"id": "b"}},
        ]}
        api = _api({"GET /api/v1/auth/me/": sessao}, escritorio=None)

        with self.assertRaisesRegex(ErroApi, "JURIPREDICT_ESCRITORIO_ID"):
            api.get("processos/")

    def test_erros_da_api_viram_mensagens_sem_vazar_o_token(self):
        for status, trecho in ((404, "Não encontrado"), (403, "Sem permissão"),
                               (429, "Limite de requisições"), (500, "HTTP 500")):
            with self.subTest(status=status):
                api = _api({"GET /api/v1/processos/": httpx.Response(status, text=TOKEN)})
                with self.assertRaises(ErroApi) as contexto:
                    api.get("processos/")
                self.assertIn(trecho, str(contexto.exception))
                for proibido in (TOKEN, "http://api"):
                    self.assertNotIn(proibido, str(contexto.exception))

    def test_falha_de_rede_vira_erro_amigavel(self):
        def cair(request):
            raise httpx.ConnectError(f"conexão recusada em http://api com {TOKEN}")

        api = ClienteApi(base_url="http://api/api/v1", token=TOKEN,
                         escritorio_id=ESC, transport=httpx.MockTransport(cair))

        with self.assertRaises(ErroApi) as contexto:
            api.get("processos/")
        self.assertNotIn(TOKEN, str(contexto.exception))

    def test_parametros_vazios_nao_vao_para_a_url(self):
        api = _api({"GET /api/v1/processos/": []})

        api.get("processos/", {"q": "", "status": None, "x": "1"})

        self.assertEqual(dict(api.chamadas[-1].url.params), {"x": "1"})

    def test_ambiente_incompleto_diz_o_que_falta(self):
        import os
        antigos = {k: os.environ.pop(k, None) for k in ("JURIPREDICT_API_URL", "JURIPREDICT_TOKEN")}
        try:
            with self.assertRaisesRegex(ErroApi, "JURIPREDICT_API_URL.*JURIPREDICT_TOKEN"):
                ClienteApi.do_ambiente()
        finally:
            for k, v in antigos.items():
                if v is not None:
                    os.environ[k] = v


class FerramentasTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, server, "_cliente", None)

    def _usar(self, rotas):
        server._cliente = _api({**LOGIN, **rotas})

    def test_processos_nao_expoem_link_de_arquivo_nem_id_do_escritorio(self):
        self._usar({"GET /api/v1/processos/": [{
            "id": 1, "numero_cnj": "x", "escritorio": ESC,
            "arquivo_peticao_inicial_url": "https://r2/assinado?sig=abc",
        }]})

        saida = server.listar_processos()

        self.assertEqual(saida["itens"], [{"id": 1, "numero_cnj": "x"}])

    def test_busca_e_status_viajam_como_filtros(self):
        self._usar({"GET /api/v1/processos/": []})

        server.listar_processos(busca="silva", status="ATIVO")

        params = dict(server._cliente.chamadas[-1].url.params)
        self.assertEqual(params, {"q": "silva", "status": "ATIVO"})

    def test_lista_longa_e_cortada_e_informa_o_total(self):
        self._usar({"GET /api/v1/processos/": [{"id": i} for i in range(300)]})

        padrao = server.listar_processos()
        teto = server.listar_processos(limite=10_000)

        self.assertEqual((padrao["total"], padrao["exibidos"]), (300, server.LIMITE_PADRAO))
        self.assertEqual(teto["exibidos"], server.LIMITE_MAXIMO)

    def test_documentos_nao_expoem_o_link_do_arquivo(self):
        self._usar({"GET /api/v1/processos/7/documentos/": [
            {"id": 1, "nome": "a.pdf", "tamanho": 5, "url": "https://r2/assinado"},
        ]})

        self.assertEqual(
            server.documentos_do_processo(7)["itens"], [{"id": 1, "nome": "a.pdf", "tamanho": 5}]
        )

    def test_andamentos_trazem_a_data_da_leitura(self):
        self._usar({"GET /api/v1/processos/7/andamentos/": {
            "sincronizado_em": "2024-01-01T00:00:00Z", "andamentos": [{"id": 1, "nome": "Juntada"}],
        }})

        saida = server.andamentos_do_processo(7)

        self.assertEqual(saida["sincronizado_em"], "2024-01-01T00:00:00Z")
        self.assertEqual(saida["itens"], [{"id": 1, "nome": "Juntada"}])

    def test_id_do_processo_e_forcado_a_inteiro_e_nao_vira_caminho(self):
        self._usar({})

        with self.assertRaises(ValueError):
            server.andamentos_do_processo("../../auth/me")

    def test_agenda_jurimetria_e_resumo_repassam_a_resposta_da_api(self):
        self._usar({
            "GET /api/v1/eventos/": [{"id": 1}],
            "GET /api/v1/jurimetria/": {"taxa_favoravel": None},
            "GET /api/v1/dashboard/": {"total": 3},
        })

        self.assertEqual(server.agenda("2024-01-01", "2024-01-31")["itens"], [{"id": 1}])
        self.assertIsNone(server.jurimetria()["taxa_favoravel"])
        self.assertEqual(server.resumo_do_escritorio(), {"total": 3})
        params = dict(next(c for c in server._cliente.chamadas if "eventos" in c.url.path).url.params)
        self.assertEqual(params, {"inicio": "2024-01-01", "fim": "2024-01-31"})

    def test_jurimetria_repassa_os_filtros_e_omite_os_vazios(self):
        self._usar({"GET /api/v1/jurimetria/": {"taxa_favoravel": None}})

        server.jurimetria(area="CIVEL")

        self.assertEqual(dict(server._cliente.chamadas[-1].url.params), {"area": "CIVEL"})

    def test_processos_da_jurimetria_mantem_o_total_informado_pela_api(self):
        self._usar({"GET /api/v1/jurimetria/processos/": {
            "total": 500, "exibidos": 200, "processos": [{"id": i} for i in range(200)],
        }})

        saida = server.processos_da_jurimetria(vara="1ª Vara", limite=10)

        self.assertEqual((saida["total"], saida["exibidos"]), (500, 10))

    def test_pendencias_repassa_a_resposta_da_api(self):
        self._usar({"GET /api/v1/pendencias/": {"urgentes": 2}})

        self.assertEqual(server.pendencias(), {"urgentes": 2})

    def test_calcular_prazo_envia_cada_suspensao_como_parametro_repetido(self):
        self._usar({"GET /api/v1/prazos/calcular/": {"vencimento": "2026-04-09"}})

        saida = server.calcular_prazo("2026-03-30", 5, suspensoes=["2026-04-01", "2026-04-02"])

        self.assertEqual(saida["vencimento"], "2026-04-09")
        self.assertEqual(
            server._cliente.chamadas[-1].url.params.get_list("suspensoes"),
            ["2026-04-01", "2026-04-02"],
        )

    def test_erro_da_api_chega_ao_agente_com_a_mensagem_e_nao_como_falha_generica(self):
        import asyncio

        from mcp import Client

        self._usar({"GET /api/v1/processos/9/andamentos/": httpx.Response(404)})

        async def chamar():
            async with Client(server.mcp) as c:
                return await c.call_tool("andamentos_do_processo", {"processo_id": 9})

        resultado = asyncio.run(chamar())

        self.assertTrue(resultado.is_error)
        self.assertIn("Não encontrado neste escritório", resultado.content[0].text)

    def test_so_ha_ferramentas_de_leitura_e_todas_declaram_isso(self):
        import asyncio
        ferramentas = asyncio.run(server.mcp.list_tools())

        self.assertGreaterEqual(len(ferramentas), 6)
        for f in ferramentas:
            with self.subTest(ferramenta=f.name):
                self.assertTrue(f.annotations.read_only_hint)
                self.assertFalse(f.annotations.destructive_hint)

    def test_nenhuma_chamada_usa_metodo_de_escrita(self):
        self._usar({
            "GET /api/v1/processos/": [], "GET /api/v1/eventos/": [],
            "GET /api/v1/jurimetria/": {}, "GET /api/v1/dashboard/": {},
            "GET /api/v1/processos/1/andamentos/": {"sincronizado_em": None, "andamentos": []},
            "GET /api/v1/processos/1/documentos/": [],
        })

        server.listar_processos(); server.agenda(); server.jurimetria(); server.resumo_do_escritorio()
        server.andamentos_do_processo(1); server.documentos_do_processo(1)

        metodos = {c.method for c in server._cliente.chamadas}
        self.assertEqual(metodos, {"GET"})


if __name__ == "__main__":
    unittest.main()
