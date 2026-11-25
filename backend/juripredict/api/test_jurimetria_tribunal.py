import io
import json
from datetime import date
from tempfile import NamedTemporaryFile

from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings

from .jurimetria_tribunal import COLUNAS, importar
from .models import DecisaoTribunal, LoteDecisoesTribunal
from .test_papeis import PAPEL, PapeisBase

ROTA = "/api/v1/jurimetria/tribunal/"
CONFERIDO = {"anotados": 70, "concordancia_deferido": 0.95, "concordancia_indeferido": 0.93}


def _csv(linhas):
    saida = io.StringIO()
    saida.write(",".join(sorted(COLUNAS)) + "\n")
    for linha in linhas:
        saida.write(",".join(str(linha.get(c, "")) for c in sorted(COLUNAS)) + "\n")
    saida.seek(0)
    return saida


def decisao(n, **campos):
    return {
        "caso_id": f"d{n}:insalubridade", "numero_cnj": f"{n:07d}-00.2025.5.16.0001",
        "tema": "insalubridade", "vara": "Vara do Trabalho de Balsas", "data_sentenca": "2025-05-10",
        "resultado": "deferido", "grau": "40", "populacao": "modelo", "motivo_fora": "",
        "mecanismo": "regra_direta", "trecho": "Pagar o adicional de insalubridade em grau máximo",
        "versao": "2.0/regra-2026.09", **campos,
    }


@override_settings(JURIMETRIA_PISO_AMOSTRA=10)
class JurimetriaTribunalTests(PapeisBase):
    def setUp(self):
        super().setUp()
        self.api = self.como(PAPEL.ADVOGADO)

    def base(self, deferidos=8, indeferidos=4, validacao=None, extras=()):
        linhas = [decisao(i) for i in range(deferidos)]
        linhas += [decisao(100 + i, resultado="indeferido", grau="") for i in range(indeferidos)]
        importar(_csv([*linhas, *extras]), validacao=validacao)

    def test_sem_base_importada_diz_que_nao_ha_dados(self):
        self.assertEqual(self.api.get(ROTA).data, {"disponivel": False})

    def test_sem_conferencia_humana_mostra_o_n_mas_nao_a_taxa(self):
        self.base()

        geral = self.api.get(ROTA).data["geral"]

        self.assertEqual(geral["total"], 12)
        self.assertTrue(geral["suficiente"])
        self.assertIsNone(geral["favoravel"])
        self.assertIsNone(geral["intervalo_favoravel"])
        self.assertIn("leitura humana", geral["motivo"])

    def test_conferido_e_com_cobertura_mostra_taxa_com_intervalo_e_cobertura(self):
        self.base(validacao={"gold_set": CONFERIDO, "cobertura": {"geral": 81}})

        geral = self.api.get(ROTA).data["geral"]

        self.assertEqual((geral["favoravel"], geral["cobertura"]), (67, 81))
        self.assertEqual(geral["intervalo_favoravel"], {"min": 39, "max": 86})
        self.assertIsNone(geral["motivo"])

    def test_cobertura_e_exigida_por_recorte(self):
        self.base(validacao={"gold_set": CONFERIDO, "cobertura": {"geral": 81}})

        dados = self.api.get(ROTA, {"vara": "Vara do Trabalho de Balsas"}).data

        self.assertIsNone(dados["geral"]["favoravel"])
        self.assertIn("Cobertura", dados["geral"]["motivo"])

    def test_concordancia_baixa_em_uma_classe_mantem_a_taxa_suprimida(self):
        fraco = {**CONFERIDO, "concordancia_indeferido": 0.7}
        self.base(validacao={"gold_set": fraco, "cobertura": {"geral": 81}})

        self.assertIsNone(self.api.get(ROTA).data["geral"]["favoravel"])

    def test_abaixo_do_piso_a_taxa_some_mesmo_validada(self):
        self.base(deferidos=3, indeferidos=2, validacao={"gold_set": CONFERIDO, "cobertura": {"geral": 81}})

        geral = self.api.get(ROTA).data["geral"]

        self.assertIsNone(geral["favoravel"])
        self.assertIn("Amostra insuficiente", geral["motivo"])

    def test_o_que_fica_fora_da_taxa_aparece_com_o_motivo(self):
        extras = [
            decisao(200, resultado="ambiguo", populacao="escape", motivo_fora="ambiguo"),
            decisao(201, resultado="deferido", populacao="fora_da_populacao", motivo_fora="EXECUCAO"),
            decisao(202, resultado="deferido", populacao="coletiva", motivo_fora="acao_coletiva"),
        ]
        self.base(extras=extras)

        dados = self.api.get(ROTA).data

        self.assertEqual(dados["geral"]["total"], 12)
        motivos = {item["motivo"] for item in dados["fora_da_taxa"]}
        self.assertEqual(len(motivos), 3)
        self.assertTrue(any("coletiva" in m for m in motivos))

    def test_filtros_por_tema_vara_e_ano(self):
        extras = [
            decisao(300, vara="1ª Vara do Trabalho de São Luís", data_sentenca="2024-02-01"),
            decisao(301, caso_id="p1:periculosidade", tema="periculosidade"),
        ]
        self.base(extras=extras)

        self.assertEqual(self.api.get(ROTA, {"ano": "2024"}).data["geral"]["total"], 1)
        self.assertEqual(self.api.get(ROTA, {"tema": "periculosidade"}).data["geral"]["total"], 1)
        varas = self.api.get(ROTA).data["opcoes"]["varas"]
        self.assertEqual(len(varas), 2)
        for invalido in ({"tema": "horas_extras"}, {"ano": "dois mil"}):
            self.assertEqual(self.api.get(ROTA, invalido).status_code, 400)

    def test_lista_das_decisoes_com_contagem_trecho_e_filtro_por_resultado(self):
        self.base(extras=[decisao(400, populacao="escape", resultado="ambiguo")])

        lista = self.api.get(f"{ROTA}decisoes/", {"resultado": "indeferido"}).data

        self.assertEqual(lista["contagem"], {"deferido": 8, "indeferido": 4})
        self.assertEqual(lista["total"], 4)
        self.assertEqual({d["resultado"] for d in lista["decisoes"]}, {"indeferido"})
        self.assertIn("trecho", lista["decisoes"][0])

    def test_estagiario_e_token_de_api_nao_veem(self):
        self.base()
        self.assertEqual(self.como(PAPEL.ESTAGIARIO).get(ROTA).status_code, 403)
        self.assertEqual(self.com_token(PAPEL.ADVOGADO).get(ROTA).status_code, 403)


