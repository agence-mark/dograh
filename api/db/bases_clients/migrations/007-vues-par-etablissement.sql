-- =====================================================================
--  007 : les vues de l'interface filtrent elles-mêmes par établissement
--  (chantier l-agent-travaille, décisions d'Evan du 07/10 : n° 318 option B,
--  et le numéro de l'appelant n'est jamais masqué, la « parade 4 » est retirée).
--  Mêmes colonnes, même ordre, mêmes droits ; numero_masque devient
--  numero_appelant, en clair.
--
--  Les vues gardent les droits de leur propriétaire (pas de security_invoker) :
--  le rôle d'interface n'a aucun droit sur appel ni contact, il ne lit que ce
--  que les vues exposent, et la fenêtre de 90 jours du cahier tient (« parade
--  3 »). La sécurité par ligne des
--  tables ne s'applique pas à travers elles (le propriétaire la contourne) :
--  chaque vue applique donc la même règle, voit_le_site(site_id, current_user),
--  current_user étant dans une vue le rôle qui lit.
-- =====================================================================
SET search_path = mark;

ALTER VIEW v_cahier_appels RENAME COLUMN numero_masque TO numero_appelant;

CREATE OR REPLACE VIEW v_cahier_appels AS
SELECT a.id, a.debut, s.nom AS site, a.issue, a.motif, a.degre_urgence,
       a.duree_s, a.hors_horaires, a.synthese,
       a.numero_appelant,
       c.nom AS contact_nom, d.id AS demande_id, d.statut AS demande_statut
FROM appel a
LEFT JOIN site s    ON s.id = a.site_id
LEFT JOIN contact c ON c.id = a.contact_id
LEFT JOIN demande d ON d.id = a.demande_id
WHERE a.debut > now() - interval '90 days'
  AND voit_le_site(a.site_id, current_user);

-- L'indice « autre demande ouverte du même numéro » ne désigne jamais une
-- demande d'un établissement que le rôle ne voit pas.
CREATE OR REPLACE VIEW v_a_rappeler AS
SELECT d.id, d.creee_le, d.type, d.priorite, d.degre_urgence, d.resume,
       s.nom AS site, p.prenom AS assignee, c.nom AS contact_nom, num.numero AS telephone,
       autre.id AS autre_demande_ouverte_id, autre.creee_le AS autre_demande_le,
       autre.type AS autre_demande_type
FROM demande d
LEFT JOIN site s      ON s.id = d.site_id
LEFT JOIN personne p  ON p.id = d.assignee_id
LEFT JOIN contact c   ON c.id = d.contact_id
LEFT JOIN LATERAL (SELECT a.numero_appelant AS numero FROM appel a
                   WHERE a.demande_id = d.id ORDER BY a.debut LIMIT 1) num ON true
LEFT JOIN LATERAL (SELECT d2.id, d2.creee_le, d2.type
                   FROM appel a2 JOIN demande d2 ON d2.id = a2.demande_id
                   WHERE a2.numero_appelant = num.numero AND d2.id <> d.id
                     AND d2.close_le IS NULL AND d2.rattachee_a_id IS NULL
                     AND voit_le_site(d2.site_id, current_user)
                   ORDER BY d2.creee_le DESC LIMIT 1) autre ON true
WHERE d.rappelee_le IS NULL AND d.close_le IS NULL AND d.rattachee_a_id IS NULL
  AND voit_le_site(d.site_id, current_user)
ORDER BY d.priorite, d.creee_le;

INSERT INTO schema_version (version, description) VALUES
    (7, 'Vues de l''interface filtrées par établissement (droits du propriétaire, 90 jours du cahier), numéro de l''appelant en clair');
