"""Regressões encontradas em revisão de código: cada teste reproduz um defeito real."""

import http.client
import tempfile
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import EmailVerificado
from accounts.services import aceitar_convite
from accounts.tokens_api import criar_token_api
from organizations.emails import enviar_convite
from organizations.models import Escritorio, MembroEscritorio
from organizations.services import convidar_membro

from .andamentos import sincronizar_processo
from .datajud import DatajudErro, consultar_movimentos
from .emails import enviar_lembrete_prazos, enviar_novos_andamentos
from .models import Cliente, EventoAgenda, Processo
from .views import AlterarSenhaAPIView

SENHA = "Senha#Forte2026x"


def pdf(nome):
    return SimpleUploadedFile(nome, b"%PDF-1.7 conteudo", content_type="application/pdf")


class BaseRegressao(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            "ana@exemplo.invalid", "ana@exemplo.invalid", SENHA, first_name="Ana"
        )
        self.escritorio = Escritorio.objects.create(nome="Escritório", criado_por=self.usuario)
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, papel=MembroEscritorio.Papel.OWNER
        )
        self.api = APIClient()
        self.api.force_authenticate(self.usuario)
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, nome="Cliente", cpf_cnpj="x", cpf_cnpj_hash="h"
        )

    def criar_processo(self, **extra):
        return Processo.objects.create(
            escritorio=self.escritorio,
            cliente=self.cliente,
            numero_cnj="0000001-00.2026.5.16.0001",
            vara="1ª Vara",
            comarca="Balsas",
            parte_contraria="Empresa",
            **extra,
        )


class LembreteDeEventoRemarcadoTests(BaseRegressao):
    def setUp(self):
        super().setUp()
        self.inicio = timezone.now() + timedelta(hours=10)
        self.evento = EventoAgenda.objects.create(
            escritorio=self.escritorio,
            usuario=self.usuario,
            titulo="Prazo",
            inicio=self.inicio,
            lembrete_enviado_em=timezone.now(),
        )

    def _patch(self, **dados):
        resposta = self.api.patch(f"/api/v1/eventos/{self.evento.pk}/", dados, format="json")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.evento.refresh_from_db()

    def test_remarcar_libera_novo_lembrete(self):
        self._patch(inicio=(self.inicio + timedelta(days=5)).isoformat())
        self.assertIsNone(self.evento.lembrete_enviado_em)

    def test_editar_outro_campo_nao_repete_o_lembrete(self):
        self._patch(titulo="Prazo revisto", inicio=self.inicio.isoformat())
        self.assertIsNotNone(self.evento.lembrete_enviado_em)


class ArquivoDaPeticaoInicialTests(BaseRegressao):
    def setUp(self):
        super().setUp()
        pasta = tempfile.TemporaryDirectory()
        self.addCleanup(pasta.cleanup)
        ajuste = override_settings(MEDIA_ROOT=pasta.name)
        ajuste.enable()
        self.addCleanup(ajuste.disable)

    def test_excluir_o_processo_apaga_o_arquivo(self):
        processo = self.criar_processo(arquivo_peticao_inicial=pdf("inicial.pdf"))
        nome = processo.arquivo_peticao_inicial.name
        self.assertTrue(default_storage.exists(nome))

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.api.delete(f"/api/v1/processos/{processo.pk}/")

        self.assertEqual(resposta.status_code, 204)
        self.assertFalse(default_storage.exists(nome))

    def test_substituir_a_peticao_apaga_o_arquivo_anterior(self):
        processo = self.criar_processo(arquivo_peticao_inicial=pdf("antiga.pdf"))
        antigo = processo.arquivo_peticao_inicial.name

        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.api.patch(
                f"/api/v1/processos/{processo.pk}/",
                {"arquivo_peticao_inicial": pdf("nova.pdf")},
                format="multipart",
            )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        processo.refresh_from_db()
        self.assertFalse(default_storage.exists(antigo))
        self.assertTrue(default_storage.exists(processo.arquivo_peticao_inicial.name))

    def test_editar_outro_campo_mantem_o_arquivo(self):
        processo = self.criar_processo(arquivo_peticao_inicial=pdf("inicial.pdf"))
        nome = processo.arquivo_peticao_inicial.name

        with self.captureOnCommitCallbacks(execute=True):
            self.api.patch(f"/api/v1/processos/{processo.pk}/", {"titulo": "Novo"}, format="json")

        self.assertTrue(default_storage.exists(nome))


    def test_salvar_o_formulario_sem_novo_arquivo_mantem_a_peticao(self):
        """O formulário do app envia multipart com todos os campos, sem o arquivo."""
        processo = self.criar_processo(arquivo_peticao_inicial=pdf("inicial.pdf"))
        nome = processo.arquivo_peticao_inicial.name
        dados = {
            "numero_cnj": processo.numero_cnj,
            "titulo": "Novo",
            "area": "TRABALHISTA",
            "vara": "1ª Vara",
            "comarca": "Balsas",
            "cliente": self.cliente.pk,
            "parte_contraria": "Empresa",
            "status": "ATIVO",
            "resultado": "PENDENTE",
            "valor_causa": "",
            "data_distribuicao": "",
            "observacoes": "",
        }

        for metodo in (self.api.put, self.api.patch):
            with self.captureOnCommitCallbacks(execute=True):
                resposta = metodo(f"/api/v1/processos/{processo.pk}/", dados, format="multipart")
            self.assertEqual(resposta.status_code, 200, resposta.data)

        processo.refresh_from_db()
        self.assertEqual(processo.arquivo_peticao_inicial.name, nome)
        self.assertTrue(default_storage.exists(nome))


