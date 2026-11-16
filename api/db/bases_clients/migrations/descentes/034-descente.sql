-- =====================================================================
--  Descente de la 034 (module Restauration, lot 26, M38). À jouer EN PREMIER (avant 033, 032…). Idempotente.
--  ⛔ SUPPRIME le compte des offres dites et acceptées (les remises et les commandes ne sont pas touchées) : sauvegarder la base avant.
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_remise_offre;

DELETE FROM schema_version WHERE version = 34;
