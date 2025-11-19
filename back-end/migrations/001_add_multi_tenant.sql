-- Migração para sistema multi-tenant
-- Adiciona suporte para clínicas e rastreamento de documentos

BEGIN;

-- 1. Criar tabela de clínicas
CREATE TABLE IF NOT EXISTS clinics (
    id VARCHAR PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    name VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')
);

CREATE INDEX IF NOT EXISTS idx_clinics_email ON clinics(email);

-- 2. Adicionar coluna clinic_id na tabela users
ALTER TABLE users ADD COLUMN IF NOT EXISTS clinic_id VARCHAR;
ALTER TABLE users ADD CONSTRAINT fk_users_clinic_id FOREIGN KEY (clinic_id) REFERENCES clinics(id);

-- 3. Criar tabela de documentos
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR PRIMARY KEY,
    clinic_id VARCHAR NOT NULL,
    uploaded_by_user_id VARCHAR NOT NULL,
    filename VARCHAR NOT NULL,
    cpf VARCHAR,
    uploaded_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    exams_found VARCHAR[],
    validation_status VARCHAR NOT NULL DEFAULT 'pending',
    ocr_markdown TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    updated_at TIMESTAMP NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC'),
    CONSTRAINT fk_documents_clinic_id FOREIGN KEY (clinic_id) REFERENCES clinics(id),
    CONSTRAINT fk_documents_user_id FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_documents_clinic_id ON documents(clinic_id);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents(uploaded_by_user_id);
CREATE INDEX IF NOT EXISTS idx_documents_cpf ON documents(cpf);

COMMIT;
