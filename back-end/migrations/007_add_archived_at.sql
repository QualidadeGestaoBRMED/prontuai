-- 007: marca quando o PDF do documento saiu do disco para o arquivo morto.
--
-- Sem esta coluna, o endpoint de visualizacao nao consegue distinguir
-- "arquivado conforme a politica de retencao" de "arquivo desapareceu por
-- bug/remocao manual" — os dois caem no mesmo 404, e a mensagem ao usuario
-- seria um chute. Com ela, arquivado responde 410 Gone com orientacao de
-- recuperacao, e sumico de verdade continua 404, que e o que precisa
-- aparecer como defeito.
--
-- Quem escreve: ops/deploy/archive_documents_to_drive.sh, depois de verificar
-- por checksum a copia no Drive e antes de remover o original.
-- NULL = o arquivo nunca foi arquivado (o caso da maioria absoluta das linhas).

ALTER TABLE documents ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP NULL;

-- Indice parcial: as consultas so procuram linhas JA arquivadas, que sao a
-- minoria. Indexar apenas NOT NULL mantem o indice pequeno e nao penaliza o
-- INSERT do fluxo normal, em que a coluna e sempre NULL.
CREATE INDEX IF NOT EXISTS idx_documents_archived_at
  ON documents (archived_at)
  WHERE archived_at IS NOT NULL;
