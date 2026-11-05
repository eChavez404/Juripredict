from datetime import date

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from .prazos import (
    INFORMADO,
    INTIMACAO,
    PUBLICACAO_DIARIO,
    RECESSO,
    calcular_prazo,
    dias_a_conferir_no_ano,
    feriados_nacionais,
    pascoa,
)


def vencimento(data_base, dias, tipo=INTIMACAO, **extra):
    return calcular_prazo(data_base=data_base, dias=dias, tipo=tipo, **extra)["vencimento"]


class CalendarioTests(SimpleTestCase):
    def test_pascoa_em_anos_conhecidos(self):
        for ano, esperada in (
            (2000, date(2000, 4, 23)),
            (2024, date(2024, 3, 31)),
            (2025, date(2025, 4, 20)),
            (2026, date(2026, 4, 5)),
            (2027, date(2027, 3, 28)),
            (2038, date(2038, 4, 25)),
        ):
            self.assertEqual(pascoa(ano), esperada)

    def test_datas_moveis_de_2026_batem_com_o_calendario_do_trt16(self):
        conferir = dias_a_conferir_no_ano(2026)
        for dia, nome in (
            (date(2026, 4, 1), "Quarta-feira da Semana Santa"),
            (date(2026, 4, 3), "Sexta-feira da Paixão"),
            (date(2026, 6, 4), "Corpus Christi"),
            (date(2026, 12, 8), "Dia da Justiça"),
        ):
            self.assertEqual(conferir[dia], nome)

    def test_consciencia_negra_so_e_feriado_nacional_a_partir_de_2024(self):
        self.assertNotIn(date(2023, 11, 20), feriados_nacionais(2023))
        self.assertIn(date(2024, 11, 20), feriados_nacionais(2024))


class ContagemTests(SimpleTestCase):
    def test_exclui_o_dia_do_comeco_e_inclui_o_do_vencimento(self):
        # intimação na segunda 9/3; 5 dias: 10, 11, 12, 13 e 16 (pula sábado e domingo)
        resultado = calcular_prazo(data_base=date(2026, 3, 9), dias=5)
        self.assertEqual(resultado["primeiro_dia_contado"], date(2026, 3, 10))
        self.assertEqual(resultado["vencimento"], date(2026, 3, 16))
        self.assertEqual(resultado["fins_de_semana_nao_contados"], 2)

    def test_sumula_1_intimacao_na_sexta_conta_desde_segunda(self):
        resultado = calcular_prazo(data_base=date(2026, 3, 6), dias=8)
        self.assertEqual(resultado["primeiro_dia_contado"], date(2026, 3, 9))
        self.assertEqual(resultado["vencimento"], date(2026, 3, 18))

    def test_sumula_262_intimacao_no_sabado_comeca_na_segunda_e_conta_na_terca(self):
        resultado = calcular_prazo(data_base=date(2026, 3, 7), dias=8)
        self.assertEqual(resultado["marco_inicial"], date(2026, 3, 9))
        self.assertEqual(resultado["primeiro_dia_contado"], date(2026, 3, 10))
        self.assertEqual(resultado["vencimento"], date(2026, 3, 19))

    def test_diario_eletronico_publica_no_dia_util_seguinte_e_conta_depois(self):
        # disponibilizado na sexta 6/3: publicação na segunda 9/3, contagem a partir da terça 10/3
        resultado = calcular_prazo(data_base=date(2026, 3, 6), dias=8, tipo=PUBLICACAO_DIARIO)
        self.assertEqual(resultado["marco_inicial"], date(2026, 3, 9))
        self.assertEqual(resultado["primeiro_dia_contado"], date(2026, 3, 10))
        self.assertEqual(resultado["vencimento"], date(2026, 3, 19))

    def test_diario_disponibilizado_em_dia_util_comum(self):
        # terça 10/3: publicação 11/3, contagem de 12/3; 5 dias: 12, 13, 16, 17 e 18
        self.assertEqual(vencimento(date(2026, 3, 10), 5, PUBLICACAO_DIARIO), date(2026, 3, 18))

    def test_feriado_nacional_nao_conta_e_aparece_na_memoria(self):
        # 20/4/2026; 21/4 é Tiradentes; 5 dias: 22, 23, 24, 27 e 28
        resultado = calcular_prazo(data_base=date(2026, 4, 20), dias=5)
        self.assertEqual(resultado["vencimento"], date(2026, 4, 28))
        self.assertEqual(
            resultado["dias_nao_contados"],
            [{"data": date(2026, 4, 21), "motivo": "Feriado nacional: Tiradentes"}],
        )

    def test_prazo_em_curso_fica_suspenso_de_20_12_a_20_1(self):
        # quinta 18/12/2025; 19/12 é o dia 1; volta em 21/1/2026: 21, 22, 23, 26, 27, 28 e 29
        resultado = calcular_prazo(data_base=date(2025, 12, 18), dias=8)
        self.assertEqual(resultado["vencimento"], date(2026, 1, 29))
        recesso = [d["data"] for d in resultado["dias_nao_contados"] if d["motivo"] == RECESSO]
        self.assertEqual((recesso[0], recesso[-1]), (date(2025, 12, 20), date(2026, 1, 20)))

    def test_nunca_vence_em_dia_que_nao_corre(self):
        for dias in range(1, 120):
            fim = vencimento(date(2026, 1, 2), dias)
            self.assertLess(fim.weekday(), 5, dias)
            self.assertNotIn(fim, feriados_nacionais(fim.year), dias)

    def test_ciencia_durante_a_suspensao_avisa_e_conta_depois_dela(self):
        resultado = calcular_prazo(data_base=date(2026, 1, 5), dias=1)
        self.assertEqual(resultado["marco_inicial"], date(2026, 1, 21))
        self.assertEqual(resultado["vencimento"], date(2026, 1, 22))
        self.assertEqual(len(resultado["ressalvas"]), 2)

    def test_diario_disponibilizado_na_suspensao_publica_depois_dela(self):
        # Resolução CSJT 185/2017, art. 28: publicação em 21/1, contagem a partir de 22/1
        resultado = calcular_prazo(data_base=date(2026, 1, 5), dias=1, tipo=PUBLICACAO_DIARIO)
        self.assertEqual(resultado["marco_inicial"], date(2026, 1, 21))
        self.assertEqual(resultado["vencimento"], date(2026, 1, 22))


