"""Persistencia: RAW imutavel, documentos por idSentenca e manifest SQLite.

Layout:

    data/
      raw/falcao/searches/<slug>/page_0000.json     pagina exata como recebida
      raw/falcao/documents/<idSentenca>.json        documento exato
      manifests/falcao.sqlite                       indice
      normalized/<slug>/<idSentenca>.txt            texto limpo (derivado)

Duas regras que o codigo faz valer, nao so promete:

  1. o arquivo RAW nunca e reescrito depois de gravado, exceto com --force;
  2. o manifest tem UNIQUE em id_sentenca e NAO em numero_cnj — um processo
     tem varios documentos, e deduplicar por CNJ na coleta perderia dado.
"""

import hashlib
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Consulta, Documento, Pagina

log = logging.getLogger(__name__)

VERSAO_PARSER = "falcao-0.1.0"

SCHEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    id_sentenca         TEXT PRIMARY KEY,
    numero_cnj          TEXT,
    page                INTEGER,
    query_text          TEXT,
    tribunal            TEXT,
    collection          TEXT,
    date_start          TEXT,
    date_end            TEXT,
    data_julgamento     TEXT,
    data_juntada        TEXT,
    orgao_julgador      TEXT,
    classe              TEXT,
    tipo_documento      TEXT,
    fase_processual     TEXT,
    score               REAL,
    http_status         INTEGER,
    collected_at        TEXT,
    raw_page_path       TEXT,
    raw_document_path   TEXT,
    sha256_raw_document TEXT,
    parser_version      TEXT
);
CREATE INDEX IF NOT EXISTS idx_doc_cnj    ON documentos(numero_cnj);
CREATE INDEX IF NOT EXISTS idx_doc_orgao  ON documentos(orgao_julgador);
CREATE INDEX IF NOT EXISTS idx_doc_page   ON documentos(page);

CREATE TABLE IF NOT EXISTS paginas (
    slug          TEXT NOT NULL,
    page          INTEGER NOT NULL,
    n_documentos  INTEGER,
    quantidade_total INTEGER,
    collected_at  TEXT,
    raw_page_path TEXT,
    sha256_page   TEXT,
    PRIMARY KEY (slug, page)
);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


class Armazenamento:
    def __init__(self, raiz: str = "data"):
        self.raiz = Path(raiz)
        self.dir_paginas = self.raiz / "raw" / "falcao" / "searches"
        self.dir_docs = self.raiz / "raw" / "falcao" / "documents"
        self.dir_norm = self.raiz / "normalized"
        self.manifest = self.raiz / "manifests" / "falcao.sqlite"
        for d in (self.dir_paginas, self.dir_docs, self.dir_norm, self.manifest.parent):
            d.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.manifest)
        self.con.executescript(SCHEMA)
        self.con.commit()

    def fechar(self) -> None:
        self.con.close()

    # caminhos
    def caminho_pagina(self, consulta: Consulta, page: int) -> Path:
        return self.dir_paginas / consulta.slug() / f"page_{page:04d}.json"

    def caminho_documento(self, id_sentenca: str) -> Path:
        return self.dir_docs / f"{id_sentenca}.json"

    def caminho_normalizado(self, consulta: Consulta, id_sentenca: str) -> Path:
        return self.dir_norm / consulta.slug() / f"{id_sentenca}.txt"

    # consultas
    def pagina_ja_baixada(self, consulta: Consulta, page: int) -> bool:
        caminho = self.caminho_pagina(consulta, page)
        if not caminho.exists():
            return False
        linha = self.con.execute(
            "SELECT sha256_page FROM paginas WHERE slug=? AND page=?",
            (consulta.slug(), page)).fetchone()
        if not linha:
            return False
        return linha[0] == sha256(caminho.read_text(encoding="utf-8"))

    def documento_ja_baixado(self, id_sentenca: str) -> bool:
        return self.con.execute(
            "SELECT 1 FROM documentos WHERE id_sentenca=?",
            (id_sentenca,)).fetchone() is not None

    # gravacao
    def gravar_pagina(self, consulta: Consulta, pagina: Pagina, http_status: int = 200, force: bool = False) -> Path:
        """Grava o JSON EXATO da pagina. Nao reordena, nao filtra, nao formata
        de outro jeito alem da indentacao."""
        caminho = self.caminho_pagina(consulta, pagina.numero)
        caminho.parent.mkdir(parents=True, exist_ok=True)

        if caminho.exists() and not force:
            log.info("pagina %s ja existe; mantida", pagina.numero)
        else:
            conteudo = json.dumps(pagina.bruto, ensure_ascii=False, indent=2)
            caminho.write_text(conteudo, encoding="utf-8")

        texto = caminho.read_text(encoding="utf-8")
        self.con.execute(
            "INSERT OR REPLACE INTO paginas VALUES (?,?,?,?,?,?,?)",
            (consulta.slug(), pagina.numero, len(pagina.documentos),
             pagina.quantidade_total, agora(), str(caminho), sha256(texto)))
        self.con.commit()
        return caminho

    def gravar_documento(self, consulta: Consulta, doc: Documento, page: int,
                         http_status: int = 200, force: bool = False) -> bool:
        """Grava o documento e indexa. Devolve True se gravou, False se pulou.

        Idempotente: documento ja no manifest com hash igual nao e reescrito.
        """
        caminho = self.caminho_documento(doc.id_sentenca)
        conteudo = json.dumps(doc.bruto, ensure_ascii=False, indent=2)
        digest = sha256(conteudo)

        existente = self.con.execute(
            "SELECT sha256_raw_document FROM documentos WHERE id_sentenca=?",
            (doc.id_sentenca,)).fetchone()

        if existente and existente[0] == digest and not force:
            return False
        if existente and existente[0] != digest and not force:
            log.warning("documento %s mudou no servidor; use --force para "
                        "sobrescrever. Mantido o original.", doc.id_sentenca)
            return False

        caminho.write_text(conteudo, encoding="utf-8")
        self.con.execute(
            "INSERT OR REPLACE INTO documentos VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc.id_sentenca, doc.numero_cnj, page, consulta.texto,
             consulta.tribunal, consulta.colecao, consulta.data_inicio,
             consulta.data_fim, doc.data_julgamento, doc.data_juntada,
             doc.orgao_por_extenso, doc.classe_processual, doc.tipo_documento,
             doc.fase_processual, doc.score, http_status, agora(),
             str(self.caminho_pagina(consulta, page)), str(caminho),
             digest, VERSAO_PARSER))
        self.con.commit()
        return True

    def gravar_normalizado(self, consulta: Consulta, id_sentenca: str,
                           texto: str) -> Path:
        caminho = self.caminho_normalizado(consulta, id_sentenca)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8")
        return caminho

    # ------------------------------------------------------------ leitura
    def contar(self, slug: Optional[str] = None) -> dict:
        if slug:
            docs = self.con.execute(
                "SELECT COUNT(*), COUNT(DISTINCT numero_cnj) FROM documentos "
                "WHERE query_text || '_' || lower(tribunal) LIKE ?",
                (f"%{slug.split('_')[0]}%",)).fetchone()
        else:
            docs = self.con.execute(
                "SELECT COUNT(*), COUNT(DISTINCT numero_cnj) FROM documentos"
            ).fetchone()
        paginas = self.con.execute("SELECT COUNT(*) FROM paginas").fetchone()[0]
        return {"documentos": docs[0], "cnjs_unicos": docs[1], "paginas": paginas}