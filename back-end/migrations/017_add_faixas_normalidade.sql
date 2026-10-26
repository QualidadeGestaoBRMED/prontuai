-- Ajuste das faixas de referência da normalidade de exames.
--
-- Como na 016, `Base.metadata.create_all()` roda antes do auto_migrate() e cria
-- a tabela numa base nova; este arquivo existe para bases já de pé, e por isso
-- tudo aqui é IF NOT EXISTS.
--
-- Os parâmetros (glicose, HbA1c, hemoglobina...) e a faixa padrão de cada um
-- vivem no código (`app/services/normalidade_exames.py`). A tabela guarda só o
-- ajuste feito na tela: sem linha = vale o padrão; apagar a linha restaura o
-- padrão. O histórico de quem mudou o quê vem do audit_logs.

BEGIN;

CREATE TABLE IF NOT EXISTS faixas_normalidade (
    parametro VARCHAR PRIMARY KEY,
    minimo DOUBLE PRECISION,
    maximo DOUBLE PRECISION,
    atualizado_por_id VARCHAR REFERENCES users(id),
    atualizado_por_email VARCHAR,
    atualizado_por_nome VARCHAR,
    atualizado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_faixas_normalidade_limite CHECK (minimo IS NOT NULL OR maximo IS NOT NULL),
    CONSTRAINT ck_faixas_normalidade_ordem CHECK (minimo IS NULL OR maximo IS NULL OR minimo <= maximo)
);

COMMENT ON TABLE faixas_normalidade IS 'Ajuste da faixa de referência por parâmetro de exame (sem linha = faixa padrão do código)';

COMMIT;
