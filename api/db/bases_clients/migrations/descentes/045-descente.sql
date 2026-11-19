-- =====================================================================
--  Descente de la 045 (chantier Partie 1, lot des manques). À jouer EN PREMIER (avant 044…). Idempotente.
--  Retire les minutes ajoutées par zone et la fin du service pour aujourd'hui : seuls ces réglages du jour sont perdus.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage_type DROP CONSTRAINT IF EXISTS resto_reglage_type_fin_aujourd_hui_check;
ALTER TABLE IF EXISTS resto_reglage_type DROP COLUMN IF EXISTS fin_aujourd_hui_le;
ALTER TABLE IF EXISTS resto_reglage_type DROP COLUMN IF EXISTS fin_aujourd_hui;
ALTER TABLE IF EXISTS resto_zone DROP COLUMN IF EXISTS ajout_jusqu_a;
ALTER TABLE IF EXISTS resto_zone DROP COLUMN IF EXISTS minutes_ajoutees;

DELETE FROM schema_version WHERE version = 45;