class CorpoDeLoginInvalidoTests(TestCase):
    def test_json_que_nao_e_objeto_responde_400_e_nao_500(self):
        cliente = APIClient(raise_request_exception=False)
        for corpo in ([], [1], "texto", 7):
            resposta = cliente.post("/api/v1/auth/token/", corpo, format="json")
            self.assertEqual(resposta.status_code, 400, corpo)


class RecuperacaoDeSenhaSemSmtpTests(BaseRegressao):
    def test_falha_de_envio_nao_revela_que_a_conta_existe(self):
        cliente = APIClient(raise_request_exception=False)
        with mock.patch("accounts.emails.send_mail", side_effect=OSError("smtp fora do ar")):
            existe = cliente.post("/api/v1/auth/password/reset/", {"email": self.usuario.email}, format="json")
        nao_existe = cliente.post("/api/v1/auth/password/reset/", {"email": "ninguem@exemplo.invalid"}, format="json")

        self.assertEqual(existe.status_code, nao_existe.status_code)
        self.assertEqual(existe.data, nao_existe.data)


class EmailComNomeDeEscritorioEmDuasLinhasTests(BaseRegressao):
    def setUp(self):
        super().setUp()
        Escritorio.objects.filter(pk=self.escritorio.pk).update(nome="Silva\nAssociados")
        self.escritorio.refresh_from_db()

    def test_lembrete_nao_quebra_no_assunto(self):
        evento = EventoAgenda.objects.create(
            escritorio=self.escritorio, usuario=self.usuario, titulo="Prazo", inicio=timezone.now()
        )
        enviar_lembrete_prazos(usuario=self.usuario, escritorio=self.escritorio, eventos=[evento])
        self.assertEqual(mail.outbox[-1].subject, "Compromisso próximo — Silva Associados")

    def test_aviso_de_andamentos_nao_quebra_no_assunto(self):
        enviar_novos_andamentos(usuario=self.usuario, escritorio=self.escritorio, itens=[])
        self.assertEqual(mail.outbox[-1].subject, "Novos andamentos — Silva Associados")

    def test_convite_nao_quebra_no_assunto(self):
        convite = mock.Mock(email="novo@exemplo.invalid", escritorio=self.escritorio, expira_em=timezone.now())
        enviar_convite(convite=convite, token="t")
        self.assertIn("Silva Associados", mail.outbox[-1].subject)


class EscritorioDadosInvalidosTests(BaseRegressao):
    def _patch(self, **dados):
        return self.api.patch(f"/api/v1/escritorios/{self.escritorio.pk}/", dados, format="json")

    def test_fuso_inexistente_e_recusado(self):
        # gravado, faria todo lembrete do escritório falhar em silêncio a cada rodada
        for fuso in ("Marte/Olympus", "../../etc/passwd", ""):
            self.assertEqual(self._patch(fuso_horario=fuso).status_code, 400, fuso)
        self.escritorio.refresh_from_db()
        self.assertEqual(self.escritorio.fuso_horario, "America/Sao_Paulo")

    def test_fuso_valido_e_aceito(self):
        self.assertEqual(self._patch(fuso_horario="America/Manaus").status_code, 200)

    def test_nome_em_varias_linhas_vira_uma_linha(self):
        resposta = self._patch(nome="Silva\r\n  Associados")
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["nome"], "Silva Associados")


class FiltroDeDatasDaAgendaTests(BaseRegressao):
    def test_data_invalida_responde_400_e_nao_500(self):
        self.api.raise_request_exception = False
        for valor in ("abc", "2026-02-31"):
            for parametro in ("inicio", "fim"):
                resposta = self.api.get("/api/v1/eventos/", {parametro: valor})
                self.assertEqual(resposta.status_code, 400, (parametro, valor))

    def test_data_valida_continua_filtrando(self):
        self.assertEqual(self.api.get("/api/v1/eventos/", {"inicio": "2026-01-01"}).status_code, 200)


