-- =====================================================================
--  Descente de la 030 (module Restauration, lot 12). À jouer EN PREMIER (avant 029, 028, 027, 026, 025). Idempotente.
--  Retire le signal « module allumé », le cercle d'affichage des zones, les réglages de paiement et de numéro et la table des soirs chargés.
--  ⛔ SUPPRIME les soirs toujours chargés (`resto_temps_recurrent`), les sources par objet et les ingrédients et allergènes écrits en surcouche : sauvegarder la base avant.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS module_actif;
ALTER TABLE IF EXISTS resto_zone DROP COLUMN IF EXISTS cercle_km;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS numero_mode;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS prefixe_mixte;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS notes_libres;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS titre_alcool_exclu;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS titre_sans_rendu;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS pause_caisse_pause_telephone;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS sources;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS ingredients;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS allergenes_ecrits;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS allergenes;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS alcool;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS produit_source;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS produit_maj_le;
DROP TABLE IF EXISTS resto_temps_recurrent;

DELETE FROM schema_version WHERE version = 30;
