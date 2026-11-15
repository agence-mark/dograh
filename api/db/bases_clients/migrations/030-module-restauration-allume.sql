-- =====================================================================
--  030 : le signal « module Restauration allumé » et le cercle d'une zone (chantier module-restauration, lot 12).
--  Additive : deux colonnes. ``module_actif`` : vrai par défaut (une base qui a déjà des lignes de réglage reste allumée).
--  Allumer = une ligne de ``resto_reglage`` par établissement avec ``module_actif`` vrai ; retirer = ``module_actif`` faux
--  partout. AUCUNE donnée n'est supprimée (carte, salles, commandes, zones restent, le remettre les retrouve).
--  Le portail et le fork lisent le même signal : ``EXISTS (SELECT 1 FROM resto_reglage WHERE module_actif)``.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS module_actif boolean NOT NULL DEFAULT true;

-- Le cercle d'une zone sur le schéma de l'écran : son rayon en km, quelle que soit sa forme. Une zone « par communes » n'a pas de ``rayon_km`` (la
-- contrainte ``resto_zone_forme`` le veut vide) : ``cercle_km`` ne sert qu'à l'affichage et au rangement des communes par la distance, jamais à
-- décider si une adresse est livrée.
ALTER TABLE resto_zone ADD COLUMN IF NOT EXISTS cercle_km numeric(6, 2) CHECK (cercle_km IS NULL OR cercle_km > 0);

INSERT INTO schema_version (version, description) VALUES
    (30, 'Module Restauration : signal « module allumé » (resto_reglage.module_actif, le retirer ne supprime aucune donnée) et cercle d''une zone (resto_zone.cercle_km)')
ON CONFLICT (version) DO NOTHING;
