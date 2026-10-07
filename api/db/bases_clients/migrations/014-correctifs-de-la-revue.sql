-- =====================================================================
--  014 : correctifs de la revue indépendante du chantier l-agent-collegue
--  (07/10). Additive seulement : rien de 009 ni de 011 n'est modifié, on
--  resserre par-dessus (rejouable).
--
--  - verification : le rôle d'interface (les gens du cahier) n'y lit plus
--    rien. La 011 lui accordait SELECT sans filtre par établissement : un
--    responsable d'un établissement aurait lu les vérifications de tous. La
--    table reste lisible par l'écriture de Dograh et par la direction à la
--    main (propriétaire) ; une vue filtrée viendra si l'interface en a besoin.
--  - retirer_acces : retirer l'accès d'un salarié le coupe vraiment. Avant,
--    NOLOGIN seulement : une session déjà ouverte gardait ses droits tant
--    qu'elle ne se reconnectait pas. Maintenant : plus de connexion, plus
--    membre du groupe des salariés, ses établissements de plus et sa ligne
--    de rôle supprimés (donc plus aucune de ses vues ne rend une ligne), et
--    ses sessions ouvertes sont fermées.
--  - personne_du_role et sites_du_salarie (SECURITY DEFINER, exécutables
--    par tous parce que les vues du salarié les appellent avec SES droits
--    d'exécution) ne répondent plus à un salarié que pour lui-même : il ne
--    peut plus demander « qui est ce rôle ? » pour un autre. Le propriétaire
--    et les comptes de Dograh gardent la réponse pour tous.
--  - voit_le_site : un salarié n'est jamais un lecteur « tout voir » (le
--    groupe n'est pas membre du rôle d'interface, ce que la règle prenait
--    pour un compte interne). Il n'a aucun droit sur les tables, mais la
--    règle le dit maintenant elle-même (défense en profondeur).
-- =====================================================================
SET search_path = mark;

REVOKE SELECT ON verification FROM mark_interface;

CREATE OR REPLACE FUNCTION retirer_acces(p_cle text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    r record;
    v_groupe text := current_database() || '_salarie';
BEGIN
    FOR r IN SELECT rp.role FROM role_personne rp JOIN personne p ON p.id = rp.personne_id WHERE p.cle = p_cle LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.role) THEN
            EXECUTE format('ALTER ROLE %I NOLOGIN', r.role);
            EXECUTE format('REVOKE %I FROM %I', v_groupe, r.role);
            BEGIN
                PERFORM pg_terminate_backend(a.pid) FROM pg_stat_activity a
                WHERE a.usename = r.role AND a.pid <> pg_backend_pid();
            EXCEPTION WHEN insufficient_privilege THEN
                -- Sans le droit de fermer la session : elle ne lit plus rien (plus de groupe, plus de ligne de rôle).
                RAISE WARNING 'Sessions de % non fermées (droit manquant)', r.role;
            END;
        END IF;
        DELETE FROM role_site WHERE role = r.role;
        DELETE FROM role_personne WHERE role = r.role;
    END LOOP;
END $$;
REVOKE EXECUTE ON FUNCTION retirer_acces(text) FROM PUBLIC;

-- Membre DIRECT du groupe des salariés (pg_has_role dit vrai pour tout superutilisateur : inutilisable ici).
CREATE OR REPLACE FUNCTION est_un_salarie(qui name) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT EXISTS (
        SELECT 1 FROM pg_auth_members m
        JOIN pg_roles g ON g.oid = m.roleid AND g.rolname = current_database() || '_salarie'
        JOIN pg_roles u ON u.oid = m.member AND u.rolname = qui
    );
$$;

CREATE OR REPLACE FUNCTION personne_du_role(qui name) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT rp.personne_id FROM role_personne rp JOIN personne p ON p.id = rp.personne_id
    WHERE rp.role = qui AND p.actif
      AND (qui = session_user OR NOT est_un_salarie(session_user));
$$;

CREATE OR REPLACE FUNCTION sites_du_salarie(qui name) RETURNS SETOF bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT p.site_id FROM role_personne rp JOIN personne p ON p.id = rp.personne_id
    WHERE rp.role = qui AND p.actif AND p.site_id IS NOT NULL
      AND (qui = session_user OR NOT est_un_salarie(session_user))
    UNION
    SELECT r.site_id FROM role_site r
    WHERE r.role = qui AND personne_du_role(qui) IS NOT NULL;
$$;

CREATE OR REPLACE FUNCTION voit_le_site(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT NOT est_un_salarie(qui)
       AND (cible IS NULL
            OR pg_has_role(qui, current_database() || '_direction', 'MEMBER')
            OR NOT pg_has_role(qui, 'mark_interface', 'MEMBER')
            OR EXISTS (SELECT 1 FROM role_site r WHERE r.role = qui AND r.site_id = cible));
$$;

INSERT INTO schema_version (version, description) VALUES
    (14, 'Correctifs de la revue : verification fermée à l''interface, retrait d''accès complet (groupe, sessions), fonctions du salarié muettes pour un autre rôle');
