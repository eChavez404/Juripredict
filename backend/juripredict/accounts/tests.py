import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AceiteTermos
from auditlog.models import EventoAuditoria
from organizations.models import ConviteEscritorio, Escritorio, MembroEscritorio
from organizations.services import convidar_membro

User = get_user_model()

SENHA = "uma-senha-bem-forte-123"


def _dados_registro(**extra):
    dados = {
        "nome": "Maria Souza",
        "email": "maria@escritorio.com",
        "senha": SENHA,
        "escritorio_nome": "Souza Advocacia",
        "aceite_termos": True,
    }
    dados.update(extra)
    return dados


class ContaTestCase(TestCase):
    def setUp(self):
        # os limites de requisição usam cache em memória, compartilhado entre testes
        cache.clear()
        self.client = APIClient()


class RegistroTests(ContaTestCase):
    def test_cria_usuario_escritorio_proprietario_aceite_e_auditoria(self):
        resposta = self.client.post(reverse("registro"), _dados_registro(), format="json")

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        usuario = User.objects.get(email="maria@escritorio.com")
        self.assertEqual(usuario.first_name, "Maria Souza")
        self.assertTrue(usuario.check_password(SENHA))

        membro = MembroEscritorio.objects.get(usuario=usuario)
        self.assertEqual(membro.papel, MembroEscritorio.Papel.OWNER)
        self.assertEqual(membro.escritorio.nome, "Souza Advocacia")
        self.assertTrue(AceiteTermos.objects.filter(usuario=usuario).exists())
        self.assertTrue(
            EventoAuditoria.objects.filter(
                escritorio=membro.escritorio, acao="escritorio.criado"
            ).exists()
        )

    def test_resposta_traz_tokens_que_funcionam(self):
        resposta = self.client.post(reverse("registro"), _dados_registro(), format="json")

        self.assertIn("access", resposta.data)
        self.assertIn("refresh", resposta.data)
        autenticado = APIClient()
        autenticado.credentials(HTTP_AUTHORIZATION=f"Bearer {resposta.data['access']}")
        me = autenticado.get(reverse("usuario-atual"))
        self.assertEqual(me.status_code, status.HTTP_200_OK)
        self.assertEqual(me.data["email"], "maria@escritorio.com")

    def test_exige_aceite_dos_termos(self):
        resposta = self.client.post(
            reverse("registro"), _dados_registro(aceite_termos=False), format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("aceite_termos", resposta.data)
        self.assertFalse(User.objects.exists())

    def test_rejeita_email_ja_cadastrado_ignorando_maiusculas(self):
        User.objects.create_user(username="x", email="MARIA@escritorio.com", password=SENHA)

        resposta = self.client.post(reverse("registro"), _dados_registro(), format="json")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", resposta.data)
        self.assertEqual(User.objects.count(), 1)

    def test_rejeita_senha_fraca_sem_criar_nada(self):
        resposta = self.client.post(
            reverse("registro"), _dados_registro(senha="12345678"), format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("senha", resposta.data)
        self.assertFalse(User.objects.exists())
        self.assertFalse(Escritorio.objects.exists())

    def test_falha_no_meio_nao_deixa_conta_pela_metade(self):
        # nome do escritório acima do limite estoura na validação, antes de gravar
        resposta = self.client.post(
            reverse("registro"), _dados_registro(escritorio_nome="x" * 300), format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.exists())

    def test_limita_cadastros_por_ip(self):
        for i in range(5):
            self.client.post(
                reverse("registro"), _dados_registro(email=f"u{i}@x.com"), format="json"
            )

        sexta = self.client.post(
            reverse("registro"), _dados_registro(email="u6@x.com"), format="json"
        )

        self.assertEqual(sexta.status_code, status.HTTP_429_TOO_MANY_REQUESTS)


class RecuperacaoSenhaTests(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.usuario = User.objects.create_user(
            username="ana@x.com", email="ana@x.com", password="senha-antiga-123"
        )

    def _link_do_email(self):
        corpo = mail.outbox[-1].body
        uid = re.search(r"uid=([\w-]+)", corpo).group(1)
        token = re.search(r"token=([\w-]+)", corpo).group(1)
        return uid, token

    def test_fluxo_completo_e_link_de_uso_unico(self):
        self.client.post(reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json")
        self.assertEqual(len(mail.outbox), 1)
        uid, token = self._link_do_email()

        confirmar = self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": uid, "token": token, "nova_senha": SENHA},
            format="json",
        )
        self.assertEqual(confirmar.status_code, status.HTTP_200_OK)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(SENHA))

        reutilizado = self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": uid, "token": token, "nova_senha": "outra-senha-forte-456"},
            format="json",
        )
        self.assertEqual(reutilizado.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password(SENHA))

    def test_resposta_igual_para_email_inexistente_e_nada_enviado(self):
        existente = self.client.post(
            reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json"
        )
        mail.outbox.clear()
        inexistente = self.client.post(
            reverse("reset-senha-solicitar"), {"email": "ninguem@x.com"}, format="json"
        )

        self.assertEqual(existente.status_code, inexistente.status_code)
        self.assertEqual(existente.data, inexistente.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_nao_envia_para_conta_desativada(self):
        self.usuario.is_active = False
        self.usuario.save()

        self.client.post(reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json")

        self.assertEqual(len(mail.outbox), 0)

    def test_token_adulterado_e_rejeitado(self):
        self.client.post(reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json")
        uid, token = self._link_do_email()

        resposta = self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": uid, "token": token[:-2] + "xx", "nova_senha": SENHA},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_uid_invalido_nao_estoura(self):
        resposta = self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": "!!!", "token": "abc", "nova_senha": SENHA},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_senha_nova_passa_pelos_validadores(self):
        self.client.post(reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json")
        uid, token = self._link_do_email()

        resposta = self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": uid, "token": token, "nova_senha": "12345678"},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.usuario.refresh_from_db()
        self.assertTrue(self.usuario.check_password("senha-antiga-123"))


class AceitarConviteTests(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            username="dono", email="dono@x.com", password=SENHA
        )
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.owner)
        self.membro_owner = MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=self.owner,
            papel=MembroEscritorio.Papel.OWNER,
        )

    def _convidar(self, email="novo@x.com", papel=MembroEscritorio.Papel.ADVOGADO):
        with self.captureOnCommitCallbacks(execute=True):
            convidar_membro(
                escritorio=self.escritorio,
                membro_ator=self.membro_owner,
                email=email,
                papel=papel,
            )
        return re.search(r"token=([\w-]+)", mail.outbox[-1].body).group(1)

    def test_pessoa_nova_cria_conta_e_entra_com_o_papel_do_convite(self):
        token = self._convidar()

        resposta = self.client.post(
            reverse("convite-aceitar"),
            {"token": token, "senha": SENHA, "nome": "Novo Advogado", "aceite_termos": True},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        usuario = User.objects.get(email="novo@x.com")
        membro = MembroEscritorio.objects.get(usuario=usuario, escritorio=self.escritorio)
        self.assertEqual(membro.papel, MembroEscritorio.Papel.ADVOGADO)
        self.assertTrue(AceiteTermos.objects.filter(usuario=usuario).exists())
        self.assertTrue(
            EventoAuditoria.objects.filter(acao="convite.aceito").exists()
        )

    def test_convite_so_vale_uma_vez(self):
        token = self._convidar()
        dados = {"token": token, "senha": SENHA, "aceite_termos": True}
        self.client.post(reverse("convite-aceitar"), dados, format="json")

        # Sem o vínculo, só a regra de uso único pode barrar a segunda tentativa.
        # (Com o vínculo ainda existindo, "já é membro" também barraria e
        # mascararia um defeito no uso único.)
        MembroEscritorio.objects.filter(usuario__email="novo@x.com").delete()
        segunda = self.client.post(reverse("convite-aceitar"), dados, format="json")

        self.assertEqual(segunda.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(segunda.data["detail"], "Convite inválido ou expirado.")
        self.assertFalse(
            MembroEscritorio.objects.filter(usuario__email="novo@x.com").exists()
        )

    def test_conta_existente_precisa_da_senha_atual(self):
        existente = User.objects.create_user(
            username="ja@x.com", email="ja@x.com", password="senha-do-dono-123"
        )
        token = self._convidar(email="ja@x.com")

        errada = self.client.post(
            reverse("convite-aceitar"), {"token": token, "senha": "palpite-errado"}, format="json"
        )
        self.assertEqual(errada.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(MembroEscritorio.objects.filter(usuario=existente).exists())

        certa = self.client.post(
            reverse("convite-aceitar"),
            {"token": token, "senha": "senha-do-dono-123"},
            format="json",
        )
        self.assertEqual(certa.status_code, status.HTTP_201_CREATED)
        self.assertTrue(MembroEscritorio.objects.filter(usuario=existente).exists())

    def test_pessoa_nova_precisa_aceitar_os_termos(self):
        token = self._convidar()

        resposta = self.client.post(
            reverse("convite-aceitar"), {"token": token, "senha": SENHA}, format="json"
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(User.objects.filter(email="novo@x.com").exists())

    def test_token_inexistente_e_expirado_dao_a_mesma_resposta(self):
        token = self._convidar()
        ConviteEscritorio.objects.update(expira_em=timezone.now() - timedelta(days=1))

        expirado = self.client.post(
            reverse("convite-aceitar"),
            {"token": token, "senha": SENHA, "aceite_termos": True},
            format="json",
        )
        inexistente = self.client.post(
            reverse("convite-aceitar"),
            {"token": "nao-existe", "senha": SENHA, "aceite_termos": True},
            format="json",
        )

        self.assertEqual(expirado.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(expirado.data, inexistente.data)

    def test_convite_de_escritorio_desativado_nao_vale(self):
        token = self._convidar()
        Escritorio.objects.update(ativo=False)

        resposta = self.client.post(
            reverse("convite-aceitar"),
            {"token": token, "senha": SENHA, "aceite_termos": True},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)


class LoginThrottleTests(ContaTestCase):
    def test_tentativas_erradas_na_mesma_conta_esbarram_no_limite(self):
        User.objects.create_user(username="alvo@x.com", email="alvo@x.com", password=SENHA)

        codigos = [
            self.client.post(
                reverse("token_obtain_pair"),
                {"username": "alvo@x.com", "password": "errada"},
                format="json",
            ).status_code
            for _ in range(12)
        ]

        self.assertEqual(codigos[:10], [status.HTTP_401_UNAUTHORIZED] * 10)
        self.assertIn(status.HTTP_429_TOO_MANY_REQUESTS, codigos[10:])

    def test_outra_conta_nao_e_afetada(self):
        User.objects.create_user(username="alvo@x.com", email="alvo@x.com", password=SENHA)
        User.objects.create_user(username="outro@x.com", email="outro@x.com", password=SENHA)
        for _ in range(12):
            self.client.post(
                reverse("token_obtain_pair"),
                {"username": "alvo@x.com", "password": "errada"},
                format="json",
            )

        resposta = self.client.post(
            reverse("token_obtain_pair"),
            {"username": "outro@x.com", "password": SENHA},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
