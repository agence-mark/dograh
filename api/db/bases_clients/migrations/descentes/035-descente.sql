-- =====================================================================
--  Descente de la 035 (module Restauration, lot 26, M50). À jouer EN PREMIER (avant 034, 033…). Idempotente.
--  Retire l'état « module allumé » de la base et le déclencheur de création d'établissement. Les lignes de réglage (donc l'état par
--  établissement) ne sont pas touchées : le module garde l'état que ses lignes disent.
-- =====================================================================
SET search_path = mark;

DROP TRIGGER IF EXISTS site_module_restauration ON site;
DROP FUNCTION IF EXISTS resto_regler_le_nouvel_etablissement();
DROP TABLE IF EXISTS resto_module;

DELETE FROM schema_version WHERE version = 35;
