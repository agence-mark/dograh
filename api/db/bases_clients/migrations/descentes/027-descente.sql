-- =====================================================================
--  Descente de la 027 (module Restauration, lot 1). À jouer APRÈS celle de la 028, AVANT celle de la 026.
--  ⛔ SUPPRIME les clients, remises, envois et réglages du module : sauvegarder la base avant. Idempotente.
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_reglage, resto_envoi, resto_remise, resto_client;

DELETE FROM schema_version WHERE version = 27;
