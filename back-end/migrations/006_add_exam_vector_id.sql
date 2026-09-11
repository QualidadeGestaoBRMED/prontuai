-- Identificador inteiro para o índice vetorial do catálogo.
--
-- O FAISS `IndexIDMap2` só aceita id int64, e as PKs do catálogo são UUID.
-- Em vez de guardar a correspondência num arquivo paralelo indexado por
-- POSIÇÃO — a fragilidade do índice antigo, onde `exam_similarity_data[idx]`
-- desalinha em silêncio a cada remoção — o id vive na própria linha.
--
-- O valor é derivado da UUID (63 bits baixos), então é determinístico: dá para
-- recalcular a qualquer momento sem sequence nem coordenação. O UNIQUE existe
-- para que uma colisão (probabilidade ~1e-13 nesta escala) falhe alto em vez
-- de corromper o índice.

BEGIN;

ALTER TABLE exam_parents    ADD COLUMN IF NOT EXISTS vector_id BIGINT;
ALTER TABLE exam_variations ADD COLUMN IF NOT EXISTS vector_id BIGINT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_parents_vector_id    ON exam_parents (vector_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_exam_variations_vector_id ON exam_variations (vector_id);

COMMENT ON COLUMN exam_parents.vector_id    IS 'Id int64 no índice FAISS, derivado da UUID (63 bits baixos)';
COMMENT ON COLUMN exam_variations.vector_id IS 'Id int64 no índice FAISS, derivado da UUID (63 bits baixos)';

COMMIT;