class ImportacaoTests(TestCase):
    def test_reimportar_substitui_a_base_inteira(self):
        importar(_csv([decisao(1), decisao(2)]))
        importar(_csv([decisao(3)]))

        self.assertEqual(list(DecisaoTribunal.objects.values_list("caso_id", flat=True)), ["d3:insalubridade"])
        self.assertEqual(LoteDecisoesTribunal.objects.count(), 2)

    def test_arquivo_errado_nao_apaga_a_base_atual(self):
        importar(_csv([decisao(1)]))
        for ruim in (io.StringIO("caso_id,tema\nx,insalubridade\n"), _csv([decisao(2, tema="horas_extras")])):
            with self.subTest(), self.assertRaises(ValueError):
                importar(ruim)
        self.assertEqual(DecisaoTribunal.objects.count(), 1)
        self.assertEqual(DecisaoTribunal.objects.get().data_sentenca, date(2025, 5, 10))

    def test_comando_importa_e_informa_se_a_taxa_esta_liberada(self):
        with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as arquivo:
            arquivo.write(_csv([decisao(1)]).getvalue())
        with NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as validacao:
            json.dump({"gold_set": CONFERIDO}, validacao)
        saida = io.StringIO()

        call_command("importar_decisoes_trt", arquivo.name, "--validacao", validacao.name, stdout=saida)

        self.assertIn("1 decisões importadas", saida.getvalue())
        self.assertIn("Taxas liberadas", saida.getvalue())
        with self.assertRaises(CommandError):
            call_command("importar_decisoes_trt", "nao-existe.csv", stdout=io.StringIO())
