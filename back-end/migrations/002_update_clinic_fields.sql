-- Migração para atualizar campos da tabela clinics
-- Remove email e adiciona campos opcionais (cnpj, phone, address, city, state)

BEGIN;

-- Adicionar novas colunas opcionais
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS cnpj VARCHAR(18);
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS phone VARCHAR(20);
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS city VARCHAR(100);
ALTER TABLE clinics ADD COLUMN IF NOT EXISTS state VARCHAR(2);

-- Remover coluna email (não é mais necessária)
-- NOTA: Esta operação só funciona se não houver índices/constraints dependentes
ALTER TABLE clinics DROP COLUMN IF EXISTS email CASCADE;

COMMIT;
