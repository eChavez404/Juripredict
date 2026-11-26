"""Remoção de dados pessoais com formato conhecido antes de qualquer envio a terceiros.

Documentos com número próprio (CPF, CNPJ, PIS, e-mail, telefone, CEP) são reconhecidos pelo
formato; os demais (RG, CTPS, OAB, CNH, título, conta, nascimento), pelo rótulo que os precede,
porque o número sozinho se confunde com outros. Nomes e endereços só são reconhecidos onde um
contrato ou uma petição os deixa marcados: depois de um rótulo ("Reclamante:", "Testemunhas:"),
de um título ("Dr.", "Sra.") ou antes da qualificação ("..., brasileira, solteira", "..., CPF").
Um nome solto no meio do texto passa: por isso o formulário pede que não sejam informados.
"""

import re

# "nº", "n.", "número", ":" entre o rótulo e o número
_N = r"(?i:[\s:]*(?:n[º°o.]\.?\s*|n[úu]mero\s*)?[\s:]*)"
_UF = r"(?:\s*[-/]?\s*[A-Z]{2}\b)?"

_PALAVRA = r"[A-ZÀ-Ý][A-Za-zÀ-ÿ'-]+"
_NOME = rf"{_PALAVRA}(?:\s+(?:(?:d[aeo]s?|D[AEO]S?|e|E)\s+)?{_PALAVRA}){{1,6}}"
_ROTULOS = (
    r"(?i:reclamante|reclamad[ao]|autor[a]?|r[ée]u|r[ée]|empregad[oa]|empregador[a]?|contratante"
    r"|contratad[oa]|testemunhas?|advogad[oa]s?|preposto|perit[oa]|nome)"
)
_NOME_ROTULADO = re.compile(rf"(\b{_ROTULOS}\s*:\s*){_NOME}")
_NOME_COM_TITULO = re.compile(
    rf"(\b(?:Dr|Dra|Sr|Sra|Srta)\.?\s+){_PALAVRA}(?:\s+(?:(?:d[aeo]s?|e)\s+)?{_PALAVRA}){{0,6}}"
)
_NOME_QUALIFICADO = re.compile(
    rf"\b{_NOME}(?=\s*,\s*(?i:brasileir|estrangeir|portador|nascid|inscrit|residente|domiciliad"
    r"|solteir|casad|divorciad|vi[úu]v|CPF|RG|OAB|CTPS))"
)
# Do logradouro até o CEP, o fim da frase ou da linha; sem logradouro ("o endereço da
# reclamada"), não é endereço. Abreviações comuns não encerram a frase.
_ENDERECO = re.compile(
    r"(\b(?i:residente(?: e domiciliad[oa])?|domiciliad[oa]|com sede|sediad[oa]|endere[çc]o)"
    r"(?:\s+(?:na|no|em|à|a|o)|\s*:)?\s+)"
    r"(?=(?i:rua|r\.|av\b|av\.|avenida|travessa|tv\.|rodovia|estrada|quadra|qd\b|alameda|pra[çc]a"
    r"|conjunto|residencial|povoado|s[íi]tio|fazenda|loteamento|vila|bairro|BR-|MA-))"
    r"[^;\n]+?(?=,?\s*(?i:CEP)\b|[;\n]|(?<!\bAv)(?<!\bR)(?<!\bQd)(?<!\bLt)(?<!\bAp)\.(?:\s|$)|$)"
)

_ROTULADOS = (
    (rf"(?i:\bCNH\b|carteira nacional de habilita[çc][ãa]o){_N}\d{{9,11}}\b", "[CNH]"),
    (
        rf"(?i:\bt[íi]tulo(?: de)? eleitor(?:al)?){_N}\d{{4}}\s?\d{{4}}\s?\d{{4}}\b",
        "[TÍTULO DE ELEITOR]",
    ),
    (
        rf"(?i:\bCTPS\b|carteira de trabalho(?: e previd[êe]ncia social)?){_N}\d(?:[\d./-]*\d)?"
        rf"(?:\s*,?\s*(?i:s[ée]rie){_N}\d(?:[\d./-]*\d)?{_UF})?",
        "[CTPS]",
    ),
    (
        r"(?i:\bRG\b|\bR\.G\.|carteira de identidade|c[ée]dula de identidade)"
        rf"{_N}\d(?:[\d.-]*[\dxX])?"
        rf"(?:\s*[-/]?\s*(?:SSP|SESP|SDS|SSPDS|PC|IFP|DETRAN)\s*[-/]?\s*[A-Z]{{2}}\b)?",
        "[RG]",
    ),
    (rf"(?i:\bOAB\b)\s*[/-]?\s*(?:[A-Z]{{2}}\b)?{_N}\d(?:[\d.]*\d)?[A-Z]?{_UF}", "[OAB]"),
    (
        r"(?i:\bnascid[oa] (?:em|aos?)|data de nascimento|\bnasc\.)"
        rf"{_N}\d{{1,2}}/\d{{1,2}}/\d{{2,4}}",
        "[NASCIMENTO]",
    ),
    (rf"(?i:\bCEP\b){_N}\d{{2}}\.?\d{{3}}-?\d{{3}}\b|\b\d{{5}}-\d{{3}}\b", "[CEP]"),
    (rf"(?i:\bag[êe]ncia\b){_N}\d{{3,5}}(?:-[\dxX])?\b", "[AGÊNCIA]"),
    (
        # sem "c/c": em sentença é "combinado com" (art. 818 da CLT c/c art. 373 do CPC)
        r"(?i:\b(?:conta\s+(?:corrente|poupan[çc]a|sal[áa]rio|banc[áa]ria)|conta(?=\s*(?:n[º°o]|:))))"
        rf"{_N}\d(?:[\d.]*\d)?(?:-[\dxX])?\b",
        "[CONTA]",
    ),
)

# O número CNJ do processo não casa com nenhum deles e é preservado.
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_PIS = re.compile(r"\b\d{3}\.\d{5}\.\d{2}-\d\b")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
# Exige o DDD: sem ele, um intervalo de anos (2019-2024) pareceria telefone.
_PHONE = re.compile(r"(?:\(\d{2}\)\s?|\b\d{2}\s)9?\d{4}-?\d{4}\b")

_ORDEM = (
    # nomes antes dos documentos: a qualificação ("..., CPF") ainda precisa estar no texto
    (_NOME_ROTULADO, r"\1[NOME]"),
    (_NOME_COM_TITULO, r"\1[NOME]"),
    (_NOME_QUALIFICADO, "[NOME]"),
    (_ENDERECO, r"\1[ENDEREÇO]"),
    # rótulos antes dos números soltos: a CNH tem 11 dígitos, como o CPF
    *((re.compile(padrao), marcador) for padrao, marcador in _ROTULADOS),
    (_EMAIL, "[EMAIL]"),
    (_CNPJ, "[CNPJ]"),
    (_PIS, "[PIS]"),
    (_CPF, "[CPF]"),
    (_PHONE, "[TELEFONE]"),
)


def mask_documents(text: str) -> str:
    """Troca dados pessoais por marcadores. Nome solto, sem rótulo nem qualificação, passa."""
    for pattern, marker in _ORDEM:
        text = pattern.sub(marker, text)
    return text