class RegraDeSegurancaTests(SimpleTestCase):
    def test_dia_incerto_e_contado_e_sinalizado(self):
        # Semana Santa de 2026, que o TRT-16 suspendeu por ato próprio
        resultado = calcular_prazo(data_base=date(2026, 3, 30), dias=5)
        self.assertEqual(resultado["vencimento"], date(2026, 4, 6))
        self.assertEqual(
            [d["data"] for d in resultado["dias_a_conferir"]],
            [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)],
        )

    def test_informar_a_suspensao_recua_a_data_e_fica_registrado(self):
        suspensas = [date(2026, 4, 1), date(2026, 4, 2), date(2026, 4, 3)]
        resultado = calcular_prazo(data_base=date(2026, 3, 30), dias=5, suspensoes=suspensas)
        # 31/3, 6/4, 7/4, 8/4 e 9/4
        self.assertEqual(resultado["vencimento"], date(2026, 4, 9))
        self.assertEqual(resultado["dias_a_conferir"], [])
        self.assertEqual(
            [d["motivo"] for d in resultado["dias_nao_contados"]], [INFORMADO] * 3
        )

    def test_calculo_sem_informar_nunca_passa_do_calculo_informando(self):
        # a propriedade que justifica o desenho: ignorar uma suspensão só antecipa a data
        for dias in (1, 5, 8, 15, 30):
            for mes in range(1, 13):
                base = date(2026, mes, 10)
                conferir = list(dias_a_conferir_no_ano(2026))
                self.assertLessEqual(
                    vencimento(base, dias), vencimento(base, dias, suspensoes=conferir)
                )

    def test_civel_segue_a_mesma_contagem_com_fundamento_proprio(self):
        resultado = calcular_prazo(data_base=date(2026, 3, 9), dias=5, area="CIVEL")
        self.assertEqual(resultado["vencimento"], date(2026, 3, 16))
        self.assertIn("CPC", resultado["fundamento"])


class RotaDeCalculoTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(
            get_user_model().objects.create_user("a@exemplo.invalid", "a@exemplo.invalid", "x")
        )

    def _get(self, **params):
        return self.api.get("/api/v1/prazos/calcular/", params)

    def test_calcula_e_devolve_a_memoria(self):
        resposta = self._get(data_base="2026-03-07", dias=8)
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.json()["vencimento"], "2026-03-19")
        self.assertIn("CLT", resposta.json()["fundamento"])

    def test_aceita_varias_suspensoes_repetindo_o_parametro(self):
        resposta = self.api.get(
            "/api/v1/prazos/calcular/?data_base=2026-03-30&dias=5"
            "&suspensoes=2026-04-01&suspensoes=2026-04-02&suspensoes=2026-04-03"
        )
        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.assertEqual(resposta.json()["vencimento"], "2026-04-09")

    def test_exige_login(self):
        self.assertEqual(
            APIClient().get("/api/v1/prazos/calcular/", {"data_base": "2026-03-07", "dias": 8}).status_code,
            401,
        )

    def test_recusa_parametros_invalidos(self):
        for params in (
            {},
            {"data_base": "2026-03-07"},
            {"data_base": "abc", "dias": 8},
            {"data_base": "2026-02-31", "dias": 8},
            {"data_base": "2026-03-07", "dias": 0},
            {"data_base": "2026-03-07", "dias": 366},
            {"data_base": "2026-03-07", "dias": "x"},
            {"data_base": "9999-12-31", "dias": 8},
            {"data_base": "2026-03-07", "dias": 8, "tipo": "OUTRO"},
            {"data_base": "2026-03-07", "dias": 8, "suspensoes": "abc"},
        ):
            self.assertEqual(self._get(**params).status_code, 400, params)

    def test_area_com_contagem_propria_e_recusada_com_o_motivo(self):
        # no processo penal o prazo é contínuo (CPP, art. 798): devolver dias úteis seria errado
        for area in ("CRIMINAL", "PREVIDENCIARIO", "TRIBUTARIO", "OUTRO"):
            resposta = self._get(data_base="2026-03-07", dias=8, area=area)
            self.assertEqual(resposta.status_code, 400, area)
            self.assertIn("area", resposta.json())
