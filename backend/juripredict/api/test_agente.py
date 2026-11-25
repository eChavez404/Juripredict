import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

from .test_papeis import PAPEL, PapeisBase, User

RELATO = "Auxiliar de limpeza em banheiros de hospital, com contato diário com lixo hospitalar."
CASO = {"tema": "insalubridade", "fase": "instrucao", "relato": RELATO}
JOB = {"job_id": "a" * 32, "status": "running", "step": "prepare_context", "result": None, "error": None}
ROTA = "/api/v1/agente/analises/"


def falha_http(codigo):
    return HTTPError("http://agente.interno", codigo, "x", None, BytesIO(b'{"detail": "interno"}'))


@override_settings(AGENTE_URL="http://agente.interno:8001", AGENTE_SEGREDO="segredo-de-teste")
class AgenteBase(PapeisBase):
    def setUp(self):
        super().setUp()
        abrir = patch("api.agente.request.urlopen")
        self.abrir = abrir.start()
        self.addCleanup(abrir.stop)
        self.agente_responde(JOB)

    def agente_responde(self, corpo):
        self.abrir.side_effect = lambda *_a, **_k: BytesIO(json.dumps(corpo).encode())

    def iniciar(self, papel=PAPEL.ADVOGADO, **extra):
        return self.como(papel).post(ROTA, {**CASO, **extra}, format="json")


class AcessoTests(AgenteBase):
    def test_estagiario_anonimo_e_token_de_api_nao_chegam_ao_agente(self):
        anonimo = APIClient()
        casos = (
            (self.como(PAPEL.ESTAGIARIO), 403),
            (self.com_token(PAPEL.ADVOGADO), 403),
            (anonimo, 401),
        )
        for cliente, esperado in casos:
            with self.subTest(esperado=esperado):
                self.assertEqual(cliente.get("/api/v1/agente/opcoes/").status_code, esperado)
                self.assertEqual(cliente.post(ROTA, CASO, format="json").status_code, esperado)
                self.assertEqual(cliente.get(f"{ROTA}qualquer/").status_code, esperado)
        self.abrir.assert_not_called()

    def test_advogado_le_as_opcoes_do_agente(self):
        opcoes = {"temas": [{"value": "t", "label": "T"}], "fases": [], "provas": []}
        self.agente_responde(opcoes)

        resposta = self.como(PAPEL.ADVOGADO).get("/api/v1/agente/opcoes/")

        self.assertEqual(resposta.data, opcoes)

    def test_opcoes_desistem_rapido_para_nao_prender_o_backend_enquanto_o_agente_acorda(self):
        self.como(PAPEL.ADVOGADO).get("/api/v1/agente/opcoes/")
        self.assertLessEqual(self.abrir.call_args.kwargs["timeout"], 3)

    def test_pagina_de_espera_do_render_vira_indisponivel(self):
        self.abrir.side_effect = lambda *_a, **_k: BytesIO(b"<html>loading</html>")
        resposta = self.como(PAPEL.ADVOGADO).get("/api/v1/agente/opcoes/")
        self.assertEqual(resposta.status_code, 502)

    def test_sem_url_ou_sem_segredo_fica_desligado(self):
        for vazio in ("AGENTE_URL", "AGENTE_SEGREDO"):
            with self.subTest(vazio), override_settings(**{vazio: ""}):
                self.assertEqual(self.iniciar().status_code, 503)
        self.abrir.assert_not_called()

    def test_ha_limite_de_analises_por_hora(self):
        cache.clear()
        for _ in range(20):
            self.assertEqual(self.iniciar().status_code, 202)
        self.assertEqual(self.iniciar().status_code, 429)


