import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import AceiteTermos
from accounts.tests import SENHA, ContaTestCase
from auditlog.models import EventoAuditoria
from organizations.models import Escritorio, MembroEscritorio

User = get_user_model()


def _entrar(client, email, senha=SENHA):
    resposta = client.post(
        reverse("token_obtain_pair"), {"username": email, "password": senha}, format="json"
    )
    assert resposta.status_code == status.HTTP_200_OK, resposta.data
    return resposta.data


class SessoesTests(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.usuario = User.objects.create_user(
            username="ana@x.com", email="ana@x.com", password=SENHA
        )

    def _renovar(self, refresh):
        return self.client.post(reverse("token_refresh"), {"refresh": refresh}, format="json")

    def test_renovar_emite_refresh_novo_e_invalida_o_anterior(self):
        antigo = _entrar(self.client, "ana@x.com")["refresh"]

        renovado = self._renovar(antigo)

        self.assertEqual(renovado.status_code, status.HTTP_200_OK)
        self.assertNotEqual(renovado.data["refresh"], antigo)
        # um refresh roubado e usado depois do dono não pode continuar valendo
        self.assertEqual(self._renovar(antigo).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self._renovar(renovado.data["refresh"]).status_code, status.HTTP_200_OK
        )

    def test_logout_revoga_o_refresh_no_servidor(self):
        refresh = _entrar(self.client, "ana@x.com")["refresh"]

        saiu = self.client.post(reverse("logout"), {"refresh": refresh}, format="json")

        self.assertEqual(saiu.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self._renovar(refresh).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_com_token_invalido_responde_igual(self):
        resposta = self.client.post(reverse("logout"), {"refresh": "lixo"}, format="json")

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)

    def test_logout_pode_ser_repetido(self):
        refresh = _entrar(self.client, "ana@x.com")["refresh"]
        self.client.post(reverse("logout"), {"refresh": refresh}, format="json")

        de_novo = self.client.post(reverse("logout"), {"refresh": refresh}, format="json")

        self.assertEqual(de_novo.status_code, status.HTTP_204_NO_CONTENT)

    def test_recuperar_a_senha_derruba_as_sessoes_abertas(self):
        refresh = _entrar(self.client, "ana@x.com")["refresh"]
        self.client.post(reverse("reset-senha-solicitar"), {"email": "ana@x.com"}, format="json")
        corpo = mail.outbox[-1].body
        uid = re.search(r"uid=([\w-]+)", corpo).group(1)
        token = re.search(r"token=([\w-]+)", corpo).group(1)

        self.client.post(
            reverse("reset-senha-confirmar"),
            {"uid": uid, "token": token, "nova_senha": "outra-senha-forte-456"},
            format="json",
        )

        self.assertEqual(self._renovar(refresh).status_code, status.HTTP_401_UNAUTHORIZED)


class LgpdTests(ContaTestCase):
    def setUp(self):
        super().setUp()
        self.dono = User.objects.create_user(
            username="dono@x.com", email="dono@x.com", password=SENHA, first_name="Dono"
        )
        self.advogado = User.objects.create_user(
            username="adv@x.com", email="adv@x.com", password=SENHA, first_name="Adv"
        )
        self.alheio = User.objects.create_user(
            username="alheio@x.com", email="alheio@x.com", password=SENHA
        )
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.dono)
        self.m_dono = MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.dono, papel="OWNER"
        )
        self.m_adv = MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.advogado, papel="ADVOGADO"
        )
        for usuario in (self.dono, self.advogado):
            AceiteTermos.objects.create(usuario=usuario, versao="2026-10", ip="203.0.113.7")

    def _autenticado(self, usuario):
        cliente = APIClient()
        cliente.force_authenticate(usuario)
        return cliente

    def _excluir(self, usuario, senha=SENHA):
        return self._autenticado(usuario).post(
            reverse("excluir-conta"), {"senha": senha}, format="json"
        )

    # ---- exportação
    def test_exportacao_exige_login(self):
        resposta = self.client.get(reverse("exportar-dados"))

        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_exportacao_traz_so_os_dados_da_propria_pessoa(self):
        EventoAuditoria.objects.create(
            escritorio=self.escritorio, ator=self.advogado, acao="cliente.criado",
            recurso_tipo="cliente", recurso_id="1",
        )
        EventoAuditoria.objects.create(
            escritorio=self.escritorio, ator=self.dono, acao="processo.criado",
            recurso_tipo="processo", recurso_id="9",
        )

        resposta = self._autenticado(self.advogado).get(reverse("exportar-dados"))

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        dados = resposta.data
        self.assertEqual(dados["conta"]["email"], "adv@x.com")
        self.assertEqual(dados["escritorios"][0]["nome"], "Banca")
        self.assertEqual(dados["aceites_termos"][0]["versao"], "2026-10")
        self.assertEqual([a["acao"] for a in dados["atividade"]], ["cliente.criado"])
        corpo = str(dados)
        self.assertNotIn("password", corpo)
        self.assertNotIn("dono@x.com", corpo)
        self.assertIn("attachment", resposta["Content-Disposition"])

    # ---- exclusão
    def test_senha_errada_nao_exclui_nada(self):
        resposta = self._excluir(self.advogado, senha="errada")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.advogado.refresh_from_db()
        self.assertTrue(self.advogado.is_active)
        self.assertEqual(self.advogado.email, "adv@x.com")

    def test_exclusao_anonimiza_e_preserva_a_trilha_do_escritorio(self):
        resposta = self._excluir(self.advogado)

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.advogado.refresh_from_db()
        self.assertFalse(self.advogado.is_active)
        self.assertEqual(self.advogado.email, "")
        self.assertNotIn("adv", self.advogado.username)
        self.assertFalse(self.advogado.has_usable_password())
        self.m_adv.refresh_from_db()
        self.assertEqual(self.m_adv.status, MembroEscritorio.Status.SUSPENSO)
        self.assertTrue(EventoAuditoria.objects.filter(acao="conta.excluida").exists())
        self.assertTrue(AceiteTermos.objects.filter(usuario=self.advogado).exists())

    def test_conta_excluida_nao_entra_mais(self):
        self._excluir(self.advogado)

        for login in ("adv@x.com", f"excluido-{self.advogado.pk}"):
            tentativa = self.client.post(
                reverse("token_obtain_pair"),
                {"username": login, "password": SENHA},
                format="json",
            )
            self.assertEqual(tentativa.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_ja_emitido_deixa_de_valer_na_hora(self):
        sessao = _entrar(self.client, "adv@x.com")
        com_token = APIClient()
        com_token.credentials(HTTP_AUTHORIZATION=f"Bearer {sessao['access']}")
        com_token.post(reverse("excluir-conta"), {"senha": SENHA}, format="json")

        self.assertEqual(
            com_token.get(reverse("usuario-atual")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        renovar = self.client.post(
            reverse("token_refresh"), {"refresh": sessao["refresh"]}, format="json"
        )
        self.assertEqual(renovar.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reativar_a_conta_nao_ressuscita_as_sessoes_antigas(self):
        # is_active=False já barra o refresh; a revogação é a segunda camada.
        # Sem ela, reativar a conta (por um admin, por exemplo) devolveria o
        # acesso a quem tinha ficado com um token.
        sessao = _entrar(self.client, "adv@x.com")
        self._excluir(self.advogado)
        self.advogado.refresh_from_db()
        self.advogado.is_active = True
        self.advogado.save()

        renovar = self.client.post(
            reverse("token_refresh"), {"refresh": sessao["refresh"]}, format="json"
        )

        self.assertEqual(renovar.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unico_proprietario_de_escritorio_com_equipe_precisa_transferir_antes(self):
        resposta = self._excluir(self.dono)

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Banca", resposta.data["detail"])
        self.dono.refresh_from_db()
        self.assertTrue(self.dono.is_active)

    def test_proprietario_pode_sair_depois_de_transferir_a_propriedade(self):
        self.m_adv.papel = "OWNER"
        self.m_adv.save()

        resposta = self._excluir(self.dono)

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.escritorio.refresh_from_db()
        self.assertTrue(self.escritorio.ativo)  # a equipe continua usando

    def test_proprietario_sozinho_desativa_o_escritorio_sem_apagar_os_dados(self):
        solo = User.objects.create_user(username="solo@x.com", email="solo@x.com", password=SENHA)
        banca = Escritorio.objects.create(nome="Solo", criado_por=solo)
        MembroEscritorio.objects.create(escritorio=banca, usuario=solo, papel="OWNER")

        resposta = self._excluir(solo)

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        banca.refresh_from_db()
        self.assertFalse(banca.ativo)
        self.assertTrue(Escritorio.objects.filter(pk=banca.pk).exists())

    def test_exclusao_nao_toca_nos_dados_de_outra_pessoa(self):
        self._excluir(self.advogado)

        self.alheio.refresh_from_db()
        self.dono.refresh_from_db()
        self.assertTrue(self.alheio.is_active and self.dono.is_active)
        self.assertEqual(self.dono.email, "dono@x.com")
