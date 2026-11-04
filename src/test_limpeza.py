"""Confere as regras de limpeza que sustentam a TED 02. Uso: python -m pytest src/test_limpeza.py"""

import json

from ted02_limpar_e_explorar import ano_referencia, construir_lexico, limpar_movimentacao, textos_json_plano


def test_remove_formatacao_e_prefixo_de_tribunal():
    assert limpar_movimentacao("Tipo do Movimento:Publicado\xa0 Atos\r\n da Serventia") == "Publicado Atos da Serventia"


def test_mascara_identificadores_e_numeros():
    texto = limpar_movimentacao(
        "Proc. 0001234-56.2023.8.26.0100 CPF 123.456.789-00 OAB/SP 123.456 "
        "R$ 1.234,56 em 02/02/2019, fls 685"
    )
    assert texto == "Proc. tkcnj CPF tkdoc tkoab tkvalor em tkdata, fls tknum"


def test_ano_ignora_datas_impossiveis_ou_futuras():
    assert ano_referencia(["em 31/13/2018 e 01/02/2055", "em 15/06/2017"]) == 2017
    assert ano_referencia(["sem data"]) is None


def test_mascara_nomes_sem_apagar_termos_juridicos():
    textos = [
        "Advogados(s): Hélio de Souza (OAB 123/SP)", "Intimado Hélio Souza OAB/SP 9",
        "Decisão proferida", "Decisão Hélio OAB 1", "a decisão",
    ]
    lexico = construir_lexico(textos)
    assert {"hélio", "souza"} <= lexico and "decisão" not in lexico
    assert limpar_movimentacao("Decisão intima Hélio de Souza", lexico=lexico) == "Decisão intima tknome"


def test_lexico_nao_captura_minusculas_nem_orgaos():
    lexico = construir_lexico(["parte autora pediu", "parte Beltrano", "Tribunal OAB/SP 9", "x Tribunal Fulano OAB/SP 9"])
    assert {"beltrano", "fulano"} <= lexico and not {"autora", "pediu", "tribunal", "oab"} & lexico
    assert limpar_movimentacao("Fulano OAB/SP 9", lexico=lexico) == "tknome tkoab"


def test_lexico_alcanca_sobrenome_colado_a_nome_conhecido():
    lexico = construir_lexico(["x Fulano OAB/SP 9", "intimado Fulano Guerra hoje", "Despacho proferido"])
    assert "guerra" in lexico and "despacho" not in lexico


def test_leitura_em_fluxo_igual_ao_json(tmp_path):
    original = {"0": 'aspas " e \\ barra', "1": "acentuação\nquebra", "2": ""}
    arquivo = tmp_path / "plano.json"
    arquivo.write_text(json.dumps(original), encoding="utf-8")
    assert list(textos_json_plano(arquivo)) == list(original.values())
