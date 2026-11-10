-- Regras de identificação de exame no Catálogo de Exames (STC-1052).
--
-- O catálogo guardava só o nome do exame (exam_parents/exam_variations). Estas
-- duas tabelas guardam como o LAUDO de cada exame é reconhecido — título,
-- marca de resultado, conteúdo que prova o exame —, que antes eram listas fixas
-- em seis módulos do back-end. Ver app/services/regras_identificacao.py.
--
-- Ficam separadas das variações de propósito: variação muda o que conta como
-- exame encontrado na comparação; regra só diz como reconhecer o laudo.
--
-- A carga inicial NÃO está aqui: ela vem de 019_regras_identificacao_exames.json,
-- gravada por regras_identificacao.semear_se_vazio() logo depois desta
-- migração, e reproduz exatamente as listas que estavam no código.
--
-- Idempotente (IF NOT EXISTS / DO block), como a 005.

BEGIN;

CREATE TABLE IF NOT EXISTS exam_report_profiles (
    id           VARCHAR PRIMARY KEY,
    key          VARCHAR NOT NULL UNIQUE,
    name         VARCHAR NOT NULL,
    description  TEXT,
    is_active    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by   VARCHAR,
    updated_at   TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by   VARCHAR
);

CREATE TABLE IF NOT EXISTS exam_report_rules (
    id            VARCHAR PRIMARY KEY,
    key           VARCHAR NOT NULL UNIQUE,
    profile_id    VARCHAR NOT NULL REFERENCES exam_report_profiles(id) ON DELETE RESTRICT,
    role          VARCHAR NOT NULL,
    position      INTEGER NOT NULL,
    -- regex procurada no nome normalizado do exame
    name_pattern  TEXT NOT NULL,
    -- árvore de condição (regex/todos/algum/nao/contar/distintos); nula nos
    -- papéis que só classificam pelo nome
    condition     JSONB,
    params        JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- frase mostrada ao revisor quando a regra muda o veredito
    reason        TEXT,
    -- exemplos que a regra tem de acertar: {nome_sim, nome_nao, texto_sim, texto_nao}
    examples      JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes         TEXT,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    created_by    VARCHAR,
    updated_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_by    VARCHAR
);

CREATE INDEX IF NOT EXISTS ix_exam_report_rules_role ON exam_report_rules (role, position);
CREATE INDEX IF NOT EXISTS ix_exam_report_rules_profile ON exam_report_rules (profile_id);

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_exam_report_rules_role') THEN
        ALTER TABLE exam_report_rules
            ADD CONSTRAINT ck_exam_report_rules_role
            CHECK (role IN (
                'titulo_laudo', 'titulo_identidade', 'marcador_ocr', 'marcador_texto',
                'marca_laudo', 'sorologia_analito', 'prova_conteudo', 'regua_monitoramento',
                'laboratorio', 'termos_extras'
            ));
    END IF;
END$$;

COMMIT;
