from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from organizations.models import Escritorio, MembroEscritorio

from .estatistica import intervalo_wilson, taxa_com_contexto
from .models import Cliente, Processo


class IntervaloWilsonTests(SimpleTestCase):
    def test_valores_de_referencia(self):
        # 20 de 40: valor clássico da tabela de Wilson, 35,2% a 64,8%
        minimo, maximo = intervalo_wilson(20, 40)
        self.assertAlmostEqual(minimo, 0.352, places=3)
        self.assertAlmostEqual(maximo, 0.648, places=3)

    def test_zero_sucessos_tem_teto_mas_nunca_limite_negativo(self):
        # 0 de 10: o teto é z²/(n+z²) = 0,2775; a normal daria um intervalo degenerado
        minimo, maximo = intervalo_wilson(0, 10)
        self.assertEqual(minimo, 0.0)
        self.assertAlmostEqual(maximo, 0.2775, places=4)

    def test_todos_sucessos_nao_passa_de_100_por_cento(self):
        minimo, maximo = intervalo_wilson(10, 10)
        self.assertEqual(maximo, 1.0)
        self.assertAlmostEqual(minimo, 0.7225, places=4)

    def test_intervalo_estreita_com_mais_casos_na_mesma_proporcao(self):
        pequeno = intervalo_wilson(6, 10)
        grande = intervalo_wilson(600, 1000)
        self.assertGreater(pequeno[1] - pequeno[0], grande[1] - grande[0])

    def test_total_zero_nao_divide_por_zero(self):
        self.assertEqual(intervalo_wilson(0, 0), (0.0, 1.0))


class TaxaComContextoTests(SimpleTestCase):
    def test_abaixo_do_piso_suprime_a_taxa_e_diz_por_que(self):
        taxa = taxa_com_contexto(1, 1, piso=10)

        self.assertFalse(taxa["suficiente"])
        self.assertIsNone(taxa["favoravel"])
        self.assertIsNone(taxa["intervalo_favoravel"])
        self.assertIn("1 de no mínimo 10", taxa["motivo"])

    def test_no_piso_exato_ja_exibe(self):
        self.assertTrue(taxa_com_contexto(5, 10, piso=10)["suficiente"])

    def test_um_abaixo_do_piso_ainda_suprime(self):
        self.assertFalse(taxa_com_contexto(5, 9, piso=10)["suficiente"])

    def test_acima_do_piso_traz_taxa_n_e_intervalo(self):
        taxa = taxa_com_contexto(7, 10, piso=10)

        self.assertEqual(taxa["favoravel"], 70)
        self.assertEqual(taxa["total"], 10)
        self.assertLess(taxa["intervalo_favoravel"]["min"], 70)
        self.assertGreater(taxa["intervalo_favoravel"]["max"], 70)

    def test_favoravel_e_desfavoravel_sempre_somam_100(self):
        for favoraveis in range(0, 31):
            with self.subTest(favoraveis=favoraveis):
                taxa = taxa_com_contexto(favoraveis, 30, piso=10)
                self.assertEqual(taxa["favoravel"] + taxa["desfavoravel"], 100)

    def test_total_zero_fica_suprimido(self):
        self.assertFalse(taxa_com_contexto(0, 0, piso=10)["suficiente"])


@override_settings(JURIMETRIA_PISO_AMOSTRA=5)
class JurimetriaEndpointTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="a", email="a@x.com", password="x")
        self.escritorio = Escritorio.objects.create(nome="Banca", criado_por=self.user)
        MembroEscritorio.objects.create(
            escritorio=self.escritorio, usuario=self.user, papel="OWNER"
        )
        self.cliente = Cliente.objects.create(
            escritorio=self.escritorio, usuario=self.user, nome="C", cpf_cnpj="x"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.contador = 0

    def _processos(self, vara, resultado, quantidade):
        for _ in range(quantidade):
            self.contador += 1
            Processo.objects.create(
                escritorio=self.escritorio,
                usuario=self.user,
                cliente=self.cliente,
                numero_cnj=f"{self.contador:07d}-00.2024.5.16.0001",
                vara=vara,
                comarca="São Luís",
                parte_contraria="X",
                resultado=resultado,
            )

    def _get(self):
        return self.client.get(
            reverse("jurimetria"), HTTP_X_ESCRITORIO_ID=str(self.escritorio.pk)
        ).data

    def test_carteira_sem_resultados_nao_inventa_taxa(self):
        dados = self._get()

        self.assertEqual(dados["total_analisados"], 0)
        self.assertIsNone(dados["taxa_favoravel"])
        self.assertFalse(dados["amostra_suficiente"])
        self.assertEqual(dados["piso_amostra"], 5)

    def test_amostra_pequena_suprime_a_taxa_geral_e_explica_no_texto(self):
        self._processos("1ª Vara", "FAVORAVEL", 3)

        dados = self._get()

        self.assertIsNone(dados["taxa_favoravel"])
        self.assertIn("mínimo é 5", dados["insight"])
        self.assertNotIn("100%", dados["insight"])

    def test_taxa_geral_vem_com_intervalo_quando_ha_amostra(self):
        self._processos("1ª Vara", "FAVORAVEL", 6)
        self._processos("1ª Vara", "DESFAVORAVEL", 4)

        dados = self._get()

        self.assertEqual(dados["taxa_favoravel"], 60)
        self.assertTrue(dados["amostra_suficiente"])
        self.assertLess(dados["intervalo_favoravel"]["min"], 60)
        self.assertGreater(dados["intervalo_favoravel"]["max"], 60)
        self.assertIn("intervalo de confiança", dados["insight"])

    def test_cada_vara_e_avaliada_pela_propria_amostra(self):
        self._processos("Vara Grande", "FAVORAVEL", 4)
        self._processos("Vara Grande", "DESFAVORAVEL", 4)
        self._processos("Vara Pequena", "FAVORAVEL", 2)

        por_vara = {v["vara"]: v for v in self._get()["por_vara"]}

        self.assertTrue(por_vara["Vara Grande"]["suficiente"])
        self.assertEqual(por_vara["Vara Grande"]["favoravel"], 50)
        self.assertFalse(por_vara["Vara Pequena"]["suficiente"])
        self.assertIsNone(por_vara["Vara Pequena"]["favoravel"])
        self.assertEqual(por_vara["Vara Pequena"]["total"], 2)

    def test_so_conta_a_carteira_do_proprio_escritorio(self):
        self._processos("1ª Vara", "FAVORAVEL", 8)
        outro_dono = get_user_model().objects.create_user(username="o", email="o@x.com", password="x")
        outro = Escritorio.objects.create(nome="Outra", criado_por=outro_dono)
        cliente = Cliente.objects.create(escritorio=outro, usuario=outro_dono, nome="C", cpf_cnpj="y")
        for i in range(20):
            Processo.objects.create(
                escritorio=outro, usuario=outro_dono, cliente=cliente,
                numero_cnj=f"9{i:06d}-00.2024.5.16.0001", vara="V", comarca="C",
                parte_contraria="X", resultado="DESFAVORAVEL",
            )

        dados = self._get()

        self.assertEqual(dados["total_analisados"], 8)
        self.assertEqual(dados["taxa_favoravel"], 100)
