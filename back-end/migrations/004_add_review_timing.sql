-- Migração para medir o tempo de revisão humana (dashboard de BI).
-- Desenho completo em docs/tempo-de-revisao-desenho.md.
--
-- Quatro colunas nullable e sem default: no PG 11+ isso é alteração só de
-- catálogo, sem rewrite da tabela, então roda no startup sem travar a fila
-- de revisão.
--
-- NULL significa "revisão sem instrumentação" (decidida antes deste deploy,
-- por cliente antigo, ou cronômetro que falhou) — nunca zero. Toda consulta
-- de BI precisa filtrar por review_active_ms IS NOT NULL.

BEGIN;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_opened_at TIMESTAMP;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_active_ms INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_wall_ms INTEGER;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS review_open_count SMALLINT;

COMMENT ON COLUMN documents.review_opened_at IS 'Primeira abertura da tela de revisão (UTC, relógio do cliente)';
COMMENT ON COLUMN documents.review_active_ms IS 'Soma dos trechos ativos de revisão, descontado o ocioso';
COMMENT ON COLUMN documents.review_wall_ms IS 'Soma dos trechos de parede de revisão, sem desconto';
COMMENT ON COLUMN documents.review_open_count IS 'Quantas vezes a tela de revisão foi aberta';

COMMIT;
