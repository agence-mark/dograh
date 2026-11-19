-- =====================================================================
--  Descente de la 038 (chantier Partie 1, lot 9). À jouer EN PREMIER (avant 037…). Idempotente.
--  Retire les trois colonnes d'un groupe de choix : seuls ces réglages sont perdus, la carte reste entière.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_groupe_choix DROP COLUMN IF EXISTS si_option;
ALTER TABLE IF EXISTS resto_groupe_choix DROP COLUMN IF EXISTS prix_au_dela;
ALTER TABLE IF EXISTS resto_groupe_choix DROP COLUMN IF EXISTS inclus;

DELETE FROM schema_version WHERE version = 38;
