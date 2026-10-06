-- Parecer humano sobre o resultado da IA, coletado no fim da checagem.
-- Molde da tabela `reviews` da Triagem BR NET, sem a tabela de eventos: a
-- trilha de alterações já vem do `audit_logs` gravado pelo middleware.
--
-- IMPORTANTE: `Base.metadata.create_all()` roda no __init__ do
-- PostgresUserDatabase, ANTES do auto_migrate() do startup. Numa base que sobe
-- do zero a tabela nasce pelo create_all e esta migration nunca aparece como
-- "necessária" no log — igual à 005. O arquivo existe para bases já de pé, e
-- por isso tudo aqui é IF NOT EXISTS.
--
-- Uma linha por documento (unique em document_id): reavaliar atualiza, não
-- empilha. Documento sem linha = não avaliado — o parecer é opcional e não
-- trava nada.

BEGIN;

CREATE TABLE IF NOT EXISTS document_feedbacks (
    id VARCHAR PRIMARY KEY,
    document_id VARCHAR NOT NULL UNIQUE REFERENCES documents(id) ON DELETE CASCADE,
    reviewed_by_id VARCHAR REFERENCES users(id),
    reviewed_by_email VARCHAR,
    status VARCHAR NOT NULL,
    issue_categories VARCHAR[] NOT NULL DEFAULT '{}',
    issue_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    document_issues VARCHAR[] NOT NULL DEFAULT '{}',
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_document_feedbacks_status
        CHECK (status IN ('IA_CORRETA', 'IA_CORRETA_COM_AJUSTES', 'IA_INCORRETA'))
);

CREATE INDEX IF NOT EXISTS ix_document_feedbacks_document_id ON document_feedbacks (document_id);
CREATE INDEX IF NOT EXISTS ix_document_feedbacks_status ON document_feedbacks (status);
CREATE INDEX IF NOT EXISTS ix_document_feedbacks_reviewed_by_email ON document_feedbacks (reviewed_by_email);
-- GIN nos dois: o painel filtra por categoria e agrega por exame dentro do JSONB.
CREATE INDEX IF NOT EXISTS ix_document_feedbacks_categories ON document_feedbacks USING GIN (issue_categories);
CREATE INDEX IF NOT EXISTS ix_document_feedbacks_items ON document_feedbacks USING GIN (issue_items);

COMMENT ON TABLE document_feedbacks IS 'Parecer humano sobre o acerto da IA em um documento (opcional, um por documento)';
COMMENT ON COLUMN document_feedbacks.status IS 'IA_CORRETA | IA_CORRETA_COM_AJUSTES | IA_INCORRETA';
COMMENT ON COLUMN document_feedbacks.issue_categories IS 'Categorias distintas de issue_items, derivadas no servidor; vazio quando status = IA_CORRETA';
COMMENT ON COLUMN document_feedbacks.document_issues IS 'Problemas do documento inteiro (OCR_NOME, OCR_CPF, OCR_DATA, DOC_ILEGIVEL) - sem exame associado';
COMMENT ON COLUMN document_feedbacks.issue_items IS 'Pares [{categoria, exame, veredito_ia, fora_da_lista}]; fora_da_lista = exame digitado, fora da tabela de comparacao';
COMMENT ON COLUMN document_feedbacks.notes IS 'Texto livre do revisor - pode conter PII, nunca vai para log ou telemetria';

COMMIT;
