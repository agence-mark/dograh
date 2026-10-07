-- =====================================================================
--  013 : la fenêtre du tour de rôle devient un réglage du planificateur
--  (chantier l-agent-collegue, retouche R-7 ; plan L5, P7). Additive seulement.
--
--  - reglage_planificateur.fenetre_equite_jours : le nombre de jours sur
--    lesquels la répartition « tour_de_role » compte les rendez-vous
--    déjà donnés pour savoir à qui c'est le tour (de 1 à 365). Vide =
--    hérité (l'établissement hérite de l'organisation, l'organisation du
--    défaut commun posé par le code : 30 jours, jamais ici).
--  Journalisé et notifié comme le reste du référentiel (déclencheur de
--  la table, déjà en place depuis 010) ; modifiable à l'écran, à la main
--  et plus tard par le client dans Metabase.
-- =====================================================================
SET search_path = mark;

ALTER TABLE reglage_planificateur
    ADD COLUMN IF NOT EXISTS fenetre_equite_jours smallint
    CHECK (fenetre_equite_jours BETWEEN 1 AND 365);

INSERT INTO schema_version (version, description) VALUES
    (13, 'Planificateur : fenêtre du tour de rôle réglable (héritage organisation, établissement)');
