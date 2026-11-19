-- =====================================================================
--  Descente de la 041 (chantier Partie 1, lot 12). À jouer EN PREMIER (avant 040…). Idempotente.
--  Retire les colonnes des conditions de vente : seuls ces réglages sont perdus, la carte reste entière.
--  ``resto_formule.modes`` n'est PAS retiré : il appartient à la 040.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS prix_par_mode;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS modes;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS disponibilite;
ALTER TABLE IF EXISTS resto_categorie DROP COLUMN IF EXISTS disponibilite;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS personnes_min;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS delai_minimal_heures;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS max_par_commande;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS frais;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS degre;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS alcool;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS modes;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS disponibilite;

DELETE FROM schema_version WHERE version = 41;
