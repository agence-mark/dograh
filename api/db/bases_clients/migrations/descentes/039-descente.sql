-- =====================================================================
--  Descente de la 039 (chantier Partie 1, lot 10). À jouer EN PREMIER (avant 038…). Idempotente.
--  Retire les trois colonnes : seuls ces réglages sont perdus, la carte reste entière.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS moities_prix;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS prix_retrait;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS prix_par_declinaison;

DELETE FROM schema_version WHERE version = 39;
