-- =====================================================================
--  Descente de la 030 (module Restauration, lot 12). À jouer EN PREMIER (avant 029, 028, 027, 026, 025). Idempotente.
--  Retire le signal « module allumé » et le cercle d'affichage des zones (``cercle_km``) : aucune autre donnée n'est touchée.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS module_actif;
ALTER TABLE IF EXISTS resto_zone DROP COLUMN IF EXISTS cercle_km;

DELETE FROM schema_version WHERE version = 30;