class InicioTests(AgenteBase):
    def test_o_agente_recebe_so_o_caso_e_o_segredo(self):
        self.iniciar(provas=["ppp"], orgao_julgador="", usuario=1, escritorio="x")

        requisicao = self.abrir.call_args.args[0]
        self.assertEqual(requisicao.full_url, "http://agente.interno:8001/api/v1/analyses")
        self.assertEqual(requisicao.get_header("Authorization"), "Bearer segredo-de-teste")
        self.assertEqual(json.loads(requisicao.data), {**CASO, "provas": ["ppp"]})
        self.assertEqual(set(requisicao.headers), {"Authorization", "Content-type"})

    def test_auditoria_registra_o_uso_sem_o_relato(self):
        self.iniciar()

        evento = EventoAuditoria.objects.get(acao="agente.analise_iniciada")
        self.assertEqual(evento.ator, self.usuarios[PAPEL.ADVOGADO])
        self.assertEqual(evento.alteracoes, {"tema": "insalubridade", "fase": "instrucao"})

    def test_relato_curto_ou_longo_demais_nem_sai_do_backend(self):
        for relato in ("curto", "x" * 12001):
            with self.subTest(tamanho=len(relato)):
                self.assertEqual(self.iniciar(relato=relato).status_code, 400)
        self.abrir.assert_not_called()

    def test_falhas_do_agente_nao_vazam_detalhe_nem_endereco(self):
        casos = (
            (falha_http(422), 400),
            (falha_http(401), 503),  # segredo diferente nos dois lados: esperar não resolve
            (falha_http(404), 503),  # endereço sem serviço, como no Render antes de criá-lo
            (falha_http(502), 502),
            (falha_http(503), 502),
            (URLError("agente.interno recusou"), 502),
            (TimeoutError("agente.interno"), 502),
        )
        for falha, esperado in casos:
            with self.subTest(falha=str(falha)):
                self.abrir.side_effect = falha
                resposta = self.iniciar()
                self.assertEqual(resposta.status_code, esperado)
                self.assertEqual(set(resposta.data), {"detail"})
                self.assertNotIn("interno", str(resposta.data))
        self.assertFalse(EventoAuditoria.objects.filter(acao="agente.analise_iniciada").exists())

    def test_resposta_que_nao_e_json_vira_indisponivel(self):
        self.abrir.side_effect = lambda *_a, **_k: BytesIO(b"<html>")
        self.assertEqual(self.iniciar().status_code, 502)


class ConsultaTests(AgenteBase):
    def test_quem_pediu_acompanha_ate_o_resultado(self):
        analise_id = self.iniciar().data["id"]
        self.agente_responde({**JOB, "status": "done", "result": {"x": 1}})

        resposta = self.como(PAPEL.ADVOGADO).get(f"{ROTA}{analise_id}/")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["result"], {"x": 1})
        self.assertNotIn("job_id", resposta.data)
        self.assertTrue(self.abrir.call_args.args[0].full_url.endswith(f"/analyses/{JOB['job_id']}"))

    def test_colega_outro_escritorio_e_id_adulterado_recebem_404(self):
        analise_id = self.iniciar().data["id"]
        advogado = self.usuarios[PAPEL.ADVOGADO]
        outro = Escritorio.objects.create(nome="Outra", criado_por=User.objects.first())
        MembroEscritorio.objects.create(escritorio=outro, usuario=advogado, papel=PAPEL.ADVOGADO)
        no_outro_escritorio = APIClient()
        no_outro_escritorio.force_authenticate(advogado)
        no_outro_escritorio.credentials(HTTP_X_ESCRITORIO_ID=str(outro.pk))
        self.abrir.reset_mock()

        casos = (
            (self.como(PAPEL.OWNER), analise_id),
            (no_outro_escritorio, analise_id),
            (self.como(PAPEL.ADVOGADO), analise_id[:-2] + "xx"),
            (self.como(PAPEL.ADVOGADO), JOB["job_id"]),
        )
        for cliente, tentativa in casos:
            with self.subTest(tentativa=tentativa):
                self.assertEqual(cliente.get(f"{ROTA}{tentativa}/").status_code, 404)
        self.abrir.assert_not_called()

    def test_analise_perdida_no_reinicio_do_agente_vira_404(self):
        analise_id = self.iniciar().data["id"]
        self.abrir.side_effect = falha_http(404)

        resposta = self.como(PAPEL.ADVOGADO).get(f"{ROTA}{analise_id}/")

        self.assertEqual(resposta.status_code, 404)
        self.assertIn("Envie o caso de novo", resposta.data["detail"])
