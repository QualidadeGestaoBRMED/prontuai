-- 009: indices para as listagens paginadas de documentos (Checagem, Pendentes,
-- Historico).
--
-- Toda pagina dessas telas roda, sobre `documents`:
--   1. o COUNT do total filtrado;
--   2. o agregado do resumo (aprovados/rejeitados/pendentes);
--   3. o ORDER BY uploaded_at DESC LIMIT n OFFSET m.
--
-- Nenhum indice cobria `uploaded_at` nem `validation_status`, entao o Postgres
-- fazia Seq Scan + top-N sort da tabela INTEIRA tres vezes por pagina. Medido no
-- dev com 11.188 linhas: Seq Scan lendo 1.792 paginas de buffer, 11ms por
-- consulta — e o custo cresce linearmente com a tabela, que so aumenta.
--
-- `idx_documents_clinic_id` ja existia (migration 001) e resolve o escopo do
-- SENDER, mas nao a ordenacao; dai o indice composto abaixo.

-- Ordenacao padrao de TODAS as listagens. DESC explicito para o indice ser
-- percorrido para frente no caso comum (pagina 1 = mais recentes).
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at
  ON documents (uploaded_at DESC);

-- Fila (Checagem/Pendentes) + filtro de status: o status restringe e o
-- uploaded_at ja sai ordenado, dispensando o sort.
CREATE INDEX IF NOT EXISTS idx_documents_status_uploaded_at
  ON documents (validation_status, uploaded_at DESC);

-- Filtro por clinica (SENDER sempre, ADMIN/CHECKER quando escolhe uma no
-- combo) combinado com a ordenacao.
CREATE INDEX IF NOT EXISTS idx_documents_clinic_uploaded_at
  ON documents (clinic_id, uploaded_at DESC);

-- NOTA DE OPERACAO: sem CONCURRENTLY de proposito. O runner caseiro
-- (app/core/migrations.py) executa o arquivo inteiro dentro de uma transacao, e
-- CREATE INDEX CONCURRENTLY nao roda em transacao. A criacao trava ESCRITA em
-- `documents` enquanto constroi — segundos, na ordem de grandeza atual da
-- tabela, durante o startup do back-end. Se a tabela crescer a ponto de isso
-- pesar, crie os tres indices a mao com CONCURRENTLY antes do deploy: os
-- `IF NOT EXISTS` fazem esta migration virar no-op.
