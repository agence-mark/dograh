-- =====================================================================
--  Descente de la 030 (module Restauration, lot 12). À jouer EN PREMIER (avant 029, 028, 027, 026, 025). Idempotente.
--  Retire le signal « module allumé », le cercle d'affichage des zones, les réglages de paiement et de numéro et la table des soirs chargés.
--  ⛔ SUPPRIME les soirs toujours chargés (``resto_temps_recurrent``) : sauvegarder la base avant.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS module_actif;
ALTER TABLE IF EXISTS resto_zone DROP COLUMN IF EXISTS cercle_km;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS numero_mode;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS prefixe_mixte;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS notes_libres;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS titre_alcool_exclu;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS titre_sans_rendu;
DROP TABLE IF EXISTS resto_temps_recurrent;

DELETE FROM schema_version WHERE version = 30;
