-- =====================================================================
--  052 : le cutoff_time du point de vente HubRise est gardé (Pierre 13, K6 ; lot de contrôle du 23/11).
--  EN AJOUT d'une colonne nullable : l'heure où la journée de service de la caisse change (HubRise : « 06:00 » par défaut). Jusqu'ici le code la supposait à 06:00 en dur : une caisse qui
--  la règle autrement (03:00, 08:00) voyait ses horaires qui passent minuit refusés ou mal coupés, et le jour de service des fins (« arrêt à 01:00 ») mal placé.
--  Vide : la caisse ne le dit pas, le code garde 06:00. Rien n'est réécrit.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_etat_caisse ADD COLUMN IF NOT EXISTS cutoff_time time;

INSERT INTO schema_version (version, description) VALUES
    (52, 'Module Restauration : le cutoff_time du point de vente (journée de service de la caisse)')
ON CONFLICT (version) DO NOTHING;
