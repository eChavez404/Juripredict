"""
Corta uma sentenca trabalhista em secoes (relatorio / fundamentacao / dispositivo)
e, dentro da fundamentacao, em capitulos por pedido.

Rodar sozinho executa os testes embutidos:
    python cortar_secoes.py
"""

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Ancoras. Padroes toleram acento ausente e numeracao romana/arabe no titulo.
# ---------------------------------------------------------------------------

_NUM = r"(?:[IVXivx]+|\d+)(?:\.\d+)*\s*[-\u2013\u2014.)]\s*"

ANCORA_RELATORIO = re.compile(
    rf"^\s*(?:{_NUM})?RELAT[\u00d3O]RIO\b", re.IGNORECASE | re.MULTILINE
)
ANCORA_FUNDAMENTACAO = re.compile(
    rf"^\s*(?:{_NUM})?(?:FUNDAMENTA[\u00c7C][\u00c3A]O|FUNDAMENTOS|M[\u00c9E]RITO)\b",
    re.IGNORECASE | re.MULTILINE,
)
ANCORA_DISPOSITIVO = re.compile(
    rf"^\s*(?:{_NUM})?(?:DISPOSITIVO|CONCLUS[\u00c3A]O)\b", re.IGNORECASE | re.MULTILINE
)
# Fecho classico usado quando nao ha titulo de secao.
FRASE_DISPOSITIVO = re.compile(
    r"(?:ANTE\s+O\s+EXPOSTO|ISTO\s+POSTO|ISSO\s+POSTO|POSTO\s+ISSO"
    r"|DIANTE\s+DO\s+EXPOSTO|PELO\s+EXPOSTO|EM\s+FACE\s+DO\s+EXPOSTO)",
    re.IGNORECASE,
)

# Titulo de capitulo dentro da fundamentacao.
#
# A primeira versao exigia inicio com DO/DA/DOS/DAS e falhou em 48 de 50
# sentencas reais: os titulos aparecem como
#
#     ADICIONAL DE INSALUBRIDADE - PROPORCIONALIDADE AOS DIAS TRABALHADOS
#
# Agora o criterio e estrutural: linha curta, isolada, predominantemente em
# caixa alta. O prefixo DO/DA continua aceito, mas nao e mais obrigatorio.
ANCORA_CAPITULO = re.compile(
    rf"^\s*(?:{_NUM})?([^\n]{{4,120}})$", re.MULTILINE
)

TEMAS = {
    "insalubridade": re.compile(r"INSALUBR", re.IGNORECASE),
    "periculosidade": re.compile(r"PERICULOS", re.IGNORECASE),
    "horas_extras": re.compile(r"HORAS?\s+EXTRA|SOBREJORNADA|HORA\s+EXTRA", re.IGNORECASE),
}


@dataclass
class Capitulo:
    titulo: str
    tema: Optional[str]
    texto: str


@dataclass
class Sentenca:
    relatorio: str = ""
    fundamentacao: str = ""
    dispositivo: str = ""
    capitulos: list = field(default_factory=list)
    estrategia: str = ""          # como o dispositivo foi localizado
    completa: bool = False        # achou fundamentacao E dispositivo

    def capitulo_de(self, tema: str) -> Optional[Capitulo]:
        for c in self.capitulos:
            if c.tema == tema:
                return c
        return None


def normalizar(texto: str) -> str:
    t = texto.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _linha_e_titulo(linha: str) -> bool:
    """
    Titulo de capitulo: curto, isolado, predominantemente em caixa alta.

    O limite de comprimento e o que separa titulo de ementa citada no corpo —
    ementas tambem vem em caixa alta, mas sao paragrafos longos.
    """
    linha = linha.strip()
    letras = [c for c in linha if c.isalpha()]
    if len(letras) < 4 or len(linha) > 120:
        return False
    maiusculas = sum(1 for c in letras if c.isupper())
    if maiusculas / len(letras) <= 0.7:
        return False
    # frase corrida terminada em ponto final costuma ser texto, nao titulo
    if linha.endswith(".") and linha.count(" ") > 12:
        return False
    return True


def _classificar_tema(titulo: str) -> Optional[str]:
    for tema, padrao in TEMAS.items():
        if padrao.search(titulo):
            return tema
    return None


def _achar_dispositivo(texto: str):
    """Retorna (posicao_inicio, estrategia). -1 se nao achou."""
    candidatos = [(m.start(), "titulo") for m in ANCORA_DISPOSITIVO.finditer(texto)]
    if candidatos:
        return max(candidatos)[0], "titulo"

    frases = [m.start() for m in FRASE_DISPOSITIVO.finditer(texto)]
    if frases:
        # a ultima ocorrencia e quase sempre o fecho da sentenca
        return max(frases), "frase_de_fecho"

    return -1, "nao_encontrado"


