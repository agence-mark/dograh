-- =====================================================================
--  017 : les lectures du portail (chantier cloture-code-avant-migration, lot F1).
--  Additive seulement (IF NOT EXISTS, CREATE OR REPLACE, DROP POLICY IF EXISTS) : rien
--  renommé ni retiré. Le motif de sécurité par ligne est celui de la 015 (bloc « La sécurité
--  par ligne du portail ») : tout autre rôle passe comme avant, le portail ne lit que ses lignes.
--
--  - incident, incident_appel : un incident se voit par l'appel qu'il touche (visible).
--  - appel_perdu : par le numéro appelé, rangé par site_numero (un numéro, un établissement).
--  - societe, adresse : par le contact visible (la société par ses contacts).
--  - type_rendez_vous : lecture ; un lieu, ou toute l'entreprise si le compte voit au moins un lieu.
--  - v_portail_kpi : appels perdus ; l'urgence corrigée sur la demande prime sur celle de l'appel.
--  - liste_valeur : journal des changements, comme les tables du référentiel (la 015 l'a fait
--    pour personne_site). Les listes sont partagées : un compte qui voit un lieu les voit.
--  - v_portail_historique : ce que le compte d'un établissement voit du journal. Sans coordonnées
--    (mail et téléphone des personnes retirés). Les changements d'entreprise : seulement pour qui
--    voit tous les établissements (variable mark.sites_portail = « * »).
--
--  Les fonctions portail_voit_* sont SECURITY DEFINER, comme celles de la 015 : le portail ne reçoit
--  pas de droit de lecture sur les tables qu'elles interrogent (site_numero, contact, personne_site).
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  1. Les règles d'accès des nouvelles lectures (même forme que la 015).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION portail_voit_un_lieu(qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND EXISTS (SELECT 1 FROM site s WHERE portail_voit_site(s.id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_numero(cible text, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND cible IS NOT NULL AND EXISTS (
        SELECT 1 FROM site_numero sn WHERE sn.numero = cible AND portail_voit_site(sn.site_id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_incident(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND EXISTS (
        SELECT 1 FROM incident_appel ia WHERE ia.incident_id = cible AND portail_voit_appel(ia.appel_id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_societe(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND EXISTS (
        SELECT 1 FROM contact c WHERE c.societe_id = cible AND portail_voit_contact(c.id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_personne(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND (
        EXISTS (SELECT 1 FROM personne p WHERE p.id = cible
                AND ((p.site_id IS NULL AND portail_voit_un_lieu(qui)) OR portail_voit_site(p.site_id, qui)))
        OR EXISTS (SELECT 1 FROM personne_site ps WHERE ps.personne_id = cible AND portail_voit_site(ps.site_id, qui)));
$$;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    -- L'incident : visible par l'appel qu'il touche. L'appel lié : par son appel.
    ALTER TABLE incident ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS incident_autres ON incident;
    CREATE POLICY incident_autres ON incident USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS incident_portail ON incident;
    CREATE POLICY incident_portail ON incident FOR SELECT USING (portail_voit_incident(id, current_user));
    EXECUTE format('GRANT SELECT ON incident TO %I', portail);

    ALTER TABLE incident_appel ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS incident_appel_autres ON incident_appel;
    CREATE POLICY incident_appel_autres ON incident_appel USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS incident_appel_portail ON incident_appel;
    CREATE POLICY incident_appel_portail ON incident_appel FOR SELECT USING (portail_voit_appel(appel_id, current_user));
    EXECUTE format('GRANT SELECT ON incident_appel TO %I', portail);

    -- L'appel perdu : par le numéro appelé, rangé dans site_numero.
    ALTER TABLE appel_perdu ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS appel_perdu_autres ON appel_perdu;
    CREATE POLICY appel_perdu_autres ON appel_perdu USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS appel_perdu_portail ON appel_perdu;
    CREATE POLICY appel_perdu_portail ON appel_perdu FOR SELECT USING (portail_voit_numero(numero_appele, current_user));
    EXECUTE format('GRANT SELECT ON appel_perdu TO %I', portail);

    -- La société : par ses contacts visibles. L'adresse : par son contact visible.
    ALTER TABLE societe ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS societe_autres ON societe;
    CREATE POLICY societe_autres ON societe USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS societe_portail ON societe;
    CREATE POLICY societe_portail ON societe FOR SELECT USING (portail_voit_societe(id, current_user));
    EXECUTE format('GRANT SELECT ON societe TO %I', portail);

    ALTER TABLE adresse ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS adresse_autres ON adresse;
    CREATE POLICY adresse_autres ON adresse USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS adresse_portail ON adresse;
    CREATE POLICY adresse_portail ON adresse FOR SELECT USING (portail_voit_contact(contact_id, current_user));
    EXECUTE format('GRANT SELECT ON adresse TO %I', portail);

    -- Le type de rendez-vous : en lecture. Propre à un lieu, ou à toute l'entreprise (lieu vide).
    ALTER TABLE type_rendez_vous ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS type_rendez_vous_autres ON type_rendez_vous;
    CREATE POLICY type_rendez_vous_autres ON type_rendez_vous USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS type_rendez_vous_portail ON type_rendez_vous;
    CREATE POLICY type_rendez_vous_portail ON type_rendez_vous FOR SELECT USING (
        CASE WHEN site_id IS NULL THEN portail_voit_un_lieu(current_user)
             ELSE portail_voit_site(site_id, current_user) END);
    EXECUTE format('GRANT SELECT ON type_rendez_vous TO %I', portail);
END $$;

-- ---------------------------------------------------------------------
--  2. Le journal des listes de valeurs (les cases « réglé seul », « urgent », « opportunité »
--     sont écrites par le portail à partir de la 017). Même fonction que le référentiel ; une
--     liste n'a pas de colonne id, sa ligne se nomme « liste:code ».
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION journaliser_referentiel() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    ancien jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    nouveau jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    ligne jsonb;
BEGIN
    -- Une écriture qui ne change rien (« Enregistrer » sans modification) ne journalise rien.
    IF TG_OP = 'UPDATE' AND ancien = nouveau THEN
        RETURN NULL;
    END IF;
    ligne := coalesce(nouveau, ancien);
    INSERT INTO journal_modif (table_nom, ligne_id, champ, avant, apres, auteur)
    VALUES (TG_TABLE_NAME,
            CASE WHEN TG_TABLE_NAME = 'site_numero' THEN ligne ->> 'numero'
                 WHEN TG_TABLE_NAME IN ('phrase', 'phrase_site') THEN ligne ->> 'variable'
                 WHEN TG_TABLE_NAME = 'reglage_metier' THEN ligne ->> 'cle'
                 WHEN TG_TABLE_NAME = 'personne_sujet' THEN (ligne ->> 'personne_id') || ':' || (ligne ->> 'sujet_id')
                 WHEN TG_TABLE_NAME = 'personne_site' THEN (ligne ->> 'personne_id') || ':' || (ligne ->> 'site_id')
                 WHEN TG_TABLE_NAME = 'liste_valeur' THEN (ligne ->> 'liste') || ':' || (ligne ->> 'code')
                 ELSE ligne ->> 'id' END,
            lower(TG_OP), ancien, nouveau, coalesce(current_setting('mark.auteur', true), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS liste_valeur_referentiel ON liste_valeur;
CREATE TRIGGER liste_valeur_referentiel AFTER INSERT OR UPDATE OR DELETE ON liste_valeur
    FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel();

-- L'entreprise n'était pas journalisée : sa règle du journal (« seulement pour qui voit tous les
-- établissements ») n'aurait rien à montrer. Même déclencheur que les autres tables du référentiel.
DROP TRIGGER IF EXISTS entreprise_referentiel ON entreprise;
CREATE TRIGGER entreprise_referentiel AFTER INSERT OR UPDATE OR DELETE ON entreprise
    FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel();

-- ---------------------------------------------------------------------
--  3. Les indicateurs du portail : appels perdus (par numéro appelé) et urgence corrigée.
--     Les colonnes d'avant gardent leur ordre et leur type ; appels_perdus vient en dernier.
--     Urgence : celle de la demande si elle a été corrigée, sinon celle de l'appel.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portail_kpi AS
WITH x AS (
    SELECT a.site_id,
           (a.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
           a.hors_horaires, a.duree_s,
           (a.appel_precedent_id IS NULL) AS premier_appel,
           EXISTS (SELECT 1 FROM liste_valeur lv
                   WHERE lv.liste = a.issue_liste AND lv.code = a.issue AND lv.regle_seul) AS regle_seul,
           (a.demande_id IS NOT NULL
            OR EXISTS (SELECT 1 FROM transfert tr WHERE tr.appel_id = a.id)) AS transmis,
           EXISTS (SELECT 1 FROM appel_motif am
                   JOIN liste_valeur lv ON lv.liste = am.motif_liste AND lv.code = am.motif
                   WHERE am.appel_id = a.id AND lv.opportunite) AS nouveau_projet,
           EXISTS (SELECT 1 FROM liste_valeur lv
                   WHERE lv.liste = 'degre_urgence'
                     AND lv.code = coalesce(d.degre_urgence, a.degre_urgence) AND lv.urgent) AS urgent,
           (SELECT count(*) FROM rendez_vous r
            WHERE r.demande_id = a.demande_id AND r.origine = 'agent' AND r.statut IN ('pose', 'fait')) AS rendez_vous_pris
    FROM appel a
    LEFT JOIN site s ON s.id = a.site_id
    LEFT JOIN demande d ON d.id = a.demande_id
    WHERE portail_voit_site(a.site_id, current_user)
),
agg AS (
    SELECT x.site_id, x.jour,
           count(*)                                          AS appels,
           count(*) FILTER (WHERE x.hors_horaires)           AS hors_horaires,
           count(*) FILTER (WHERE x.regle_seul)              AS regles_seul,
           count(*) FILTER (WHERE x.transmis)               AS transmis,
           count(*) FILTER (WHERE x.premier_appel)           AS premiers_appels,
           count(*) FILTER (WHERE x.nouveau_projet)          AS nouveaux_projets,
           count(*) FILTER (WHERE x.urgent)                  AS urgents,
           coalesce(sum(x.duree_s), 0)::bigint               AS duree_totale_s,
           coalesce(sum(x.rendez_vous_pris), 0)::bigint      AS rendez_vous_pris
    FROM x
    GROUP BY x.site_id, x.jour
),
perdus AS (
    SELECT sn.site_id,
           (p.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
           count(*) AS appels_perdus
    FROM appel_perdu p
    JOIN site_numero sn ON sn.numero = p.numero_appele
    LEFT JOIN site s ON s.id = sn.site_id
    WHERE portail_voit_numero(p.numero_appele, current_user)
    GROUP BY sn.site_id, 2
),
cles AS (
    SELECT site_id, jour FROM agg
    UNION
    SELECT site_id, jour FROM perdus
)
SELECT c.site_id, c.jour,
       coalesce(g.appels, 0)              AS appels,
       coalesce(g.hors_horaires, 0)       AS hors_horaires,
       coalesce(g.regles_seul, 0)         AS regles_seul,
       coalesce(g.transmis, 0)            AS transmis,
       coalesce(g.premiers_appels, 0)     AS premiers_appels,
       coalesce(g.nouveaux_projets, 0)    AS nouveaux_projets,
       coalesce(g.urgents, 0)             AS urgents,
       coalesce(g.duree_totale_s, 0)      AS duree_totale_s,
       coalesce(g.rendez_vous_pris, 0)    AS rendez_vous_pris,
       coalesce(p.appels_perdus, 0)       AS appels_perdus
FROM cles c
LEFT JOIN agg g ON g.site_id IS NOT DISTINCT FROM c.site_id AND g.jour = c.jour
LEFT JOIN perdus p ON p.site_id IS NOT DISTINCT FROM c.site_id AND p.jour = c.jour;

-- ---------------------------------------------------------------------
--  4. Le journal que voit le portail (v_portail_historique).
--     Une ligne de journal se voit si son lieu se voit (site_id de la ligne, avant ou après).
--     Sans lieu (propre à l'entreprise) : visible à un compte qui voit au moins un lieu.
--     Mail et téléphone d'une personne : jamais dans la vue (la 015 ne les lui donne pas non plus).
--     Hors liste : rien. Les phrases de l'agent et les réglages métier ne sont pas dans cette vue.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portail_historique AS
SELECT j.id, j.table_nom, j.ligne_id, j.champ,
       CASE WHEN j.table_nom = 'personne' THEN j.avant - 'mail' - 'telephone' ELSE j.avant END AS avant,
       CASE WHEN j.table_nom = 'personne' THEN j.apres - 'mail' - 'telephone' ELSE j.apres END AS apres,
       j.auteur, j.le
FROM (
    SELECT jm.*, coalesce(jm.apres ->> 'site_id', jm.avant ->> 'site_id') AS lieu_txt
    FROM journal_modif jm
) j
WHERE est_du_portail(current_user) AND CASE
    WHEN j.table_nom = 'entreprise'
        THEN btrim(coalesce(current_setting('mark.sites_portail', true), '')) = '*'
    WHEN j.table_nom IN ('liste_valeur', 'sujet')
        THEN portail_voit_un_lieu(current_user)
    WHEN j.table_nom = 'site'
        THEN j.ligne_id ~ '^[0-9]+$' AND portail_voit_site(j.ligne_id::bigint, current_user)
    WHEN j.table_nom IN ('site_numero', 'horaire', 'fermeture', 'type_rendez_vous',
                         'reglage_planificateur', 'personne', 'personne_site')
        THEN CASE WHEN j.lieu_txt IS NULL THEN portail_voit_un_lieu(current_user)
                  ELSE portail_voit_site(j.lieu_txt::bigint, current_user) END
    WHEN j.table_nom = 'personne_sujet'
        THEN portail_voit_personne(split_part(j.ligne_id, ':', 1)::bigint, current_user)
    ELSE false
END;

DO $$
BEGIN
    EXECUTE format('GRANT SELECT ON v_portail_kpi, v_portail_historique TO %I', current_database() || '_portail');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (17, 'Lectures du portail : incident, appel perdu, société, adresse, type de rendez-vous (sécurité par ligne) ; appels perdus et urgence corrigée dans v_portail_kpi ; journal des listes de valeurs ; v_portail_historique sans coordonnées');
