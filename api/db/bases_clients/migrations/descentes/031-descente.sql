-- =====================================================================
--  Descente de la 031 (module Restauration, lot 20). À jouer EN PREMIER (avant 030, 029…). Idempotente.
--  Retire la contrainte qui ferme la liste des douze mécanismes de remise. AUCUNE donnée n'est touchée.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_remise DROP CONSTRAINT IF EXISTS resto_remise_mecanisme_ferme;

DELETE FROM schema_version WHERE version = 31;
