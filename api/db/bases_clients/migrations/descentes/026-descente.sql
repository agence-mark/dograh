-- =====================================================================
--  Descente de la 026 (module Restauration, lot 1). À jouer APRÈS celles de la 028 et de la 027.
--  ⛔ SUPPRIME les commandes, ruptures, zones, réglages par type et la liaison : sauvegarder la base avant.
--  Idempotente.
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_compteur_jour, resto_liaison, resto_message_recu, resto_commande_ligne, resto_commande,
                     resto_zone, resto_reglage_type, resto_etat_caisse, resto_rupture;

DELETE FROM schema_version WHERE version = 26;
