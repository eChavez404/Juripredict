from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from organizations.models import Escritorio, MembroEscritorio

from .models import EventoAuditoria
from .services import registrar_evento_auditoria, sanitizar


class AuditoriaTests(TestCase):
    def setUp(self):
        self.owner = get_user_model().objects.create_user(
            username="owner-audit", password="senha-forte"
        )
        self.escritorio = Escritorio.objects.create(nome="Auditável")
        MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=self.owner,
            papel=MembroEscritorio.Papel.OWNER,
        )

    def test_sanitizacao_remove_segredos_recursivamente(self):
        resultado = sanitizar(
            {
                "cpf_cnpj": "12345678900",
                "dados": {"access_token": "segredo", "campo": "permitido"},
            }
        )

        self.assertEqual(resultado["cpf_cnpj"], "[REMOVIDO]")
        self.assertEqual(resultado["dados"]["access_token"], "[REMOVIDO]")
        self.assertEqual(resultado["dados"]["campo"], "permitido")

    def test_evento_e_imutavel_por_instancia(self):
        evento = registrar_evento_auditoria(
            escritorio=self.escritorio,
            ator=self.owner,
            acao="teste.criado",
            recurso_tipo="teste",
            recurso_id="1",
        )
        evento.acao = "teste.alterado"

        with self.assertRaises(TypeError):
            evento.save()
        with self.assertRaises(TypeError):
            evento.delete()

    def test_endpoint_e_somente_leitura_para_owner(self):
        registrar_evento_auditoria(
            escritorio=self.escritorio,
            ator=self.owner,
            acao="teste.criado",
            recurso_tipo="teste",
            recurso_id="1",
        )
        client = APIClient()
        client.force_authenticate(self.owner)

        listado = client.get(reverse("auditoria-list"))
        escrita = client.post(reverse("auditoria-list"), {}, format="json")

        self.assertEqual(listado.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listado.data), 1)
        self.assertEqual(escrita.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_advogado_nao_le_auditoria(self):
        advogado = get_user_model().objects.create_user(
            username="adv-audit", password="senha-forte"
        )
        MembroEscritorio.objects.create(
            escritorio=self.escritorio,
            usuario=advogado,
            papel=MembroEscritorio.Papel.ADVOGADO,
        )
        client = APIClient()
        client.force_authenticate(advogado)

        response = client.get(reverse("auditoria-list"))

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

