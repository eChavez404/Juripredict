"""Testes do coletor. Sem rede: o cliente HTTP e substituido por um duble.

    pytest -v
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collector.audit import auditar_lote, auditar_manifest
from collector.client import PAGE_SIZE_MAX, ClienteFalcao
from collector.collector import coletar
from collector.models import Consulta, Documento, ErroFalcao, ErroSessao, Pagina
from collector.normalize import contar_base64, html_para_texto
from collector.session import valido, mascarar
from collector.storage import Armazenamento, sha256

CONSULTA = Consulta("insalubridade", "TRT16", "sentencas", "2024-01-01", "2026-08-18")


def doc(id_sentenca, cnj="0016667-53.2023.5.16.0012", texto="<p>ok</p>"):
    return {
        "idSentenca": id_sentenca,
        "numeroProcesso": cnj,
        "classeProcessual": "ATSum",
        "classeProcessualPorExtenso": "Ação Trabalhista - Rito Sumaríssimo",
        "orgaoJulgador": "59",
        "orgaoJulgadorPorExtenso": "1ª Vara do Trabalho de Imperatriz",
        "tribunal": "TRT16",
        "tipoDocumento": "Sentença",
        "textoSentenca": texto,
        "dataJulgamento": "13/09/2024",
        "dataJuntada": "13/09/2024",
        "score": 138.68513,
    }


class ClienteFalso(ClienteFalcao):
    """Duble: devolve paginas programadas, sem tocar na rede."""

    def __init__(self, paginas, total=6983):
        self.paginas = paginas
        self.total = total
        self.chamadas = []

    def buscar_pagina(self, consulta, page, size=PAGE_SIZE_MAX):
        if page < 0:
            raise ValueError("page e zero-based; nao aceita negativo")
        if size > PAGE_SIZE_MAX:
            raise ValueError(f"size={size} e recusado pelo servidor.")
        self.chamadas.append((page, size))
        docs = self.paginas[page] if page < len(self.paginas) else []
        return Pagina.de_json(page, {"documentos": docs, "temasTopFive": [],
                                     "quantidadeTotal": self.total})


# paginacao
def test_paginacao_e_zero_based(tmp_path):
    cliente = ClienteFalso([[doc(f"{i}")] for i in range(3)])
    arm = Armazenamento(str(tmp_path))
    coletar(cliente, arm, CONSULTA, paginas=3, normalizar=False)
    arm.fechar()
    assert [p for p, _ in cliente.chamadas] == [0, 1, 2]


def test_page_negativo_recusado():
    cliente = ClienteFalso([[doc("1")]])
    with pytest.raises(ValueError):
        cliente.buscar_pagina(CONSULTA, -1)


# size
def test_size_acima_de_dez_recusado_antes_de_sair_da_maquina():
    cliente = ClienteFalso([[doc("1")]])
    with pytest.raises(ValueError, match="recusado pelo servidor"):
        cliente.buscar_pagina(CONSULTA, 0, size=20)
    with pytest.raises(ValueError):
        cliente.buscar_pagina(CONSULTA, 0, size=100)


def test_size_dez_passa():
    cliente = ClienteFalso([[doc(str(i)) for i in range(10)]])
    pagina = cliente.buscar_pagina(CONSULTA, 0, size=10)
    assert len(pagina.documentos) == 10
    assert len({d.id_sentenca for d in pagina.documentos}) == 10


# resposta
def test_quantidade_total_e_lida():
    cliente = ClienteFalso([[doc("1")]], total=6983)
    assert cliente.buscar_pagina(CONSULTA, 0).quantidade_total == 6983


def test_resposta_vazia_para_a_coleta(tmp_path):
    cliente = ClienteFalso([[doc("1")], [], [doc("2")]])
    arm = Armazenamento(str(tmp_path))
    res = coletar(cliente, arm, CONSULTA, paginas=3, normalizar=False)
    arm.fechar()
    assert res.paginas_baixadas == 1
    assert len(cliente.chamadas) == 2      # parou na pagina vazia


def test_quantidade_total_zero_nao_quebra():
    cliente = ClienteFalso([[]], total=0)
    pagina = cliente.buscar_pagina(CONSULTA, 0)
    assert pagina.vazia() and pagina.quantidade_total == 0


# dedup
def test_deduplicacao_por_id_sentenca_entre_paginas(tmp_path):
    # mesmo idSentenca em duas paginas: a busca ordena por score e pode repetir
    cliente = ClienteFalso([[doc("A"), doc("B")], [doc("B"), doc("C")]])
    arm = Armazenamento(str(tmp_path))
    res = coletar(cliente, arm, CONSULTA, paginas=2, normalizar=False)
    rel = auditar_lote(res.documentos)
    arm.fechar()

    assert rel["baixados"] == 4
    assert rel["ids_unicos"] == 3
    assert rel["duplicatas_id"] == {"B": 2}
    assert res.documentos_novos == 3


def test_cnj_repetido_nao_e_deduplicado(tmp_path):
    # um processo pode ter varios documentos: isso NAO pode virar descarte
    cliente = ClienteFalso([[doc("A", cnj="X"), doc("B", cnj="X")]])
    arm = Armazenamento(str(tmp_path))
    res = coletar(cliente, arm, CONSULTA, paginas=1, normalizar=False)
    rel = auditar_lote(res.documentos)
    arm.fechar()

    assert res.documentos_novos == 2
    assert rel["cnjs_unicos"] == 1
    assert rel["cnjs_com_varios_documentos"] == {"X": 2}


# idempotencia
def test_segunda_execucao_nao_rebaixa(tmp_path):
    cliente = ClienteFalso([[doc("A"), doc("B")]])
    arm = Armazenamento(str(tmp_path))
    r1 = coletar(cliente, arm, CONSULTA, paginas=1, normalizar=False)
    assert r1.documentos_novos == 2

    cliente2 = ClienteFalso([[doc("A"), doc("B")]])
    r2 = coletar(cliente2, arm, CONSULTA, paginas=1, normalizar=False)
    arm.fechar()

    assert r2.paginas_puladas == 1
    assert r2.documentos_novos == 0
    assert len(cliente2.chamadas) == 0      # nem chegou a pedir


def test_force_refaz(tmp_path):
    arm = Armazenamento(str(tmp_path))
    coletar(ClienteFalso([[doc("A")]]), arm, CONSULTA, paginas=1, normalizar=False)
    cliente = ClienteFalso([[doc("A")]])
    r = coletar(cliente, arm, CONSULTA, paginas=1, force=True, normalizar=False)
    arm.fechar()
    assert len(cliente.chamadas) == 1
    assert r.paginas_baixadas == 1


def test_raw_gravado_e_identico_ao_recebido(tmp_path):
    arm = Armazenamento(str(tmp_path))
    bruto = doc("A")
    cliente = ClienteFalso([[bruto]])
    coletar(cliente, arm, CONSULTA, paginas=1, normalizar=False)
    arm.fechar()

    gravado = json.loads(arm.caminho_documento("A").read_text(encoding="utf-8"))
    assert gravado == bruto      # nada foi filtrado nem reordenado


def test_manifest_tem_unique_em_id_e_nao_em_cnj(tmp_path):
    arm = Armazenamento(str(tmp_path))
    coletar(ClienteFalso([[doc("A", cnj="X"), doc("B", cnj="X")]]), arm, CONSULTA, paginas=1, normalizar=False)
    arm.fechar()
    rel = auditar_manifest(str(arm.manifest))
    assert rel["documentos"] == 2
    assert rel["ids_unicos"] == 2
    assert rel["cnjs_unicos"] == 1


# sessao
def test_falha_de_sessao_interrompe_sem_apagar_o_que_ja_veio(tmp_path):
    class ClienteExpira(ClienteFalso):
        def buscar_pagina(self, consulta, page, size=PAGE_SIZE_MAX):
            if page == 1:
                raise ErroSessao("Tentativa inválida de acesso ao sistema")
            return super().buscar_pagina(consulta, page, size)

    arm = Armazenamento(str(tmp_path))
    res = coletar(ClienteExpira([[doc("A")], [doc("B")]]), arm, CONSULTA, paginas=2, normalizar=False)
    arm.fechar()
    assert res.paginas_baixadas == 1
    assert res.documentos_novos == 1


def test_erro_de_negocio_vira_excecao(tmp_path):
    class ClienteRecusa(ClienteFalso):
        def buscar_pagina(self, consulta, page, size=PAGE_SIZE_MAX):
            raise ErroFalcao("Seu usuário não tem autorização para realizar " "pesquisas com páginas de tamanho 20!")

    arm = Armazenamento(str(tmp_path))
    res = coletar(ClienteRecusa([]), arm, CONSULTA, paginas=1, normalizar=False)
    arm.fechar()
    assert res.paginas_baixadas == 0


def test_formato_do_session_id():
    assert valido("_2761j7j")
    assert valido("abc123XYZ")
    assert not valido("")
    assert not valido(None)
    assert not valido("tem espaco")


def test_sessao_nunca_aparece_inteira_no_log():
    assert mascarar("_2761j7j") == "_27...7j"
    assert "2761j7j" not in mascarar("_2761j7j")


# normalize
def test_html_vira_texto_sem_tocar_no_raw():
    html = ('<html><style>p{color:red}</style><script>x=1</script>'
            '<p>Ante o exposto, julgo <b>PROCEDENTE EM PARTE</b>.</p>'
            '<img src="data:image/jpeg;base64,AAAA"></html>')
    original = html
    texto = html_para_texto(html)

    assert html == original                    # entrada intacta
    assert "PROCEDENTE EM PARTE" in texto
    assert "color:red" not in texto
    assert "base64" not in texto
    assert "<p>" not in texto


def test_contagem_de_imagens_base64():
    html = '<img src="data:image/png;base64,AA"><img src="/logo.png">'
    assert contar_base64(html) == 1


def test_html_vazio_ou_nulo():
    assert html_para_texto(None) == ""
    assert html_para_texto("") == ""


# hash
def test_hash_estavel():
    assert sha256("abc") == sha256("abc")
    assert sha256("abc") != sha256("abd")