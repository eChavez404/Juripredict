"""Base da jurimetria do tribunal: qual documento vale pelo processo e o que sai sem nome."""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from exportar_jurimetria import fatiar, pseudonimizar, trechos_rag  # noqa: E402
from processar import _prevalece  # noqa: E402

MERITO = (True, True, "2025-03-10")


def test_sentenca_de_merito_prevalece_sobre_embargos_e_execucao_em_qualquer_ordem():
    embargos = (False, True, "2025-04-02")
    assert _prevalece(MERITO, embargos)
    assert not _prevalece(embargos, MERITO)
    assert _prevalece(MERITO, None)


def test_entre_duas_de_merito_fica_a_primeira_e_a_com_resultado():
    depois = (True, True, "2025-06-01")
    assert not _prevalece(depois, MERITO)
    assert _prevalece(MERITO, depois)
    assert _prevalece(MERITO, (True, False, "2025-01-01"))
    assert not _prevalece((True, True, None), MERITO)


# palavras comuns que aparecem minusculas no corpus; nomes nunca aparecem
CORPUS = Counter({p: 10 for p in (
    "julgar", "procedentes", "parcialmente", "pedidos", "formulados", "empresa", "brasileira",
    "adicional", "insalubridade", "pagar", "reclamada", "dias", "restaurante", "vale")})


def test_nome_de_pessoa_e_de_empresa_sai_inteiro():
    casos = {
        "JULGAR PARCIALMENTE PROCEDENTES os pedidos formulados por MARIA DIAS SOUSA em face de "
        "EMPRESA BRASILEIRA DE CORREIOS E TELEGRAFOS, para condenar":
            "JULGAR PARCIALMENTE PROCEDENTES os pedidos formulados por [parte] em face de [parte], "
            "para condenar",
        "movida por Josefa Lima contra R de F Ribamar (Restaurante Sabor)":
            "movida por [parte] contra [parte] ([parte])",
        "a segunda reclamada Alumar S.A., a pagar o adicional de insalubridade":
            "a segunda reclamada [parte], a pagar o adicional de insalubridade",
        "CPF 123.456.789-09 da Sra. Francisca":
            "CPF [documento] da [parte]",
    }
    for trecho, esperado in casos.items():
        assert pseudonimizar(trecho, CORPUS) == esperado


def test_texto_juridico_sem_nome_nao_muda():
    trecho = ("Pagar o adicional de insalubridade em grau maximo (40% sobre o salario-minimo), "
              "com reflexos em FGTS + 40%, conforme NR-15 e CLT, art. 192")
    assert pseudonimizar(trecho, CORPUS) == trecho


def test_fatiar_corta_em_espaco_com_sobra_e_cobre_o_texto_todo():
    texto = " ".join(f"palavra{i}" for i in range(400))
    pedacos = fatiar(texto, tamanho=300, sobra=50)
    assert all(len(p) <= 300 for p in pedacos)
    assert pedacos[0].startswith("palavra0 ") and pedacos[-1].endswith("palavra399")
    assert all(not p.startswith(" ") and " " in p for p in pedacos)
    assert fatiar("curto") == ["curto"]


def test_trechos_do_rag_so_das_decisoes_da_taxa_e_sem_nome():
    linhas = [
        {"caso_id": "d1:insalubridade", "populacao": "modelo", "trecho": "condenar a [parte]",
         "numero_cnj": "0000001-00.2025.5.16.0011", "vara": "VT de Balsas", "data_sentenca": "2025-01-02",
         "resultado": "deferido", "tema": "insalubridade"},
        {"caso_id": "d2:insalubridade", "populacao": "escape", "trecho": "", "numero_cnj": "x",
         "vara": "v", "data_sentenca": "", "resultado": "ambiguo", "tema": "insalubridade"},
    ]
    capitulos = {"d1:insalubridade": "O perito constatou agente biologico. MARIA SOUSA trabalhava na limpeza."}
    trechos = list(trechos_rag(linhas, capitulos, CORPUS))
    assert [t["id"] for t in trechos] == ["d1:insalubridade#0", "d1:insalubridade#1"]
    assert "MARIA" not in trechos[0]["texto"] and "[parte]" in trechos[0]["texto"]
    assert trechos[1]["texto"] == "Dispositivo: condenar a [parte]"
    assert {t["resultado"] for t in trechos} == {"deferido"}
