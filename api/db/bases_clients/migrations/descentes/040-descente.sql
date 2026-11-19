-- =====================================================================
--  Descente de la 040 (chantier Partie 1, lot 11). À jouer EN PREMIER (avant 039…). Idempotente.
--  Retire les colonnes des formules complètes et l'inclus de rubrique : seuls ces réglages sont perdus, la carte reste entière.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_categorie DROP COLUMN IF EXISTS inclus;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS par_lot;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS tailles;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS personnes;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS public;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS age_max;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS modes;

DELETE FROM schema_version WHERE version = 40;