def cortar(texto_bruto: str) -> Sentenca:
    texto = normalizar(texto_bruto)
    s = Sentenca()

    pos_disp, s.estrategia = _achar_dispositivo(texto)

    m_fund = ANCORA_FUNDAMENTACAO.search(texto)
    m_rel = ANCORA_RELATORIO.search(texto)

    pos_fund = m_fund.start() if m_fund else -1
    pos_rel = m_rel.start() if m_rel else -1

    # dispositivo
    if pos_disp >= 0:
        s.dispositivo = texto[pos_disp:].strip()
    fim_corpo = pos_disp if pos_disp >= 0 else len(texto)

    # fundamentacao
    if 0 <= pos_fund < fim_corpo:
        s.fundamentacao = texto[pos_fund:fim_corpo].strip()
    elif pos_rel >= 0:
        s.fundamentacao = ""
    else:
        # sem titulos: trata o corpo inteiro como fundamentacao
        s.fundamentacao = texto[:fim_corpo].strip()

    # relatorio
    if pos_rel >= 0:
        fim_rel = pos_fund if pos_fund > pos_rel else fim_corpo
        s.relatorio = texto[pos_rel:fim_rel].strip()

    s.capitulos = _cortar_capitulos(s.fundamentacao)
    s.completa = bool(s.dispositivo) and bool(s.fundamentacao)
    return s


def _cortar_capitulos(fundamentacao: str) -> list:
    if not fundamentacao:
        return []

    marcas = []
    for m in ANCORA_CAPITULO.finditer(fundamentacao):
        linha = m.group(0).strip()
        if _linha_e_titulo(linha):
            marcas.append((m.start(), m.end(), m.group(1).strip()))

    capitulos = []
    for i, (ini, fim_titulo, titulo) in enumerate(marcas):
        fim = marcas[i + 1][0] if i + 1 < len(marcas) else len(fundamentacao)
        capitulos.append(
            Capitulo(
                titulo=titulo,
                tema=_classificar_tema(titulo),
                texto=fundamentacao[fim_titulo:fim].strip(),
            )
        )
    return capitulos


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

EXEMPLO_PADRAO = """PODER JUDICIARIO
JUSTICA DO TRABALHO
TRIBUNAL REGIONAL DO TRABALHO DA 16a REGIAO
2a VARA DO TRABALHO DE BALSAS
ATOrd 0000123-45.2022.5.16.0002
RECLAMANTE: FULANO DE TAL
RECLAMADA: AGRO EXEMPLO LTDA

SENTENCA

I - RELATORIO
FULANO DE TAL ajuizou reclamacao trabalhista em face de AGRO EXEMPLO LTDA,
postulando adicional de insalubridade e horas extras. Regularmente notificada,
a reclamada apresentou defesa.

II - FUNDAMENTACAO

II.1 - DA PRESCRICAO
Pronuncio a prescricao quinquenal das parcelas anteriores a 10/03/2018.

II.2 - DO ADICIONAL DE INSALUBRIDADE
O laudo pericial de fls. 340/365 concluiu pela existencia de insalubridade em
grau medio, por exposicao a agentes biologicos. A reclamada impugnou o laudo
alegando fornecimento de EPI, mas nao comprovou a entrega regular nem a
fiscalizacao do uso. Acolho a conclusao pericial.

II.3 - DAS HORAS EXTRAS
A reclamada nao juntou os controles de ponto do periodo. Aplico a presuncao
relativa de veracidade da jornada declarada na inicial.

III - DISPOSITIVO
Ante o exposto, julgo PROCEDENTES EM PARTE os pedidos para condenar a reclamada
ao pagamento do adicional de insalubridade em grau medio (20%) e das horas
extras excedentes da 8a diaria. Custas pela reclamada.
"""

EXEMPLO_SEM_TITULOS = """SENTENCA

Vistos etc. Trata-se de reclamacao em que se postula adicional de periculosidade.

DA PERICULOSIDADE
O perito concluiu pela inexistencia de exposicao a area de risco. Nao ha prova
em sentido contrario.

Ante o exposto, julgo IMPROCEDENTES os pedidos. Indefiro o adicional de
periculosidade. Custas pelo reclamante, dispensadas.
"""


def _testes():
    print("=== EXEMPLO 1: sentenca com titulos numerados ===")
    s = cortar(EXEMPLO_PADRAO)
    assert s.completa, "deveria achar fundamentacao e dispositivo"
    assert s.estrategia == "titulo", s.estrategia
    assert s.relatorio.startswith("I - RELATORIO")
    assert "PROCEDENTES EM PARTE" in s.dispositivo
    temas = [c.tema for c in s.capitulos]
    print("  estrategia:", s.estrategia)
    print("  capitulos :", [(c.titulo, c.tema) for c in s.capitulos])
    assert "insalubridade" in temas and "horas_extras" in temas, temas

    cap = s.capitulo_de("insalubridade")
    assert "laudo pericial" in cap.texto
    print("  tamanho do texto completo :", len(EXEMPLO_PADRAO), "chars")
    print("  tamanho do cap. insalubr. :", len(cap.texto), "chars")
    print("  reducao                   : {:.0f}%".format(
        100 * (1 - len(cap.texto) / len(EXEMPLO_PADRAO))))

    print("\n=== EXEMPLO 2: sentenca sem titulos de secao ===")
    s2 = cortar(EXEMPLO_SEM_TITULOS)
    print("  estrategia:", s2.estrategia)
    print("  capitulos :", [(c.titulo, c.tema) for c in s2.capitulos])
    assert s2.estrategia == "frase_de_fecho", s2.estrategia
    assert "IMPROCEDENTES" in s2.dispositivo
    assert s2.capitulo_de("periculosidade") is not None

    print("\nOK: todos os testes passaram.")


if __name__ == "__main__":
    _testes()