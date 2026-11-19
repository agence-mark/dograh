-- =====================================================================
--  Descente de la 043 (chantier Partie 1, lot 13). À jouer EN PREMIER (avant 042…). Idempotente.
--  Retire seulement les colonnes ajoutées : les lignes entières existantes n'y perdent rien (``quantite`` est inchangée).
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS lot_de_vente;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS arrondi;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS prix_par_unite;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS unite;
ALTER TABLE IF EXISTS resto_commande_ligne DROP COLUMN IF EXISTS poids_g;

DELETE FROM schema_version WHERE version = 43;
