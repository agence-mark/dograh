-- =====================================================================
--  Descente de la 029 (module Restauration, lots 9 et 10). À jouer EN PREMIER (avant 028, 027, 026, 025).
--  ⛔ SUPPRIME les tickets, l'imprimante et la référence du jeton de la caisse : sauvegarder la base avant. Idempotente.
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_ticket, resto_imprimante, resto_liaison_acces;
ALTER TABLE IF EXISTS resto_liaison DROP COLUMN IF EXISTS mode_passif;
ALTER TABLE IF EXISTS resto_liaison DROP COLUMN IF EXISTS derniere_releve;
ALTER TABLE IF EXISTS resto_liaison DROP COLUMN IF EXISTS avertissements;

DELETE FROM schema_version WHERE version = 29;
