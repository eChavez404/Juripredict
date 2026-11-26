import json
import tempfile
import zipfile
from datetime import timedelta
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from xml.sax.saxutils import escape

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

from .models import CasoEstudo, Cliente, DocumentoProcesso, MensagemCaso, Processo
from .test_papeis import PAPEL, PapeisBase, User

RELATO = "Auxiliar de limpeza em banheiros de hospital, com contato diário com lixo hospitalar."
CASO = {"tema": "insalubridade", "fase": "instrucao", "relato": RELATO, "provas": ["ppp"]}
ROTA = "/api/v1/agente/casos/"
JOB = {"job_id": "a" * 32, "status": "running", "step": "prepare_context", "result": None, "error": None}
MEDIA = tempfile.mkdtemp(prefix="juripredict-test-media-")


def resultado(indice=58, potencial=83, titulo="Limpeza hospitalar"):
    return {
        "analise": {"titulo": titulo, "resposta": "Falta a prova técnica; requeira a perícia."},
        "medicao": {"indice_atual": indice, "indice_potencial": potencial, "ganho": potencial - indice},
        "casos": [],
    }


def falha_http(codigo):
    return HTTPError("http://agente.interno", codigo, "x", None, BytesIO(b'{"detail": "interno"}'))


def pdf(texto):
    """Um PDF de uma página com `texto`, montado à mão (com xref) para não depender de gerador."""
    conteudo = f"BT /F1 12 Tf 72 712 Td ({texto}) Tj ET".encode()
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(conteudo), conteudo),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    saida = BytesIO()
    saida.write(b"%PDF-1.4\n")
    posicoes = []
    for numero, objeto in enumerate(objetos, start=1):
        posicoes.append(saida.tell())
        saida.write(b"%d 0 obj\n%s\nendobj\n" % (numero, objeto))
    xref = saida.tell()
    saida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1))
    for posicao in posicoes:
        saida.write(b"%010d 00000 n \n" % posicao)
    saida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref))
    return saida.getvalue()


def docx(*paragrafos):
    saida = BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        corpo = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(p)}</w:t></w:r></w:p>' for p in paragrafos)
        arquivo.writestr("word/document.xml", f"<w:document><w:body>{corpo}</w:body></w:document>")
    return saida.getvalue()


