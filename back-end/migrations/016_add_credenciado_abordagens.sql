-- Status de abordagem das credenciadas sem cadastro ("Quem vale a pena incluir").
--
-- A numeração pula para 016 de propósito: 013 a 015 já existem na staging.
--
-- Como na 008, `Base.metadata.create_all()` roda antes do auto_migrate() e cria
-- a tabela numa base nova; este arquivo existe para bases já de pé, e por isso
-- tudo aqui é IF NOT EXISTS.
--
-- Uma linha por credenciada, pelo rótulo do BRNET ("CIDADE - UF - NOME"): a API
-- de monitoramento não manda id nem CNPJ. Sem linha = "Não abordada". O
-- histórico das mudanças vem do audit_logs gravado pelo middleware.

BEGIN;

CREATE TABLE IF NOT EXISTS credenciado_abordagens (
    credenciado VARCHAR PRIMARY KEY,
    status VARCHAR NOT NULL,
    motivo TEXT,
    atualizado_por_id VARCHAR REFERENCES users(id),
    atualizado_por_email VARCHAR,
    atualizado_por_nome VARCHAR,
    atualizado_em TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_credenciado_abordagens_status
        CHECK (status IN ('NAO_ABORDADA', 'EM_CONTATO', 'AGUARDANDO_RETORNO', 'ACEITOU', 'RECUSOU'))
);

CREATE INDEX IF NOT EXISTS ix_credenciado_abordagens_status ON credenciado_abordagens (status);

COMMENT ON TABLE credenciado_abordagens IS 'Status de abordagem das credenciadas sem cadastro no ProntuAI (um por credenciada)';

COMMIT;
