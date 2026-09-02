-- Catálogo de exames similares: exame pai (canônico) + variações.
--
-- Substitui, como fonte de verdade, o par
-- `back-end/exames_similares_final.csv` + `data/exam_similarity_data.json`.
-- Nesta fase só o painel de CRUD consome estas tabelas; o motor
-- (workflow_service / validacao_service) continua lendo os artefatos de disco
-- até a fase de lógica.
--
-- Três regras de modelagem estão gravadas no schema:
--   1. Pai é nome do BRNET. Pai herdado do CSV sem correspondência entra com
--      status 'quarentena' — não vale como canônico, mas o nome continua
--      servindo de vocabulário para o portão de extração do OCR.
--   2. Árvore estrita: name_normalized de variação é único no catálogo, logo
--      uma variação tem exatamente um pai. Colisão vai para
--      exam_variation_conflicts e espera decisão humana.
--   3. "(externo)" é flag no pai (is_external), não pai separado.
--
-- Idempotente: o Base.metadata.create_all() do startup cria estas tabelas
-- antes de auto_migrate() rodar, então tudo aqui usa IF NOT EXISTS / DO block.

BEGIN;

CREATE TABLE IF NOT EXISTS exam_parents (
    id                      VARCHAR PRIMARY KEY,
    name                    VARCHAR NOT NULL,
    name_normalized         VARCHAR NOT NULL UNIQUE,
    status                  VARCHAR NOT NULL DEFAULT 'quarentena',
    is_external             BOOLEAN NOT NULL DEFAULT FALSE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    source                  VARCHAR,
    notes                   TEXT,
    embedding               BYTEA,
    embedding_model         VARCHAR,
    embedding_generated_at  TIMESTAMP,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by              VARCHAR,
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by              VARCHAR
);

CREATE TABLE IF NOT EXISTS exam_variations (
    id                      VARCHAR PRIMARY KEY,
    parent_id               VARCHAR NOT NULL REFERENCES exam_parents(id) ON DELETE CASCADE,
    name                    VARCHAR NOT NULL,
    name_normalized         VARCHAR NOT NULL UNIQUE,
    is_active               BOOLEAN NOT NULL DEFAULT TRUE,
    source                  VARCHAR,
    occurrences             INTEGER,
    embedding               BYTEA,
    embedding_model         VARCHAR,
    embedding_generated_at  TIMESTAMP,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by              VARCHAR,
    updated_at              TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by              VARCHAR
);

CREATE TABLE IF NOT EXISTS exam_variation_conflicts (
    id                      VARCHAR PRIMARY KEY,
    name                    VARCHAR NOT NULL,
    name_normalized         VARCHAR NOT NULL,
    candidate_parents       VARCHAR[] NOT NULL,
    source                  VARCHAR,
    resolution              VARCHAR,
    resolved_parent_id      VARCHAR REFERENCES exam_parents(id) ON DELETE SET NULL,
    resolved_at             TIMESTAMP,
    resolved_by             VARCHAR,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Constraints em DO block: Postgres não tem ADD CONSTRAINT IF NOT EXISTS, e a
-- tabela pode já ter vindo do create_all com elas.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_exam_parents_status') THEN
        ALTER TABLE exam_parents
            ADD CONSTRAINT ck_exam_parents_status
            CHECK (status IN ('ativo', 'quarentena'));
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_exam_variation_conflicts_name') THEN
        ALTER TABLE exam_variation_conflicts
            ADD CONSTRAINT uq_exam_variation_conflicts_name UNIQUE (name_normalized);
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_exam_variation_conflicts_resolution') THEN
        ALTER TABLE exam_variation_conflicts
            ADD CONSTRAINT ck_exam_variation_conflicts_resolution
            CHECK (resolution IS NULL OR resolution IN ('atribuida', 'descartada'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_exam_parents_name_normalized ON exam_parents (name_normalized);
CREATE INDEX IF NOT EXISTS ix_exam_variations_parent_id ON exam_variations (parent_id);
CREATE INDEX IF NOT EXISTS ix_exam_variations_name_normalized ON exam_variations (name_normalized);
CREATE INDEX IF NOT EXISTS ix_exam_variation_conflicts_name_normalized ON exam_variation_conflicts (name_normalized);

COMMENT ON TABLE  exam_parents IS 'Exame pai (canônico) do catálogo de similaridade';
COMMENT ON COLUMN exam_parents.status IS 'ativo = nome confirmado no BRNET, vale como canônico; quarentena = herdado do CSV, serve só de vocabulário';
COMMENT ON COLUMN exam_parents.is_external IS 'Antigo sufixo "(externo)" promovido a flag';
COMMENT ON COLUMN exam_parents.embedding IS 'Reservado para a fase de lógica: vetor 3072 dims (text-embedding-3-large). NULL nesta fase';
COMMENT ON TABLE  exam_variations IS 'Variações/sinônimos de um exame pai. name_normalized único = árvore estrita';
COMMENT ON COLUMN exam_variations.occurrences IS 'Ocorrências observadas nos documentos, para ordenar curadoria. NULL = nunca medido, nunca zero';
COMMENT ON TABLE  exam_variation_conflicts IS 'Variação que apareceu sob mais de um pai na importação; espera decisão humana no painel';

COMMIT;
