-- =====================================================================
--  050 : la fin du service « pour ce soir » devient un INSTANT (chantier Partie 1, lot 19 bis, K7 ; audit caisse de Pierre du 20/11).
--  EN AJOUT d'une colonne ; les deux colonnes de la 045 ne sont plus écrites (elles sont vidées, jamais une double vérité).
--
--  Avant : une heure (``fin_aujourd_hui``) et un jour (``fin_aujourd_hui_le``). Un restaurant ouvert jusqu'à 2 h : à 22 h, « arrêt à 00 h 30 » coupait tout de suite (``22:00 >= 00:30``) et
--  « arrêt à 23 h 30 » ne comptait plus à 0 h 01 (le jour avait changé). Maintenant ``fin_aujourd_hui_a`` (timestamptz) : l'instant où le type arrête de prendre des commandes ; il vaut
--  jusqu'à la fin de SON jour de service (06 h du lieu), puis s'efface seul.
--  Les valeurs déjà posées sont converties (heure + jour du lieu : une heure avant 06 h tombe la nuit qui suit ce jour), puis les anciennes colonnes sont vidées.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage_type ADD COLUMN IF NOT EXISTS fin_aujourd_hui_a timestamptz;

UPDATE resto_reglage_type t
   SET fin_aujourd_hui_a = ((t.fin_aujourd_hui_le + CASE WHEN t.fin_aujourd_hui < time '06:00' THEN 1 ELSE 0 END) + t.fin_aujourd_hui) AT TIME ZONE s.fuseau,
       fin_aujourd_hui = NULL, fin_aujourd_hui_le = NULL
  FROM site s
 WHERE s.id = t.site_id AND t.fin_aujourd_hui IS NOT NULL AND t.fin_aujourd_hui_le IS NOT NULL;

INSERT INTO schema_version (version, description) VALUES
    (50, 'Module Restauration : la fin du service pour ce soir est un instant (fin_aujourd_hui_a)')
ON CONFLICT (version) DO NOTHING;
