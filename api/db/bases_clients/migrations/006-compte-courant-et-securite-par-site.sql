-- =====================================================================
--  006 : le compte courant de Dograh et la sécurité par établissement
--  (chantier l-agent-travaille, décisions d'Evan du 07/10, n° 317).
--  Additive seulement.
--
--  - Dograh ne travaille plus avec le compte propriétaire du serveur : ses
--    connexions courantes (appels, après-appel, synchro, purge, rattrapage)
--    passent par un compte de connexion sans privilège, qui prend le rôle
--    <base>_ecriture (SET ROLE). Le compte propriétaire ne sert plus qu'à
--    « Créer » et « Mettre à niveau ». Ici : les droits que ce rôle doit avoir,
--    et rien de plus (ni schema_version, ni role_site).
--  - La purge de nuit rafraîchit kpi_jour, ce que seul le propriétaire peut
--    faire : nuit() s'exécute donc avec ses droits.
--  - La sécurité par ligne était évaluée pour le PROPRIÉTAIRE de voit_le_site
--    (SECURITY DEFINER : current_user y est le propriétaire), donc ouverte à
--    tous. La règle reçoit désormais le rôle qui demande.
-- =====================================================================
SET search_path = mark;

GRANT USAGE ON SCHEMA mark TO mark_ecriture;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mark TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;
REVOKE INSERT, UPDATE, DELETE ON schema_version, role_site FROM mark_ecriture;

ALTER FUNCTION nuit() SECURITY DEFINER;
REVOKE EXECUTE ON FUNCTION nuit() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION nuit() TO mark_ecriture;

CREATE OR REPLACE FUNCTION voit_le_site(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT cible IS NULL
        OR pg_has_role(qui, current_database() || '_direction', 'MEMBER')
        OR NOT pg_has_role(qui, 'mark_interface', 'MEMBER')
        OR EXISTS (SELECT 1 FROM role_site r WHERE r.role = qui AND r.site_id = cible);
$$;

DROP POLICY IF EXISTS demande_par_site ON demande;
CREATE POLICY demande_par_site ON demande USING (voit_le_site(site_id, current_user));
DROP POLICY IF EXISTS appel_par_site ON appel;
CREATE POLICY appel_par_site ON appel USING (voit_le_site(site_id, current_user));

INSERT INTO schema_version (version, description) VALUES
    (6, 'Compte courant de Dograh (rôle <base>_ecriture), nuit() aux droits du propriétaire, sécurité par ligne évaluée pour le rôle qui demande');
