from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from .crypto_utils import encrypt_data, hash_data
from .models import Cliente, EventoAgenda, Processo


def criar_cliente(usuario, documento="12345678900", nome="João Silva"):
    return Cliente.objects.create(
        usuario=usuario,
        nome=nome,
        cpf_cnpj=encrypt_data(documento),
        cpf_cnpj_hash=hash_data(documento),
        tipo="PF",
        email="cliente@example.com",
    )


class ApiAuthenticationTests(TestCase):
    def test_rotas_de_negocio_exigem_autenticacao(self):
        response = APIClient().get(reverse("cliente-list"))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_aceita_email(self):
        get_user_model().objects.create_user(
            username="advogado",
            email="advogado@example.com",
            password="senha-forte-123",
        )
        response = APIClient().post(
            reverse("token_obtain_pair"),
            {"username": "advogado@example.com", "password": "senha-forte-123"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["username"], "advogado")


class AuthenticatedApiTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username="gestor",
            email="gestor@example.com",
            password="senha-forte-de-teste",
        )
        self.client.force_authenticate(self.user)


class ClienteApiTests(AuthenticatedApiTestCase):
    def test_crud_cliente_criptografa_e_valida_documento_unico(self):
        payload = {
            "nome": "João Silva",
            "cpf_cnpj": "123.456.789-00",
            "email": "joao@example.com",
            "telefone": "(98) 99999-0000",
            "tipo": "PF",
        }
        created = self.client.post(reverse("cliente-list"), payload, format="json")
        cliente = Cliente.objects.get()

        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["cpf_cnpj"], "12345678900")
        self.assertNotEqual(cliente.cpf_cnpj, "12345678900")
        self.assertTrue(cliente.cpf_cnpj_hash)

        duplicate = self.client.post(reverse("cliente-list"), payload, format="json")
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)

        updated = self.client.patch(
            reverse("cliente-detail", args=[cliente.id]),
            {"nome": "João da Silva"},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["nome"], "João da Silva")

        deleted = self.client.delete(reverse("cliente-detail", args=[cliente.id]))
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_usuario_nao_enxerga_cliente_de_outro_usuario(self):
        outro = get_user_model().objects.create_user(username="outro", password="senha-forte")
        criar_cliente(outro)
        response = self.client.get(reverse("cliente-list"))
        self.assertEqual(response.data, [])


class ProcessoApiTests(AuthenticatedApiTestCase):
    def setUp(self):
        super().setUp()
        self.cliente = criar_cliente(self.user)

    def payload(self):
        return {
            "numero_cnj": "0010234-56.2024.5.16.0001",
            "titulo": "Reclamação trabalhista",
            "area": "TRABALHISTA",
            "vara": "1ª Vara do Trabalho de São Luís",
            "comarca": "São Luís",
            "cliente": self.cliente.id,
            "parte_contraria": "Empresa ABC",
            "status": "ATIVO",
            "resultado": "PENDENTE",
        }

    def test_crud_processo_e_protecao_do_cliente(self):
        created = self.client.post(reverse("processo-list"), self.payload(), format="json")
        processo_id = created.data["id"]
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        self.assertEqual(created.data["cliente_nome"], self.cliente.nome)

        updated = self.client.patch(
            reverse("processo-detail", args=[processo_id]),
            {"status": "ARQUIVADO", "resultado": "FAVORAVEL"},
            format="json",
        )
        self.assertEqual(updated.status_code, status.HTTP_200_OK)
        self.assertEqual(updated.data["resultado"], "FAVORAVEL")

        protected = self.client.delete(reverse("cliente-detail", args=[self.cliente.id]))
        self.assertEqual(protected.status_code, status.HTTP_409_CONFLICT)

        deleted = self.client.delete(reverse("processo-detail", args=[processo_id]))
        self.assertEqual(deleted.status_code, status.HTTP_204_NO_CONTENT)

    def test_rejeita_cliente_de_outro_usuario(self):
        outro = get_user_model().objects.create_user(username="outro", password="senha-forte")
        cliente_alheio = criar_cliente(outro, "12345678901")
        payload = self.payload() | {"cliente": cliente_alheio.id}
        response = self.client.post(reverse("processo-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class EventoAgendaApiTests(AuthenticatedApiTestCase):
    def test_crud_evento_e_validacao_de_horario(self):
        inicio = timezone.now() + timedelta(days=1)
        payload = {
            "titulo": "Prazo de recurso",
            "tipo": "PRAZO",
            "inicio": inicio.isoformat(),
            "fim": (inicio + timedelta(hours=1)).isoformat(),
            "local": "Sistema eletrônico",
            "concluido": False,
        }
        created = self.client.post(reverse("evento-list"), payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        updated = self.client.patch(
            reverse("evento-detail", args=[created.data["id"]]),
            {"concluido": True},
            format="json",
        )
        self.assertTrue(updated.data["concluido"])

        invalid = self.client.post(
            reverse("evento-list"),
            payload | {"fim": (inicio - timedelta(hours=1)).isoformat()},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)


class IndicadoresApiTests(AuthenticatedApiTestCase):
    def test_dashboard_e_jurimetria_refletem_dados_do_usuario(self):
        cliente = criar_cliente(self.user)
        Processo.objects.create(
            usuario=self.user,
            cliente=cliente,
            numero_cnj="0010234-56.2024.5.16.0001",
            vara="1ª Vara",
            comarca="São Luís",
            parte_contraria="Empresa ABC",
            status="ATIVO",
            resultado="FAVORAVEL",
        )
        EventoAgenda.objects.create(
            usuario=self.user,
            titulo="Audiência inicial",
            tipo="AUDIENCIA",
            inicio=timezone.now() + timedelta(days=1),
        )

        dashboard = self.client.get(reverse("dashboard"))
        jurimetria = self.client.get(reverse("jurimetria"))

        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.data["metricas"]["processos_ativos"], 1)
        self.assertEqual(jurimetria.data["total_analisados"], 1)
        self.assertEqual(jurimetria.data["taxa_favoravel"], 100)
