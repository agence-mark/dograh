-- =====================================================================
--  Descente de la 052 (K6). À jouer EN PREMIER (avant 051...). Idempotente : sans la table, rien à faire.
--  Retire la colonne ; le code revient au 06:00 par défaut.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_etat_caisse DROP COLUMN IF EXISTS cutoff_time;

DELETE FROM schema_version WHERE version = 52;
