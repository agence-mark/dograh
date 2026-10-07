-- =====================================================================
--  012 : le verdict de la fiche d'un appel (chantier l-agent-collegue,
--  L7, Q-2 ; plan qualite-des-donnees, lot 3). Additive seulement.
--
--  - appel.qualite_fiche : le verdict du contrôle de fin d'appel
--    ({statut : complete | a_reprendre | non_controle, problemes : [...]}),
--    écrit à côté de la fiche, qui reste ce que l'extraction a écrit
--    (QD8 : rien n'est corrigé). Vide : agent sans contrôle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE appel ADD COLUMN IF NOT EXISTS qualite_fiche jsonb;

INSERT INTO schema_version (version, description) VALUES
    (12, 'Qualité de la fiche : le verdict du contrôle de fin d''appel, à côté de la fiche');
