-- =====================================================================
--  Descente de la 044 (chantier Partie 1, lot 14). À jouer EN PREMIER (avant 043…). Idempotente.
--  Retire l'index et la colonne ajoutés : les remises existantes n'y perdent rien (une remise à code redevient une remise sans code, annoncée).
-- =====================================================================
SET search_path = mark;

DROP INDEX IF EXISTS resto_remise_code_idx;
ALTER TABLE IF EXISTS resto_remise DROP COLUMN IF EXISTS code;

DELETE FROM schema_version WHERE version = 44;
