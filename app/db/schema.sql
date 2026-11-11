CREATE TABLE IF NOT EXISTS localidade (
    id               SERIAL PRIMARY KEY,
    series_id        TEXT UNIQUE NOT NULL,
    corredor         TEXT NOT NULL,
    sentido          TEXT NOT NULL,
    regiao           TEXT,
    tipo_via         TEXT,
    extensao_max_km  NUMERIC(8, 3)
);

CREATE TABLE IF NOT EXISTS serie_horaria (
    localidade_id  INTEGER NOT NULL REFERENCES localidade (id) ON DELETE CASCADE,
    instante       TIMESTAMP NOT NULL,
    km_lentidao    REAL NOT NULL CHECK (km_lentidao >= 0),
    PRIMARY KEY (localidade_id, instante)
);
CREATE INDEX IF NOT EXISTS ix_serie_horaria_instante ON serie_horaria (instante);

CREATE TABLE IF NOT EXISTS feriado (
    data  DATE PRIMARY KEY,
    nome  TEXT
);

CREATE TABLE IF NOT EXISTS parametro_sistema (
    chave          TEXT PRIMARY KEY,
    valor          JSONB NOT NULL,
    descricao      TEXT,
    atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS carga (
    id            SERIAL PRIMARY KEY,
    arquivo       TEXT NOT NULL,
    sha256        TEXT NOT NULL,
    linhas        INTEGER NOT NULL,
    carregado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);
