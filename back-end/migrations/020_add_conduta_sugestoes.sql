-- Trilha da conduta sugerida (tela Conduta Médica): o que o ml-exams respondeu, quem viu e o que o médico decidiu.
--
-- `Base.metadata.create_all()` roda antes do auto_migrate() e cria as tabelas
-- numa base nova; este arquivo existe para bases já de pé, e por isso tudo
-- aqui é IF NOT EXISTS.
--
-- As três tabelas só recebem linhas novas, nunca são atualizadas: para qualquer
-- documento dá para responder o que o modelo sugeriu, com qual versão, quem viu
-- e o que o médico decidiu. Sem nome, CPF nem texto do documento: as features
-- são as mesmas que já saem para o ml-exams.

BEGIN;

-- Cada chamada ao POST /prever do ml-exams, com a resposta inteira ou a falha.
-- Abrir o documento de novo reaproveita a última resposta com as mesmas
-- features (features_hash) em vez de chamar o serviço outra vez.
CREATE TABLE IF NOT EXISTS conduta_sugestoes (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    features_hash VARCHAR(64) NOT NULL,
    versao_features VARCHAR NOT NULL,
    versao_modelo VARCHAR,
    features JSONB NOT NULL,
    resposta JSONB,
    status_http INTEGER,
    erro VARCHAR,
    duracao_ms INTEGER,
    request_id VARCHAR(64),
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conduta_sugestoes_documento ON conduta_sugestoes (document_id, criado_em);

-- Cada vez que a tela mostrou a sugestão (ou a falta dela) a alguém.
CREATE TABLE IF NOT EXISTS conduta_exibicoes (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    sugestao_id BIGINT REFERENCES conduta_sugestoes(id) ON DELETE SET NULL,
    situacao_aso VARCHAR,
    motivo_sem_sugestao VARCHAR,
    confianca DOUBLE PRECISION,
    versao_modelo VARCHAR,
    user_id VARCHAR,
    user_email VARCHAR,
    exibido_em TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conduta_exibicoes_documento ON conduta_exibicoes (document_id, exibido_em);

-- Cada decisão registrada pelo médico. A última vale; as anteriores ficam.
CREATE TABLE IF NOT EXISTS conduta_decisoes (
    id BIGSERIAL PRIMARY KEY,
    document_id VARCHAR NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    exibicao_id BIGINT REFERENCES conduta_exibicoes(id) ON DELETE SET NULL,
    sugestao_exibida BOOLEAN NOT NULL,
    situacao_sugerida VARCHAR,
    concordou_com_sugestao BOOLEAN,
    situacao_final VARCHAR NOT NULL,
    observacao TEXT,
    normalidade_final JSONB NOT NULL DEFAULT '[]'::jsonb,
    versao_modelo VARCHAR,
    decidido_em TIMESTAMP NOT NULL,
    user_id VARCHAR,
    user_email VARCHAR,
    registrado_em TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conduta_decisoes_documento ON conduta_decisoes (document_id, registrado_em);

COMMENT ON TABLE conduta_sugestoes IS 'Cada chamada ao POST /prever do ml-exams por documento, com a resposta inteira ou a falha; app/services/conduta/conduta_sugerida.py';
COMMENT ON TABLE conduta_exibicoes IS 'Cada exibição da conduta sugerida na tela Conduta Médica: o que foi mostrado, a quem e quando';
COMMENT ON TABLE conduta_decisoes IS 'Decisões do médico na tela Conduta Médica, com a sugestão que ele viu; a última de cada documento vale';

COMMIT;
