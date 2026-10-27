-- Posição de cada linha do OCR na página do PDF.
--
-- `Base.metadata.create_all()` roda antes do auto_migrate() e cria a tabela
-- numa base nova; este arquivo existe para bases já de pé, e por isso tudo
-- aqui é IF NOT EXISTS.
--
-- O Textract devolve a caixa de cada linha e palavra; o markdown guarda só o
-- texto. Com a caixa, a checagem leva o revisor direto ao exame no PDF, com o
-- trecho destacado. Fica numa tabela à parte para a listagem de documentos não
-- carregar centenas de caixas por linha. Sem linha = documento lido antes disto
-- ou pelo OCR local: a checagem segue sem o atalho.

BEGIN;

CREATE TABLE IF NOT EXISTS documento_layout (
    document_id VARCHAR PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
    layout JSONB NOT NULL,
    criado_em TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE documento_layout IS 'Posição de cada linha do OCR (Textract) na página do PDF; formato em app/services/layout_ocr.py';

COMMIT;
