-- ⚠️ Destrutivo: limpa dados operacionais mantendo usuários e clínicas.
-- Use SOMENTE quando quiser “resetar” o ambiente.
-- Mantém: users, clinics
-- Remove: documents, notifications, audit_logs (e dependências via CASCADE)

BEGIN;

TRUNCATE TABLE notifications, audit_logs, documents RESTART IDENTITY CASCADE;

COMMIT;
