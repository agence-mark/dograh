-- =====================================================================
--  Descente de la 053 (chantier Partie 1, lot 9). À jouer AVANT la descente de la 052. Idempotente.
--  Remet les deux colonnes vides (comme la 050 les avait laissées) : la descente de la 050 y reverse ensuite ``fin_aujourd_hui_a``.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage_type ADD COLUMN IF NOT EXISTS fin_aujourd_hui time;
ALTER TABLE resto_reglage_type ADD COLUMN IF NOT EXISTS fin_aujourd_hui_le date;
ALTER TABLE resto_reglage_type DROP CONSTRAINT IF EXISTS resto_reglage_type_fin_aujourd_hui_check;
ALTER TABLE resto_reglage_type ADD CONSTRAINT resto_reglage_type_fin_aujourd_hui_check
    CHECK ((fin_aujourd_hui IS NULL) = (fin_aujourd_hui_le IS NULL));

DELETE FROM schema_version WHERE version = 53;
