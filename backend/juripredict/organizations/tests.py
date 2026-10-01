from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from auditlog.models import EventoAuditoria

from .models import Escritorio, MembroEscritorio


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