@override_settings(AGENTE_URL="http://agente.interno:8001", AGENTE_SEGREDO="segredo-de-teste")
class AgenteBase(PapeisBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        abrir = patch("api.agente.request.urlopen")
        self.abrir = abrir.start()
        self.addCleanup(abrir.stop)
        self.agente_responde(JOB)
        self.api = self.como(PAPEL.ADVOGADO)

    def agente_responde(self, corpo):
        self.abrir.side_effect = lambda *_a, **_k: BytesIO(json.dumps(corpo).encode())

    def pedidos_ao_agente(self):
        """Só os envios de caso: as consultas de andamento não têm corpo."""
        return [c.args[0] for c in self.abrir.call_args_list if c.args[0].data is not None]

    def criar(self, **extra):
        return self.api.post(ROTA, {**CASO, **extra}, format="json")

    def concluir(self, caso_id, **campos):
        self.agente_responde({**JOB, "status": "done", "result": resultado(**campos)})
        return self.api.get(f"{ROTA}{caso_id}/").data


class AcessoTests(AgenteBase):
    def test_estagiario_anonimo_e_token_de_api_nao_chegam_ao_agente(self):
        for cliente, esperado in (
            (self.como(PAPEL.ESTAGIARIO), 403),
            (self.com_token(PAPEL.ADVOGADO), 403),
            (APIClient(), 401),
        ):
            with self.subTest(esperado=esperado):
                self.assertEqual(cliente.get("/api/v1/agente/opcoes/").status_code, esperado)
                self.assertEqual(cliente.get(ROTA).status_code, esperado)
                self.assertEqual(cliente.post(ROTA, CASO, format="json").status_code, esperado)
        self.abrir.assert_not_called()

    def test_opcoes_vem_do_agente(self):
        opcoes = {"ia_configurada": True, "base_configurada": False, "temas": [], "fases": [], "provas": []}
        self.agente_responde(opcoes)
        self.assertEqual(self.api.get("/api/v1/agente/opcoes/").data, opcoes)

    def test_opcoes_desistem_rapido_para_nao_prender_o_backend_enquanto_o_agente_liga(self):
        self.api.get("/api/v1/agente/opcoes/")
        self.assertLessEqual(self.abrir.call_args.kwargs["timeout"], 3)

    def test_sem_url_ou_sem_segredo_nada_e_gravado(self):
        for vazio in ("AGENTE_URL", "AGENTE_SEGREDO"):
            with self.subTest(vazio), override_settings(**{vazio: ""}):
                self.assertEqual(self.criar().status_code, 503)
        self.assertFalse(CasoEstudo.objects.exists())

    def test_ha_limite_de_mensagens_por_hora(self):
        for _ in range(20):
            self.assertEqual(self.criar().status_code, 201)
            MensagemCaso.objects.filter(status="pendente").update(status="concluida")
        self.assertEqual(self.criar().status_code, 429)


class ConversaTests(AgenteBase):
    def test_criar_caso_envia_so_o_caso_e_guarda_a_conversa(self):
        resposta = self.criar(usuario=1, escritorio="x")

        self.assertEqual(resposta.status_code, 201)
        pedido = self.pedidos_ao_agente()[0]
        self.assertTrue(pedido.full_url.endswith("/api/v1/analyses"))
        self.assertEqual(pedido.get_header("Authorization"), "Bearer segredo-de-teste")
        self.assertEqual(
            json.loads(pedido.data),
            {"tema": "insalubridade", "fase": "instrucao", "relato": RELATO, "provas": ["ppp"]},
        )
        mensagens = resposta.data["mensagens"]
        self.assertEqual([(m["autor"], m["status"]) for m in mensagens], [("advogado", "concluida"), ("agente", "pendente")])
        self.assertEqual(resposta.data["etapa"], "prepare_context")
        self.assertNotIn("job_id", json.dumps(resposta.data))
        evento = EventoAuditoria.objects.get(acao="agente.caso_criado")
        self.assertEqual(evento.alteracoes, {"tema": "insalubridade", "fase": "instrucao", "processo": None})

    def test_ao_concluir_grava_resposta_indices_e_titulo(self):
        caso_id = self.criar().data["id"]

        dados = self.concluir(caso_id)

        agente = dados["mensagens"][-1]
        self.assertEqual(agente["status"], "concluida")
        self.assertEqual(agente["texto"], "Falta a prova técnica; requeira a perícia.")
        self.assertEqual((agente["indice_atual"], agente["indice_potencial"]), (58, 83))
        self.assertEqual(dados["titulo"], "Limpeza hospitalar")
        self.assertIsNone(dados["etapa"])
        self.assertEqual(self.api.get(ROTA).data[0]["indice_atual"], 58)

    def test_nova_mensagem_reanalisa_o_caso_inteiro_e_responde_a_ela(self):
        caso_id = self.criar().data["id"]
        self.concluir(caso_id)
        self.agente_responde(JOB)

        resposta = self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "Juntamos o laudo pericial favorável."}, format="json")

        self.assertEqual(resposta.status_code, 201)
        corpo = json.loads(self.pedidos_ao_agente()[-1].data)
        self.assertIn(RELATO, corpo["relato"])
        self.assertIn("Informação acrescentada pelo advogado: Juntamos o laudo pericial favorável.", corpo["relato"])
        self.assertEqual(corpo["mensagem"], "Juntamos o laudo pericial favorável.")
        dados = self.concluir(caso_id, indice=83, potencial=92)
        self.assertEqual([m["indice_atual"] for m in dados["mensagens"] if m["autor"] == "agente"], [58, 83])
        self.assertEqual(EventoAuditoria.objects.filter(acao="agente.mensagem_enviada").count(), 1)

    def test_nao_aceita_mensagem_com_analise_em_andamento(self):
        caso_id = self.criar().data["id"]

        resposta = self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "Mais um fato."}, format="json")

        self.assertEqual(resposta.status_code, 400)
        self.assertEqual(MensagemCaso.objects.filter(autor="advogado").count(), 1)

    def test_atualizar_fase_e_provas_vale_para_a_proxima_mensagem(self):
        caso_id = self.criar().data["id"]
        self.concluir(caso_id)
        self.api.patch(f"{ROTA}{caso_id}/", {"fase": "recurso", "provas": ["laudo_pericial"]}, format="json")
        self.agente_responde(JOB)

        self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "Sentença saiu."}, format="json")

        corpo = json.loads(self.pedidos_ao_agente()[-1].data)
        self.assertEqual((corpo["fase"], corpo["provas"]), ("recurso", ["laudo_pericial"]))

    def test_erro_ou_perda_da_analise_fica_registrado_e_libera_nova_mensagem(self):
        casos = (
            ({**JOB, "status": "error", "error": "A chave do provedor de IA não está configurada."}, "chave do provedor"),
            (falha_http(404), "se perdeu"),
        )
        for resposta_do_agente, esperado in casos:
            with self.subTest(esperado):
                caso_id = self.criar().data["id"]
                if isinstance(resposta_do_agente, dict):
                    self.agente_responde(resposta_do_agente)
                else:
                    self.abrir.side_effect = resposta_do_agente
                agente = self.api.get(f"{ROTA}{caso_id}/").data["mensagens"][-1]
                self.assertEqual(agente["status"], "erro")
                self.assertIn(esperado, agente["erro"])
                self.agente_responde(JOB)
                nova = self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "De novo."}, format="json")
                self.assertEqual(nova.status_code, 201)

    def test_agente_sem_resposta_mantem_pendente_ate_a_espera_maxima(self):
        caso_id = self.criar().data["id"]
        self.abrir.side_effect = URLError("agente ligando")

        self.assertEqual(self.api.get(f"{ROTA}{caso_id}/").data["mensagens"][-1]["status"], "pendente")
        MensagemCaso.objects.update(criado_em=timezone.now() - timedelta(minutes=11))
        agente = self.api.get(f"{ROTA}{caso_id}/").data["mensagens"][-1]
        self.assertEqual(agente["status"], "erro")
        self.assertIn("demorou", agente["erro"])

    def test_recusa_do_agente_nao_deixa_caso_pela_metade(self):
        for falha, esperado in ((falha_http(422), 400), (falha_http(503), 502), (URLError("x"), 502)):
            with self.subTest(esperado=esperado):
                self.abrir.side_effect = falha
                resposta = self.criar()
                self.assertEqual(resposta.status_code, esperado)
                self.assertEqual(set(resposta.data), {"detail"})
                self.assertNotIn("interno", str(resposta.data))
        self.assertFalse(CasoEstudo.objects.exists())
        self.assertFalse(MensagemCaso.objects.exists())

    def test_relato_curto_ou_caso_longo_demais(self):
        self.assertEqual(self.criar(relato="curto").status_code, 400)
        caso_id = self.criar().data["id"]
        self.concluir(caso_id)
        for _ in range(5):
            MensagemCaso.objects.create(caso_id=caso_id, autor="advogado", texto="x" * 4000)
        resposta = self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "y" * 3000}, format="json")
        self.assertEqual(resposta.status_code, 400)
        self.assertIn("20 mil", str(resposta.data))


