import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from auditlog.models import EventoAuditoria

from .models import ConviteEscritorio, Escritorio, MembroEscritorio
from .tokens import hash_token


class OrganizacoesApiTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="owner", email="owner@example.com", password="senha-forte"
        )
        self.escritorio = Escritorio.objects.create(
            nome="Escritório Principal", criado_por=self.owner
        )
        self.owner_membership = MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=self.owner,
            papel=MembroEscritorio.Papel.OWNER,
        )
        self.advogado = get_user_model().objects.create_user(
            username="advogado", email="advogado@example.com", password="senha-forte"
        )
        self.advogado_membership = MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=self.advogado,
            papel=MembroEscritorio.Papel.ADVOGADO,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.headers = {"HTTP_X_ESCRITORIO_ID": str(self.escritorio.pk)}

    def test_lista_escritorios_e_membros(self):
        escritorios = self.client.get(reverse("escritorio-list"))
        membros = self.client.get(
            reverse("membro-escritorio-list", args=[self.escritorio.pk]),
            **self.headers,
        )

        self.assertEqual(escritorios.status_code, status.HTTP_200_OK)
        self.assertEqual(len(escritorios.data), 1)
        self.assertEqual(membros.status_code, status.HTTP_200_OK)
        self.assertEqual(len(membros.data), 2)

    def test_owner_atualiza_escritorio_e_audita(self):
        response = self.client.patch(
            reverse("escritorio-detail", args=[self.escritorio.pk]),
            {"nome": "Novo Nome"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.escritorio.refresh_from_db()
        self.assertEqual(self.escritorio.nome, "Novo Nome")
        self.assertTrue(
            EventoAuditoria.objects.filter(acao="escritorio.atualizado").exists()
        )

    def test_ultimo_owner_nao_pode_ser_rebaixado_ou_suspenso(self):
        url = reverse(
            "membro-escritorio-detail",
            args=[self.escritorio.pk, self.owner_membership.pk],
        )

        rebaixado = self.client.patch(
            url, {"papel": "ADMIN"}, format="json", **self.headers
        )
        suspenso = self.client.patch(
            url, {"status": "SUSPENSO"}, format="json", **self.headers
        )

        self.assertEqual(rebaixado.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(suspenso.status_code, status.HTTP_400_BAD_REQUEST)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.papel, MembroEscritorio.Papel.OWNER)
        self.assertEqual(self.owner_membership.status, MembroEscritorio.Status.ATIVO)

    def test_owner_pode_alterar_membro_quando_outro_owner_permanece(self):
        self.advogado_membership.papel = MembroEscritorio.Papel.OWNER
        self.advogado_membership.save(update_fields=("papel",))
        url = reverse(
            "membro-escritorio-detail",
            args=[self.escritorio.pk, self.owner_membership.pk],
        )

        response = self.client.patch(
            url, {"papel": "ADMIN"}, format="json", **self.headers
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.owner_membership.refresh_from_db()
        self.assertEqual(self.owner_membership.papel, MembroEscritorio.Papel.ADMIN)
        self.assertTrue(EventoAuditoria.objects.filter(acao="membro.atualizado").exists())

    def test_advogado_nao_gerencia_escritorio(self):
        self.client.force_authenticate(self.advogado)

        response = self.client.patch(
            reverse("escritorio-detail", args=[self.escritorio.pk]),
            {"nome": "Tentativa"},
            format="json",
            **self.headers,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_header_de_outro_escritorio_e_negado(self):
        outro = Escritorio.objects.create(nome="Outro")

        response = self.client.get(
            reverse("escritorio-detail", args=[outro.pk]),
            HTTP_X_ESCRITORIO_ID=str(outro.pk),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ContextoNegadoPorPadraoTests(TestCase):
    def test_usuario_sem_membership_nao_acessa_recurso_de_negocio(self):
        usuario = get_user_model().objects.create_user(
            username="sem-escritorio", password="senha-forte"
        )
        client = APIClient()
        client.force_authenticate(usuario)

        response = client.get(reverse("cliente-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)



class ConviteApiTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="dono", email="dono@example.com", password="senha-forte"
        )
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.owner)
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.owner, papel=MembroEscritorio.Papel.OWNER
        )
        self.advogado = get_user_model().objects.create_user(
            username="adv", email="adv@example.com", password="senha-forte"
        )
        MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=self.advogado,
            papel=MembroEscritorio.Papel.ADVOGADO,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.headers = {"HTTP_X_ESCRITORIO_ID": str(self.escritorio.pk)}
        self.url = reverse("convite-escritorio-list", args=[self.escritorio.pk])

    def _convidar(self, email="novo@example.com", papel="ADVOGADO"):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(
                self.url, {"email": email, "papel": papel}, format="json", **self.headers
            )

    def test_gestor_convida_e_o_email_sai_so_depois_do_commit(self):
        resposta = self._convidar()

        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["novo@example.com"])
        self.assertTrue(EventoAuditoria.objects.filter(acao="convite.criado").exists())

    def test_token_nao_vaza_na_resposta_nem_no_banco(self):
        resposta = self._convidar()

        token = re.search(r"token=([\w-]+)", mail.outbox[0].body).group(1)
        convite = ConviteEscritorio.objects.get()
        self.assertNotIn(token, str(resposta.data))
        self.assertNotEqual(convite.token_hash, token)
        self.assertEqual(convite.token_hash, hash_token(token))

    def test_advogado_nao_convida(self):
        self.client.force_authenticate(self.advogado)

        resposta = self._convidar()

        self.assertEqual(resposta.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(ConviteEscritorio.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_nao_se_concede_proprietario_por_convite(self):
        resposta = self._convidar(papel="OWNER")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ConviteEscritorio.objects.exists())

    def test_nao_convida_quem_ja_e_membro(self):
        resposta = self._convidar(email="ADV@example.com")

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ConviteEscritorio.objects.exists())

    def test_reconvidar_invalida_o_link_anterior(self):
        self._convidar()
        primeiro = re.search(r"token=([\w-]+)", mail.outbox[-1].body).group(1)
        self._convidar()

        self.assertEqual(ConviteEscritorio.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 2)
        self.assertNotEqual(
            ConviteEscritorio.objects.get().token_hash, hash_token(primeiro)
        )

    def test_lista_so_pendentes_do_proprio_escritorio(self):
        self._convidar()
        outro = Escritorio.objects.create(nome="Outra", criado_por=self.owner)
        ConviteEscritorio.objects.create(
            escritorio=outro,
            email="alheio@example.com",
            papel="ADVOGADO",
            token_hash="x" * 64,
            expira_em=timezone.now() + timedelta(days=1),
        )

        resposta = self.client.get(self.url, **self.headers)

        self.assertEqual([c["email"] for c in resposta.data], ["novo@example.com"])

    def test_revogar_apaga_e_audita(self):
        self._convidar()
        convite = ConviteEscritorio.objects.get()

        resposta = self.client.delete(
            reverse("convite-escritorio-detail", args=[self.escritorio.pk, convite.pk]),
            **self.headers,
        )

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ConviteEscritorio.objects.exists())
        self.assertTrue(EventoAuditoria.objects.filter(acao="convite.revogado").exists())

    def test_nao_revoga_convite_de_outro_escritorio(self):
        outro_dono = get_user_model().objects.create_user(
            username="outro", email="outro@example.com", password="senha-forte"
        )
        outro = Escritorio.objects.create(nome="Outra", criado_por=outro_dono)
        convite = ConviteEscritorio.objects.create(
            escritorio=outro,
            email="alheio@example.com",
            papel="ADVOGADO",
            token_hash="y" * 64,
            expira_em=timezone.now() + timedelta(days=1),
        )

        resposta = self.client.delete(
            reverse("convite-escritorio-detail", args=[outro.pk, convite.pk]),
            **self.headers,
        )

        self.assertIn(resposta.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        self.assertTrue(ConviteEscritorio.objects.filter(pk=convite.pk).exists())
