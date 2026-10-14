-- 010: motivos estruturados da rejeicao.
--
-- O campo de texto livre "Motivo da rejeicao" saiu do modal da checagem e,
-- desde entao, toda rejeicao era gravada sem motivo nenhum. O modal novo monta
-- o motivo por cliques: o texto continua em `rejection_reason` (e o que a
-- clinica le e o que vai para o PDF), e os codigos que o geraram ficam aqui,
-- para dar para contar - "quais exames as clinicas mais deixam de mandar".
--
-- Formato: [{"codigo": "EXAME_FALTANTE", "exame": "Espirometria"},
--           {"codigo": "ASO_INCOMPLETO"}]
-- Codigos validos: CODIGOS_REJEICAO em back-end/app/models/document.py.
-- NULL = rejeitado antes desta migration, ou documento nao rejeitado.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS rejection_codes JSONB NULL;

COMMENT ON COLUMN documents.rejection_codes IS 'Motivos da rejeicao: [{codigo, exame?}]; texto correspondente em rejection_reason';
