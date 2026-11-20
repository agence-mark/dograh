-- =====================================================================
--  Descente de la 046 (chantier Partie 1, lot 15). À jouer EN PREMIER (avant 045…). Idempotente.
--  Retire les colonnes ajoutées : les allergènes du produit gardent leur liste (la colonne d'origine, 025) ; ceux d'une option, son état et sa source disparaissent.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS allergies_renvoyees_au_restaurant;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS halal_restaurant;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS consigne_allergie;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS nutrition;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS epice;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS regimes;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes_source;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes_etat;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS allergenes_source;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS allergenes_etat;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes;

DELETE FROM schema_version WHERE version = 46;