class AndamentosDoDataJudTests(BaseRegressao):
    def test_movimento_sem_codigo_nao_duplica_ao_ler_de_novo(self):
        processo = self.criar_processo()
        movimentos = [{"data_hora": timezone.now(), "codigo": None, "nome": "Juntada", "complemento": ""}]

        self.assertEqual(sincronizar_processo(processo, buscar=lambda _: movimentos), 1)
        self.assertEqual(sincronizar_processo(processo, buscar=lambda _: movimentos), 0)
        self.assertEqual(processo.andamentos.count(), 1)

    def test_movimento_repetido_na_mesma_resposta_grava_uma_vez(self):
        processo = self.criar_processo()
        movimento = {"data_hora": timezone.now(), "codigo": None, "nome": "Juntada", "complemento": ""}

        self.assertEqual(sincronizar_processo(processo, buscar=lambda _: [movimento, movimento]), 1)

    @override_settings(DATAJUD_API_KEY="chave")
    def test_falha_de_rede_durante_a_leitura_vira_erro_tratado(self):
        for falha in (http.client.IncompleteRead(b""), ConnectionResetError()):
            abrir = mock.MagicMock()
            abrir.return_value.__enter__.return_value.read.side_effect = falha
            with self.assertRaises(DatajudErro):
                consultar_movimentos("0000001-00.2026.5.16.0001", abrir=abrir)


class TrocaDeEmailTests(BaseRegressao):
    def setUp(self):
        super().setUp()
        EmailVerificado.objects.create(usuario=self.usuario)

    def _patch(self, **dados):
        with self.captureOnCommitCallbacks(execute=True):
            return self.api.patch("/api/v1/auth/me/", dados, format="json")

    def test_email_novo_deixa_de_constar_como_verificado_e_recebe_link(self):
        resposta = self._patch(email="Nova@Exemplo.invalid")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.data["email"], "nova@exemplo.invalid")
        self.assertIs(resposta.data["email_verificado"], False)
        self.assertEqual([m.to for m in mail.outbox], [["nova@exemplo.invalid"]])

    def test_salvar_o_perfil_sem_mudar_o_email_mantem_a_verificacao(self):
        resposta = self._patch(nome="Ana Maria", email="ANA@exemplo.invalid")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertIs(resposta.data["email_verificado"], True)
        self.assertEqual(mail.outbox, [])

    def test_email_vazio_e_recusado(self):
        self.assertEqual(self._patch(email="").status_code, 400)

    def test_email_que_e_login_de_outra_conta_e_recusado(self):
        get_user_model().objects.create_user("ocupado@exemplo.invalid", "outro@exemplo.invalid", SENHA)
        self.assertEqual(self._patch(email="ocupado@exemplo.invalid").status_code, 400)


class TrocaDeSenhaTests(BaseRegressao):
    def test_revoga_os_tokens_de_api(self):
        token, _ = criar_token_api(usuario=self.usuario, nome="Agente", senha=SENHA)

        resposta = self.api.post(
            "/api/v1/auth/password/",
            {"senha_atual": SENHA, "nova_senha": "Outra#Senha2026y"},
            format="json",
        )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        token.refresh_from_db()
        self.assertFalse(token.ativo)

    def test_tem_o_limite_das_rotas_que_conferem_senha(self):
        self.assertEqual(AlterarSenhaAPIView.throttle_scope, "conta_sensivel")


class ConvitesTests(BaseRegressao):
    def _convidar(self, email):
        membro = MembroEscritorio.objects.get(usuario=self.usuario)
        capturado = {}
        with self.captureOnCommitCallbacks(execute=True):
            convidar_membro(
                escritorio=self.escritorio,
                membro_ator=membro,
                email=email,
                papel=MembroEscritorio.Papel.ADVOGADO,
                enviar=lambda convite, token: capturado.update(token=token),
            )
        return capturado["token"]

    def test_convite_para_email_que_e_login_antigo_de_uma_conta(self):
        antiga = get_user_model().objects.create_user(
            "antigo@exemplo.invalid", "atual@exemplo.invalid", SENHA
        )
        token = self._convidar("antigo@exemplo.invalid")

        usuario = aceitar_convite(token=token, senha=SENHA)

        self.assertEqual(usuario.pk, antiga.pk)
        self.assertTrue(
            MembroEscritorio.objects.filter(escritorio=self.escritorio, usuario=antiga).exists()
        )
        # o link provou a caixa do e-mail antigo, não a do e-mail atual da conta
        self.assertFalse(EmailVerificado.objects.filter(usuario=antiga).exists())

    def test_estagiario_nao_lista_os_emails_convidados(self):
        self._convidar("novo@exemplo.invalid")
        estagiario = get_user_model().objects.create_user("e@exemplo.invalid", "e@exemplo.invalid", SENHA)
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=estagiario, papel=MembroEscritorio.Papel.ESTAGIARIO
        )
        api = APIClient()
        api.force_authenticate(estagiario)
        rota = f"/api/v1/escritorios/{self.escritorio.pk}/convites/"

        self.assertEqual(api.get(rota).status_code, 403)
        self.assertEqual(self.api.get(rota).status_code, 200)
