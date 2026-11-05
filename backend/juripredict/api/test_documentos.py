import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

from .models import Cliente, DocumentoProcesso, Processo

PDF = b"%PDF-1.4 conteudo"
MEDIA = tempfile.mkdtemp(prefix="juripredict-test-media-")


def _pdf(nome="prova.pdf", conteudo=PDF):
    return SimpleUploadedFile(nome, conteudo, content_type="application/pdf")


@override_settings(MEDIA_ROOT=MEDIA)
class DocumentosProcessoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="a", email="a@x.com", password="x", first_name="Ana")
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.user)
        MembroEscritorio.objects.create(escritorio=self.escritorio, usuario=self.user, papel="OWNER")
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=self.user, nome="C", cpf_cnpj="x"
        )
        self.processo = self._processo()
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.cabecalho = {"HTTP_X_ESCRITORIO_ID": str(self.escritorio.pk)}

    def _processo(self, escritorio=None, cliente=None, numero="0000001-00.2024.5.16.0001"):
        return Processo.objects.create(
            escritorio=escritorio or self.escritorio, usuario=self.user,
            cliente=cliente or self.cliente, numero_cnj=numero,
            vara="V", comarca="C", parte_contraria="X",
        )

    def _url(self, processo=None, sufixo=""):
        return f"/api/v1/processos/{(processo or self.processo).pk}/documentos/{sufixo}"

    def _enviar(self, arquivo=None, processo=None):
        return self.client.post(
            self._url(processo), {"arquivo": arquivo or _pdf()}, format="multipart", **self.cabecalho
        )

    def test_anexa_varios_documentos_e_lista_do_mais_recente_ao_mais_antigo(self):
        self._enviar(_pdf("primeiro.pdf"))
        resposta = self._enviar(_pdf("segundo.pdf"))

        self.assertEqual(resposta.status_code, 201)
        self.assertEqual(resposta.data["nome"], "segundo.pdf")
        self.assertEqual(resposta.data["enviado_por_nome"], "Ana")
        self.assertEqual(resposta.data["tamanho"], len(PDF))
        self.assertNotIn("arquivo", resposta.data)

        lista = self.client.get(self._url(), **self.cabecalho).data
        self.assertEqual([d["nome"] for d in lista], ["segundo.pdf", "primeiro.pdf"])
        self.assertTrue(lista[0]["url"])

    def test_recusa_arquivo_que_nao_e_o_que_diz_ser(self):
        resposta = self._enviar(_pdf("virus.pdf", b"MZ\x90\x00executavel"))

        self.assertEqual(resposta.status_code, 400)
        self.assertFalse(DocumentoProcesso.objects.exists())

    def test_recusa_extensao_nao_permitida_e_envio_sem_arquivo(self):
        invalido = self._enviar(SimpleUploadedFile("planilha.xlsx", b"PK\x03\x04x"))
        vazio = self.client.post(self._url(), {}, format="multipart", **self.cabecalho)

        self.assertEqual(invalido.status_code, 400)
        self.assertEqual(vazio.status_code, 400)

    @override_settings(UPLOAD_MAX_BYTES=10)
    def test_recusa_arquivo_acima_do_tamanho_maximo(self):
        self.assertEqual(self._enviar().status_code, 400)

    @override_settings(DOCUMENTOS_MAX_POR_PROCESSO=2)
    def test_limite_por_processo_vale_para_o_processo_e_nao_para_o_escritorio(self):
        self._enviar(_pdf("1.pdf"))
        self._enviar(_pdf("2.pdf"))
        terceiro = self._enviar(_pdf("3.pdf"))
        outro_processo = self._enviar(_pdf("4.pdf"), self._processo(numero="0000002-00.2024.5.16.0001"))

        self.assertEqual(terceiro.status_code, 400)
        self.assertIn("até 2 documentos", str(terceiro.data))
        self.assertEqual(self.processo.documentos.count(), 2)
        self.assertEqual(outro_processo.status_code, 201)

    def test_exclusao_apaga_o_registro_o_arquivo_e_audita(self):
        documento_id = self._enviar().data["id"]
        documento = DocumentoProcesso.objects.get(pk=documento_id)
        caminho = documento.arquivo.path

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.delete(self._url(sufixo=f"{documento_id}/"), **self.cabecalho)

        self.assertEqual(resposta.status_code, 204)
        self.assertFalse(DocumentoProcesso.objects.filter(pk=documento_id).exists())
        self.assertFalse(os.path.exists(caminho))
        removido = EventoAuditoria.objects.get(acao="processo.documento_removido")
        self.assertEqual(removido.alteracoes["nome_do_anexo"], "prova.pdf")  # não pode virar [REMOVIDO]
        acoes = set(EventoAuditoria.objects.values_list("acao", flat=True))
        self.assertLessEqual({"processo.documento_anexado", "processo.documento_removido"}, acoes)

    def test_excluir_o_processo_tambem_limpa_os_arquivos(self):
        documento_id = self._enviar().data["id"]
        caminho = DocumentoProcesso.objects.get(pk=documento_id).arquivo.path

        with self.captureOnCommitCallbacks(execute=True):
            self.processo.delete()

        self.assertFalse(os.path.exists(caminho))

    def test_arquivo_continua_no_storage_se_a_transacao_for_desfeita(self):
        documento = DocumentoProcesso.objects.create(
            processo=self.processo, arquivo=_pdf(), nome="p.pdf", tamanho=len(PDF)
        )
        caminho = documento.arquivo.path

        # sem executar os callbacks de commit: é o que acontece num rollback
        with self.captureOnCommitCallbacks(execute=False):
            documento.delete()

        self.assertTrue(os.path.exists(caminho))

    def test_documento_de_outro_processo_nao_pode_ser_excluido_por_este_endereco(self):
        outro = self._processo(numero="0000002-00.2024.5.16.0001")
        alheio = DocumentoProcesso.objects.create(
            processo=outro, arquivo=_pdf(), nome="a.pdf", tamanho=1
        )

        resposta = self.client.delete(self._url(sufixo=f"{alheio.pk}/"), **self.cabecalho)

        self.assertEqual(resposta.status_code, 404)
        self.assertTrue(DocumentoProcesso.objects.filter(pk=alheio.pk).exists())

    def test_processo_de_outro_escritorio_e_invisivel(self):
        dono = get_user_model().objects.create_user(username="o", email="o@x.com", password="x")
        outro = Escritorio.objects.create(nome="Outra", criado_por=dono)
        cliente = Cliente.objects.create(escritorio=outro, usuario=dono, nome="C", cpf_cnpj="y")
        alheio = self._processo(escritorio=outro, cliente=cliente, numero="0000003-00.2024.5.16.0001")
        documento = DocumentoProcesso.objects.create(
            processo=alheio, arquivo=_pdf(), nome="a.pdf", tamanho=1
        )

        listar = self.client.get(self._url(alheio), **self.cabecalho)
        enviar = self._enviar(processo=alheio)
        excluir = self.client.delete(self._url(alheio, f"{documento.pk}/"), **self.cabecalho)

        self.assertEqual((listar.status_code, enviar.status_code, excluir.status_code), (404, 404, 404))
        self.assertTrue(DocumentoProcesso.objects.filter(pk=documento.pk).exists())

    def test_exige_login(self):
        resposta = APIClient().get(self._url(), **self.cabecalho)

        self.assertEqual(resposta.status_code, 401)
