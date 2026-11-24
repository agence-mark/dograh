-- =====================================================================
--  053 (chantier Partie 1, lot 9, constat 137) : retire les colonnes mortes ``fin_aujourd_hui`` et ``fin_aujourd_hui_le``.
--  La 050 les a remplacées par ``fin_aujourd_hui_a`` (un instant) et les a mises à NULL ; plus aucun code ne les lit ni ne les écrit. Idempotente.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage_type DROP CONSTRAINT IF EXISTS resto_reglage_type_fin_aujourd_hui_check;
ALTER TABLE resto_reglage_type DROP COLUMN IF EXISTS fin_aujourd_hui_le;
ALTER TABLE resto_reglage_type DROP COLUMN IF EXISTS fin_aujourd_hui;

INSERT INTO schema_version (version, description) VALUES
    (53, 'Module Restauration : retire les colonnes mortes fin_aujourd_hui et fin_aujourd_hui_le (remplacées par fin_aujourd_hui_a)')
ON CONFLICT (version) DO NOTHING;
