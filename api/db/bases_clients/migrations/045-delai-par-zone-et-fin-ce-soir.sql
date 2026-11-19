-- =====================================================================
--  045 : le délai annoncé par zone et la fin du service pour aujourd'hui (chantier Partie 1, lot des manques ; E5, E6 ; décision d'Evan du 19/11 soir).
--  EN AJOUT SEULEMENT : des colonnes facultatives, rien d'existant n'est modifié ; à leur défaut, le comportement d'avant.
--
--  ``resto_zone.minutes_ajoutees`` et ``resto_zone.ajout_jusqu_a`` (E5) : en plein rush, les minutes ajoutées au délai de CETTE zone de livraison,
--  jusqu'à une heure ou jusqu'à nouvel ordre (NULL), comme la durée ajoutée d'un type (``resto_reglage_type``). Le délai dit d'une livraison vaut le
--  délai de la zone, ses minutes ajoutées, les minutes du type et des soirs chargés, et la caisse débordée.
--  ``resto_reglage_type.fin_aujourd_hui`` et ``resto_reglage_type.fin_aujourd_hui_le`` (E6) : l'heure (du lieu) où le type arrête de prendre des
--  commandes AUJOURD'HUI seulement, et le jour (du lieu) où elle vaut ; un autre jour, elle ne compte plus (effacée seule à minuit du lieu). Elle
--  s'ajoute à ``fin_par_jour`` : la plus tôt des deux gagne (le plus prudent).
--  Les droits et la sécurité par ligne des tables ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_zone ADD COLUMN IF NOT EXISTS minutes_ajoutees integer NOT NULL DEFAULT 0 CHECK (minutes_ajoutees BETWEEN 0 AND 240);
ALTER TABLE resto_zone ADD COLUMN IF NOT EXISTS ajout_jusqu_a timestamptz;

ALTER TABLE resto_reglage_type ADD COLUMN IF NOT EXISTS fin_aujourd_hui time;
ALTER TABLE resto_reglage_type ADD COLUMN IF NOT EXISTS fin_aujourd_hui_le date;
ALTER TABLE resto_reglage_type DROP CONSTRAINT IF EXISTS resto_reglage_type_fin_aujourd_hui_check;
ALTER TABLE resto_reglage_type ADD CONSTRAINT resto_reglage_type_fin_aujourd_hui_check
    CHECK ((fin_aujourd_hui IS NULL) = (fin_aujourd_hui_le IS NULL));

INSERT INTO schema_version (version, description) VALUES
    (45, 'Module Restauration : minutes ajoutées par zone de livraison et fin du service pour aujourd''hui, par type')
ON CONFLICT (version) DO NOTHING;
