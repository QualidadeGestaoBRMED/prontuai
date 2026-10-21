-- 014: vinculo da clinica com o credenciado do BRNET.
--
-- O identificador vem de GET /api/rede/credenciada ("C25414") e e guardado como
-- texto, com o "C", do jeito que o BRNET o expoe. Ate aqui a unica ponte entre
-- clinica e credenciado era o nome, e o dashboard casava os dois pelo rotulo
-- "CIDADE - UF - NOME" (app/services/dashboard_service.py::_cadastro_do_credenciado).
--
-- Indice COMUM, nao unico, de proposito (decisao de out/2026): 18 grupos de
-- clinicas cadastradas mais de uma vez para o mesmo credenciado (ex.: cinco
-- "TRES RIOS - RJ - ASO") ainda precisam ser unificados. Quando forem, este
-- indice vira UNIQUE (brnet_id) -- NULL continua livre para as contas internas,
-- que nao tem credenciado.
--
-- NULL = clinica sem vinculo: cadastrada antes desta migration (o vinculo das
-- existentes sai de scripts/vincular_clinicas_brnet.py) ou cadastrada sem
-- vinculo por um ADMIN.

ALTER TABLE clinics ADD COLUMN IF NOT EXISTS brnet_id VARCHAR(16) NULL;

-- E-mail de contato da clinica. O formulario de cadastro sempre pediu e-mail,
-- mas a tabela nao tinha a coluna e o back-end descartava o valor. Agora vem
-- do campo, ou, se ele ficar vazio, do credenciado na rede do BRNET.
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS email VARCHAR NULL;

CREATE INDEX IF NOT EXISTS ix_clinics_brnet_id ON clinics (brnet_id);

COMMENT ON COLUMN clinics.email IS 'E-mail de contato: o digitado no cadastro ou, vazio, o do credenciado no BRNET';
COMMENT ON COLUMN clinics.brnet_id IS 'Identificador do credenciado no BRNET (GET /api/rede/credenciada), ex.: C25414';