class EscritorioTests(AgenteBase):
    def test_colega_ve_outro_escritorio_nao_e_excluir_audita(self):
        caso_id = self.criar().data["id"]
        self.assertEqual(self.como(PAPEL.OWNER).get(f"{ROTA}{caso_id}/").status_code, 200)

        advogado = self.usuarios[PAPEL.ADVOGADO]
        outro = Escritorio.objects.create(nome="Outra", criado_por=User.objects.first())
        MembroEscritorio.objects.create(escritorio=outro, usuario=advogado, papel=PAPEL.ADVOGADO)
        no_outro = APIClient()
        no_outro.force_authenticate(advogado)
        no_outro.credentials(HTTP_X_ESCRITORIO_ID=str(outro.pk))
        self.assertEqual(no_outro.get(f"{ROTA}{caso_id}/").status_code, 404)
        self.assertEqual(no_outro.get(ROTA).data, [])

        self.assertEqual(self.api.delete(f"{ROTA}{caso_id}/").status_code, 204)
        self.assertFalse(MensagemCaso.objects.exists())
        self.assertTrue(EventoAuditoria.objects.filter(acao="agente.caso_excluido").exists())


@override_settings(MEDIA_ROOT=MEDIA)
class ProcessoVinculadoTests(AgenteBase):
    def setUp(self):
        super().setUp()
        self.cliente.nome = "Maria das Graças Sousa"
        self.cliente.save()
        self.processo.parte_contraria = "Hospital Santa Luzia"
        self.processo.titulo = "Maria x Hospital"
        self.processo.vara = "Vara do Trabalho de Balsas"
        self.processo.observacoes = "Trabalhou na limpeza do centro cirúrgico."
        self.processo.save()

    def anexar(self, nome, conteudo):
        DocumentoProcesso.objects.create(
            processo=self.processo, nome=nome, tamanho=len(conteudo),
            arquivo=SimpleUploadedFile(nome, conteudo),
        )

    def test_documentos_e_cadastro_entram_sem_cliente_parte_valor_nem_nome_de_arquivo(self):
        self.anexar("contrato Maria.docx", docx("CONTRATO DE TRABALHO", "Função: auxiliar de limpeza hospitalar."))
        self.anexar("laudo.pdf", pdf("Laudo pericial: insalubridade em grau maximo"))
        self.anexar("antigo.doc", b"\xd0\xcf\x11\xe0 sem texto legivel")
        self.anexar("quebrado.pdf", b"%PDF-1.4 truncado")

        resposta = self.criar(processo=self.processo.pk)

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.data["processo"], self.processo.pk)
        relato = json.loads(self.pedidos_ao_agente()[0].data)["relato"]
        for presente in (RELATO, "Vara do Trabalho de Balsas", "centro cirúrgico", "auxiliar de limpeza hospitalar",
                         "Laudo pericial: insalubridade em grau maximo"):
            self.assertIn(presente, relato)
        for ausente in ("Maria", "Hospital Santa Luzia", "12345", "contrato Maria", "laudo.pdf", self.processo.numero_cnj):
            self.assertNotIn(ausente, relato)
        lidos = resposta.data["mensagens"][0]["documentos_lidos"]
        self.assertEqual(
            {d["nome"]: d["situacao"] for d in lidos},
            {"contrato Maria.docx": "lido", "laudo.pdf": "lido", "antigo.doc": "sem texto", "quebrado.pdf": "sem texto"},
        )
        evento = EventoAuditoria.objects.get(acao="agente.caso_criado")
        self.assertEqual(evento.alteracoes["processo"], self.processo.pk)

    def test_documento_longo_entra_em_parte_e_os_seguintes_ficam_fora(self):
        self.anexar("depois.docx", docx("ficou de fora"))
        self.anexar("longo.docx", docx("x" * 20000))

        lidos = self.criar(processo=self.processo.pk).data["mensagens"][0]["documentos_lidos"]

        self.assertEqual(lidos, [{"nome": "longo.docx", "situacao": "lido em parte"}, {"nome": "depois.docx", "situacao": "fora do limite"}])
        relato = json.loads(self.pedidos_ao_agente()[0].data)["relato"]
        self.assertLessEqual(len(relato), 20000)
        self.assertNotIn("ficou de fora", relato)

    def test_vincular_depois_vale_para_a_proxima_mensagem_e_so_processo_do_escritorio(self):
        caso_id = self.criar().data["id"]
        self.concluir(caso_id)
        outro = Escritorio.objects.create(nome="Outra", criado_por=User.objects.first())
        cliente = Cliente.objects.create(escritorio=outro, usuario=User.objects.first(), nome="Y", cpf_cnpj="")
        alheio = Processo.objects.create(
            escritorio=outro, cliente=cliente, numero_cnj="0000002-00.2024.5.16.0001", vara="V", comarca="C",
            parte_contraria="Z",
        )

        self.assertEqual(self.criar(processo=alheio.pk).status_code, 400)
        recusa = self.api.patch(f"{ROTA}{caso_id}/", {"processo": alheio.pk}, format="json")
        self.assertEqual(recusa.status_code, 400)
        self.assertIn("inválido", str(recusa.data))

        self.assertEqual(self.api.patch(f"{ROTA}{caso_id}/", {"processo": self.processo.pk}, format="json").status_code, 200)
        self.agente_responde(JOB)
        self.api.post(f"{ROTA}{caso_id}/mensagens/", {"texto": "Vinculei o processo."}, format="json")
        self.assertIn("centro cirúrgico", json.loads(self.pedidos_ao_agente()[-1].data)["relato"])
