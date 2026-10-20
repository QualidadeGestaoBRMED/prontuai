-- 013: previsao de liberacao do pedido como coluna, para o filtro da Checagem.
--
-- A data ja vinha do BRNET e ficava so dentro de `result_payload`
-- (brmed_result.data_previsao_liberacao, "dd/mm/aaaa"). Filtrar a lista por
-- ela lendo o JSON custou 5,3s por consulta no dev (12 mil documentos), e a
-- tela refaz a consulta a cada 7s. Daqui em diante o back grava a coluna junto
-- com o payload (app/models/document.py::previsao_liberacao_do_payload).
--
-- Preenchimento dos documentos ja existentes, pela mesma regra do back:
--   * "dd/mm/aaaa", e tambem "aaaa-mm-dd" (dois documentos de 2025);
--   * data invalida ou ausente fica NULL. O to_date do Postgres levanta erro em
--     31/02 em vez de devolver NULL, e um erro aqui derrubaria o startup -- dai a
--     funcao temporaria que engole o erro. pg_temp some ao fim da conexao.
-- Le o texto com regex, sem `::jsonb`: payload que nao for JSON valido nao
-- pode abortar a migration. Ha uma chave por documento (conferido nos 10.284
-- do dev que a tem).

ALTER TABLE documents ADD COLUMN IF NOT EXISTS data_previsao_liberacao DATE NULL;

CREATE OR REPLACE FUNCTION pg_temp.data_ou_nulo(texto text, formato text) RETURNS date AS $$
BEGIN
  RETURN to_date(texto, formato);
EXCEPTION WHEN others THEN
  RETURN NULL;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

UPDATE documents d
SET data_previsao_liberacao = COALESCE(
      pg_temp.data_ou_nulo(substring(v.bruto from '^(\d{2}/\d{2}/\d{4})$'), 'DD/MM/YYYY'),
      pg_temp.data_ou_nulo(substring(v.bruto from '^(\d{4}-\d{2}-\d{2})$'), 'YYYY-MM-DD')
    )
FROM (
  SELECT id, trim(substring(result_payload from '"data_previsao_liberacao":\s*"([^"]*)"')) AS bruto
  FROM documents
  WHERE data_previsao_liberacao IS NULL
    AND result_payload LIKE '%"data_previsao_liberacao"%'
) v
WHERE d.id = v.id AND v.bruto IS NOT NULL;

-- Filtro por intervalo de previsao. Sem CONCURRENTLY pelo mesmo motivo da 009:
-- o runner roda o arquivo inteiro numa transacao.
CREATE INDEX IF NOT EXISTS idx_documents_previsao_liberacao
  ON documents (data_previsao_liberacao);

COMMENT ON COLUMN documents.data_previsao_liberacao IS 'Previsao de liberacao do pedido no BRNET; copia de result_payload.brmed_result.data_previsao_liberacao';
