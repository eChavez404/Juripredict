-- Esquema do dataset JuriPredict.
-- Roda em SQLite (desenvolvimento) e PostgreSQL com ajuste de tipos.
--
-- Regra estrutural: 'casos' tem UMA linha por (numero_cnj, pedido).
-- Toda granularidade fina vive em tabelas-filhas e nunca vira linha de treino.

-- ---------------------------------------------------------------- documentos
CREATE TABLE IF NOT EXISTS documentos (
    doc_id            TEXT PRIMARY KEY,
    numero_cnj        TEXT NOT NULL,
    orgao_julgador    TEXT,
    regiao            TEXT,
    data_sentenca     DATE,
    -- Metadado do tribunal, nao inferido do texto. `classe` distingue a acao
    -- (ATOrd, ATSum) do cumprimento de sentenca (CumSen, CumPrSe), e e a unica
    -- fonte confiavel para isso: `tipo_documento` vem "Sentenca" em 776 dos 787
    -- documentos, inclusive nos de liquidacao e embargos.
    classe            TEXT,
    tipo_documento    TEXT,
    -- 1 quando a acao foi proposta por sindicato, federacao, associacao ou MPT,
    -- ou quando a classe e coletiva (ACC, ACPCiv, ACum). Guarda-se o indicador,
    -- nunca o nome da parte (invariante I6).
    autor_coletivo    INTEGER DEFAULT 0,
    tipo_decisao      TEXT NOT NULL,   -- ver livro de codigos, 3.1
    julga_insalubridade TEXT,          -- sim | nao | nao_informado
    ordem_sentenca    TEXT,            -- primeira | posterior (exige DataJud)
    arquivo_bruto     TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    estrategia_corte  TEXT,            -- titulo | frase_de_fecho | nao_encontrado
    coletado_em       TIMESTAMP,
    fonte             TEXT             -- falcao | datajud | outra
);

-- --------------------------------------------------------------------- casos
-- Uma linha por processo x pedido. E esta tabela que vira o dataset.
CREATE TABLE IF NOT EXISTS casos (
    caso_id           TEXT PRIMARY KEY,
    numero_cnj        TEXT NOT NULL,
    pedido            TEXT NOT NULL,   -- insalubridade | periculosidade | horas_extras
    doc_id            TEXT NOT NULL REFERENCES documentos(doc_id),

    resultado_pedido  TEXT NOT NULL,   -- deferido | indeferido | prescrito_total
                                       -- | prejudicado | nao_analisado | ambiguo
    grau_deferido     INTEGER,         -- 10 | 20 | 40 | NULL
    resultado_global  TEXT,            -- procedente | parcial | improcedente
                                       -- | acordo | extinto_sem_merito

    entra_no_modelo   INTEGER NOT NULL DEFAULT 0,  -- 1 se resultado in (deferido, indeferido)
    motivo_exclusao   TEXT,

    UNIQUE (numero_cnj, pedido)
);

-- ---------------------------------------------------------- periodos julgados
-- Preservacao de resolucao. NUNCA vira linha do dataset de treino.
CREATE TABLE IF NOT EXISTS periodos_julgados (
    id                INTEGER PRIMARY KEY,
    caso_id           TEXT NOT NULL REFERENCES casos(caso_id),
    periodo_inicio    DATE,
    periodo_fim       DATE,
    reconhecido       TEXT NOT NULL,   -- sim | nao
    grau              INTEGER,
    motivo_recorte    TEXT
);

-- ------------------------------------------------------------------- valores
-- Um registro por campo anotado, com evidencia e proveniencia (livro, secao 8).
-- Formato longo de proposito: permite guardar metodo e versao por campo, e
-- comparar humano x regra x llm sobre o mesmo campo sem duplicar colunas.
CREATE TABLE IF NOT EXISTS valores (
    id                INTEGER PRIMARY KEY,
    caso_id           TEXT NOT NULL REFERENCES casos(caso_id),
    campo             TEXT NOT NULL,
    valor             TEXT,
    evidencia         TEXT,
    metodo            TEXT NOT NULL,   -- regra | llm | humano
    versao            TEXT NOT NULL,
    extraido_em       TIMESTAMP,
    UNIQUE (caso_id, campo, metodo, versao)
);

-- ------------------------------------------------------------------ gold set
CREATE TABLE IF NOT EXISTS gold_set (
    caso_id           TEXT NOT NULL REFERENCES casos(caso_id),
    campo             TEXT NOT NULL,
    valor             TEXT,
    evidencia         TEXT,
    anotador          TEXT NOT NULL,
    anotado_em        TIMESTAMP,
    PRIMARY KEY (caso_id, campo, anotador)
);

-- --------------------------------------------------------- eventos posteriores
-- Anulacao, reforma, transito. Registrados, nunca substituem o target.
CREATE TABLE IF NOT EXISTS eventos_posteriores (
    id                INTEGER PRIMARY KEY,
    numero_cnj        TEXT NOT NULL,
    evento            TEXT NOT NULL,   -- anulacao | recurso | provimento_global | transito
    data_evento       DATE,
    fonte             TEXT
);

-- ------------------------------------------------------------------ auditoria
CREATE TABLE IF NOT EXISTS cobertura (
    vara              TEXT NOT NULL,
    ano               INTEGER NOT NULL,
    n_datajud         INTEGER NOT NULL,
    n_falcao          INTEGER NOT NULL,
    medido_em         TIMESTAMP,
    PRIMARY KEY (vara, ano)
);

CREATE INDEX IF NOT EXISTS idx_casos_cnj    ON casos(numero_cnj);
CREATE INDEX IF NOT EXISTS idx_valores_caso ON valores(caso_id, campo);
CREATE INDEX IF NOT EXISTS idx_doc_data     ON documentos(data_sentenca);