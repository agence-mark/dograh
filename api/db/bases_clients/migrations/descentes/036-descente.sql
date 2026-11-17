-- =====================================================================
--  Descente de la 036 (SA-48, numéro de carte). À jouer EN PREMIER (avant 035, 034…). Idempotente.
--  Retire la colonne ``numero`` des produits et des formules : seuls les numéros sont perdus, la carte reste entière.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS numero;
ALTER TABLE IF EXISTS resto_formule DROP COLUMN IF EXISTS numero;

DELETE FROM schema_version WHERE version = 36;
