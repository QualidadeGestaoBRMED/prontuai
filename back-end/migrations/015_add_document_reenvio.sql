-- 015: reenvio de prontuario ja liberado.
--
-- Clinicas reenviam prontuarios que ja foram aprovados; o reenvio virava um
-- item novo na Checagem e a clinica entendia que o documento nao tinha sido
-- aprovado. Reconstruido sobre jun a 19/10/2026: 184 reenvios de documento ja
-- aprovado pelo revisor (mesmo arquivo, mesmo pedido do BRNET, ou mesmo CPF +
-- empresa em 30 dias).
-- O documento novo passa a ser gravado com validation_status = 'reenvio' e
-- `reenvio_de` apontando para o liberado (app/services/reenvio_service.py).
--
-- `pedido_exame_id` sai do JSON para uma coluna porque e a chave da deteccao e
-- ler o JSON de cada documento custa segundos por consulta. Preenchimento dos
-- existentes pela mesma regra do back (pedido_exame_id_do_payload): ha uma
-- chave por documento, numero ou texto ("123" em 9 deles).

ALTER TABLE documents ADD COLUMN IF NOT EXISTS pedido_exame_id BIGINT NULL;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS reenvio_de VARCHAR NULL;

UPDATE documents
SET pedido_exame_id = substring(result_payload from '"pedido_exame_id":\s*"?(\d{1,18})"?')::bigint
WHERE pedido_exame_id IS NULL
  AND result_payload LIKE '%"pedido_exame_id"%'
  AND substring(result_payload from '"pedido_exame_id":\s*"?(\d{1,18})"?') IS NOT NULL;

-- Sem CONCURRENTLY pelo mesmo motivo da 009: o runner roda o arquivo inteiro
-- numa transacao. `cpf` entra porque a regra de CPF + empresa filtra por ele.
CREATE INDEX IF NOT EXISTS ix_documents_pedido_exame_id ON documents (pedido_exame_id);
CREATE INDEX IF NOT EXISTS ix_documents_reenvio_de ON documents (reenvio_de);
CREATE INDEX IF NOT EXISTS ix_documents_cpf ON documents (cpf);

COMMENT ON COLUMN documents.pedido_exame_id IS 'Pedido de exame no BRNET; copia de result_payload.brmed_result.pedido_exame_id';
COMMENT ON COLUMN documents.reenvio_de IS 'Documento ja liberado de que este e reenvio (validation_status = reenvio)';
