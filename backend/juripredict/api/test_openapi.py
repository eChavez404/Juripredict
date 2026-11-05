from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from config.openapi import DashboardRespostaSerializer, JurimetriaRespostaSerializer
from organizations.models import Escritorio, MembroEscritorio

ARQUIVO_PUBLICADO = Path(settings.BASE_DIR).parent / "openapi.yaml"


class EsquemaOpenApiTests(SimpleTestCase):
    def test_esquema_valido_sem_avisos_e_igual_ao_publicado(self):
        with TemporaryDirectory() as pasta:
            gerado = Path(pasta) / "openapi.yaml"
            call_command("spectacular", "--validate", "--fail-on-warn", "--file", str(gerado))
            self.assertEqual(
                gerado.read_text(encoding="utf-8"),
                ARQUIVO_PUBLICADO.read_text(encoding="utf-8"),
                "Regenere com: python manage.py spectacular --file ../openapi.yaml",
            )


class RespostasDocumentadasTests(TestCase):
    """O esquema dessas rotas é escrito à mão: não pode divergir do que elas devolvem."""

    def setUp(self):
        usuario = get_user_model().objects.create_user("ana", "ana@exemplo.invalid", "x")
        escritorio = Escritorio.objects.create(nome="Escritório", criado_por=usuario)
        MembroEscritorio.objects.create(
            escritorio=escritorio, usuario=usuario, papel=MembroEscritorio.Papel.OWNER
        )
        self.cliente = APIClient()
        self.cliente.force_authenticate(usuario)

    def test_jurimetria(self):
        resposta = self.cliente.get("/api/v1/jurimetria/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(set(resposta.data), set(JurimetriaRespostaSerializer().fields))

    def test_dashboard(self):
        resposta = self.cliente.get("/api/v1/dashboard/")
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(set(resposta.data), set(DashboardRespostaSerializer().fields))


class SwaggerForaDeProducaoTests(TestCase):
    def test_rotas_de_documentacao_nao_existem_com_debug_desligado(self):
        # O executor de testes roda com DEBUG=False, como em produção.
        for rota in ("/api/docs/", "/api/schema/"):
            self.assertEqual(self.client.get(rota).status_code, 404)
