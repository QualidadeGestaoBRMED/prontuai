-- 012: mais de um cargo por usuario.
--
-- `roles` passa a ser a lista de cargos (ex.: {CHECKER,SENDER}). A coluna
-- `role` continua, agora como o PAPEL PRINCIPAL -- o mais forte da lista, na
-- ordem ADMIN > MANAGER > CHECKER > CURATOR > SENDER (ver
-- app/models/user.py::PRECEDENCIA_PAPEIS). Ela segue existindo porque o
-- `audit_logs.user_role` e a consulta do dashboard que reconhece revisao humana
-- leem o papel unico; o back grava as duas juntas.
--
-- VARCHAR[] e nao o enum `userrole`: o enum nasceu pelo create_all e ja exigiu
-- ALTER TYPE a cada papel novo (ver _ensure_role_enum_values); a validacao dos
-- valores fica no Pydantic, como nas outras colunas de codigo.
--
-- Bases ja de pe: cada usuario comeca com o cargo que ja tinha.

ALTER TABLE users ADD COLUMN IF NOT EXISTS roles VARCHAR[] NULL;

UPDATE users
SET roles = ARRAY[role::text]
WHERE roles IS NULL OR cardinality(roles) = 0;

COMMENT ON COLUMN users.roles IS 'Cargos do usuario; role = o principal (mais forte) entre eles';
