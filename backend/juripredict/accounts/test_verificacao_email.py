import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail, signing
from django.test import override_settings
from django.urls import reverse
from rest_framework import status

from accounts.models import EmailVerificado
from accounts.services import enviar_verificacao
from organizations.models import ConviteEscritorio, Escritorio, MembroEscritorio
from organizations.services import convidar_membro

from .tests import SENHA, ContaTestCase, _dados_registro

User = get_user_model()


def _token_do_email():
    return re.search(r"token=(\S+)", mail.outbox[-1].body).group(1)


class VerificacaoEmailTests(ContaTestCase):
    def _registrar(self):
        with self.captureOnCommitCallbacks(execute=True):
            resposta = self.client.post(reverse("registro"), _dados_registro(), format="json")
        return resposta, User.objects.get(email="maria@escritorio.com")

    def test_cadastro_envia_link_e_nasce_nao_verificado(self):
        resposta, usuario = self._registrar()

        self.assertFalse(resposta.data["user"]["email_verificado"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["maria@escritorio.com"])
        self.assertIn("/confirmar-email?token=", mail.outbox[0].body)
        self.assertFalse(EmailVerificado.objects.filter(usuario=usuario).exists())

    def test_cadastro_nao_depende_do_envio_do_email(self):
        # falha de SMTP não pode impedir a pessoa de criar a conta nem devolver erro
        with mock.patch("accounts.emails.send_mail", side_effect=OSError):
            with self.assertLogs("accounts.services", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    resposta = self.client.post(
                        reverse("registro"), _dados_registro(), format="json"
                    )
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="maria@escritorio.com").exists())

    def test_link_confirma_o_email_e_o_me_passa_a_refletir(self):
        _, usuario = self._registrar()

        confirmar = self.client.post(
            reverse("email-confirmar"), {"token": _token_do_email()}, format="json"
        )

        self.assertEqual(confirmar.status_code, status.HTTP_200_OK)
        self.assertTrue(EmailVerificado.objects.filter(usuario=usuario).exists())
        self.client.force_authenticate(usuario)
        me = self.client.get(reverse("usuario-atual"))
        self.assertTrue(me.data["email_verificado"])

    def test_repetir_o_link_e_inofensivo(self):
        self._registrar()
        token = _token_do_email()

        primeira = self.client.post(reverse("email-confirmar"), {"token": token}, format="json")
        segunda = self.client.post(reverse("email-confirmar"), {"token": token}, format="json")

        self.assertEqual(primeira.status_code, status.HTTP_200_OK)
        self.assertEqual(segunda.status_code, status.HTTP_200_OK)
        self.assertEqual(EmailVerificado.objects.count(), 1)

    def test_token_adulterado_ou_inventado_e_recusado(self):
        _, usuario = self._registrar()
        token = _token_do_email()

        for invalido in (token[:-2] + "xx", "lixo", signing.dumps({"uid": usuario.pk, "email": usuario.email})):
            with self.subTest(token=invalido):
                resposta = self.client.post(
                    reverse("email-confirmar"), {"token": invalido}, format="json"
                )
                self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EmailVerificado.objects.exists())

    def test_link_expirado_e_recusado(self):
        _, usuario = self._registrar()
        token = _token_do_email()

        with override_settings(VERIFICACAO_EMAIL_HORAS=0):
            resposta = self.client.post(reverse("email-confirmar"), {"token": token}, format="json")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EmailVerificado.objects.filter(usuario=usuario).exists())

    def test_link_antigo_nao_vale_depois_de_trocar_o_email(self):
        _, usuario = self._registrar()
        token = _token_do_email()
        usuario.email = "outro@escritorio.com"
        usuario.save(update_fields=("email",))

        resposta = self.client.post(reverse("email-confirmar"), {"token": token}, format="json")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EmailVerificado.objects.exists())

    def test_link_de_conta_desativada_e_recusado(self):
        _, usuario = self._registrar()
        token = _token_do_email()
        usuario.is_active = False
        usuario.save(update_fields=("is_active",))

        resposta = self.client.post(reverse("email-confirmar"), {"token": token}, format="json")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reenvio_exige_login(self):
        resposta = self.client.post(reverse("email-reenviar"))

        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reenvio_manda_novo_link_e_para_depois_de_verificado(self):
        _, usuario = self._registrar()
        mail.outbox.clear()
        self.client.force_authenticate(usuario)

        self.client.post(reverse("email-reenviar"))
        self.assertEqual(len(mail.outbox), 1)

        self.client.post(reverse("email-confirmar"), {"token": _token_do_email()}, format="json")
        self.client.post(reverse("email-reenviar"))
        self.assertEqual(len(mail.outbox), 1)

    def test_reenvio_tem_limite_de_requisicoes(self):
        _, usuario = self._registrar()
        self.client.force_authenticate(usuario)

        codigos = [self.client.post(reverse("email-reenviar")).status_code for _ in range(11)]

        self.assertEqual(codigos[-1], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_enviar_verificacao_usa_o_enviador_injetado(self):
        usuario = User.objects.create_user(username="a@x.com", email="a@x.com", password=SENHA)
        enviar = mock.Mock()

        enviar_verificacao(usuario, enviar=enviar)

        enviar.assert_called_once()
        self.assertEqual(enviar.call_args.kwargs["usuario"], usuario)


class ConviteVerificaEmailTests(ContaTestCase):
    def test_aceitar_convite_conta_como_email_verificado(self):
        dono = User.objects.create_user(username="d@x.com", email="d@x.com", password=SENHA)
        escritorio = Escritorio.objects.create(nome="Banca", criado_por=dono)
        MembroEscritorio.objects.create(
            escritorio=escritorio, usuario=dono, papel=MembroEscritorio.Papel.OWNER
        )
        membro = MembroEscritorio.objects.get(escritorio=escritorio, usuario=dono)
        with self.captureOnCommitCallbacks(execute=True):
            convidar_membro(
                escritorio=escritorio, membro_ator=membro, email="novo@x.com",
                papel=MembroEscritorio.Papel.ADVOGADO,
            )
        token = re.search(r"token=([\w-]+)", mail.outbox[-1].body).group(1)

        resposta = self.client.post(
            reverse("convite-aceitar"),
            {"token": token, "senha": SENHA, "nome": "Novo", "aceite_termos": True},
            format="json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertTrue(resposta.data["user"]["email_verificado"])
        self.assertTrue(ConviteEscritorio.objects.filter(email="novo@x.com", aceito_em__isnull=False).exists())
