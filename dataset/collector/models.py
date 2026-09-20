"""Modelos da resposta do FALCAO.

Campos conforme observado empiricamente no DevTools. Nada aqui e inventado:
o que nao foi visto na resposta real nao esta modelado.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Consulta:
    """Parametros da pesquisa. Vira nome de pasta e chave do manifest."""

    texto: str
    tribunal: str
    colecao: str
    data_inicio: str
    data_fim: str

    def slug(self) -> str:
        """
        Identificador da consulta. Vira nome de pasta e chave de retomada.

        Usa as datas INTEIRAS. A primeira versao usava so o ano, e isso fez
        todas as janelas mensais do mesmo ano colidirem: a segunda janela
        encontrava as paginas da primeira, concluia "ja baixei" e pulava tudo.
        Meses inteiros foram perdidos em silencio.
        """
        t = self.texto.lower().replace(" ", "-")
        return (f"{t}_{self.tribunal.lower()}_"
                f"{self.data_inicio}_{self.data_fim}")

    def params(self, session_id: str, page: int, size: int) -> dict:
        """Query params exatamente na forma observada no navegador."""
        return {
            "sessionId": session_id,
            "latitude": 0,
            "longitude": 0,
            "texto": self.texto,
            "verTodosPrecedentes": "false",
            "tribunais": self.tribunal,
            "pesquisaSomenteNasEmentas": "false",
            "filtroRapidoData": "IntervaloSelecionado",
            "dataInicio": self.data_inicio,
            "dataFim": self.data_fim,
            "colecao": self.colecao,
            "page": page,
            "size": size,
        }


@dataclass
class Documento:
    """Um item de `documentos`. `bruto` preserva o objeto original intacto."""

    id_sentenca: str
    numero_cnj: Optional[str]
    tribunal: Optional[str]
    tipo_documento: Optional[str]
    classe_processual: Optional[str]
    classe_por_extenso: Optional[str]
    orgao_julgador: Optional[str]
    orgao_por_extenso: Optional[str]
    fase_processual: Optional[str]
    data_julgamento: Optional[str]
    data_juntada: Optional[str]
    score: Optional[float]
    texto_sentenca: Optional[str]
    bruto: dict = field(repr=False, default_factory=dict)

    @classmethod
    def de_json(cls, d: dict) -> "Documento":
        def s(chave: str) -> Optional[str]:
            v = d.get(chave)
            return None if v is None else str(v)

        return cls(
            id_sentenca=str(d.get("idSentenca")),
            numero_cnj=s("numeroProcesso"),
            tribunal=s("tribunal"),
            tipo_documento=s("tipoDocumento"),
            classe_processual=s("classeProcessual"),
            classe_por_extenso=s("classeProcessualPorExtenso"),
            orgao_julgador=s("orgaoJulgador"),
            orgao_por_extenso=s("orgaoJulgadorPorExtenso"),
            fase_processual=s("faseProcessual"),
            data_julgamento=s("dataJulgamento"),
            data_juntada=s("dataJuntada"),
            score=d.get("score"),
            texto_sentenca=d.get("textoSentenca"),
            bruto=d,
        )


@dataclass
class Pagina:
    """Resposta de uma pagina. `bruto` e o JSON exato, para gravar sem alterar."""

    numero: int
    documentos: list
    quantidade_total: int
    bruto: dict = field(repr=False, default_factory=dict)

    @classmethod
    def de_json(cls, numero: int, d: dict) -> "Pagina":
        return cls(
            numero=numero,
            documentos=[Documento.de_json(x) for x in (d.get("documentos") or [])],
            quantidade_total=int(d.get("quantidadeTotal") or 0),
            bruto=d,
        )

    def vazia(self) -> bool:
        return not self.documentos


class ErroFalcao(RuntimeError):
    """Resposta de erro do backend, com a mensagem que ele devolveu."""

    def __init__(self, mensagem_usuario: str, corpo: Any = None):
        super().__init__(mensagem_usuario)
        self.mensagem_usuario = mensagem_usuario
        self.corpo = corpo


class ErroSessao(ErroFalcao):
    """Sessao ausente, invalida ou expirada."""