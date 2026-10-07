-- =====================================================================
--  009 : les mentions d'un salarié et son accès à lui (chantier
--  l-agent-collegue, L3, C11, C14, C15). Additive seulement.
--
--  - mention : chaque fois qu'un salarié est concerné par un appel. Source
--    (transfert, transmission, destinataire, rendez_vous, nom_cite) et
--    certitude (certaine pour un geste fait par le code ; detectee ou
--    a_confirmer pour un nom repéré dans un texte). Une ligne par appel,
--    personne et source : un rejeu n'écrit rien deux fois.
--  - L'accès d'un salarié : un rôle de connexion par salarié, membre du groupe
--    <base>_salarie, qui ne lit QUE deux vues : ses mentions, et les appels de
--    son établissement (plus ceux des établissements qu'on lui ouvre en plus).
--    Le groupe n'est PAS membre de mark_interface : un salarié ne voit ni
--    l'équipe entière (téléphones, mails), ni les sujets, ni les phrases.
--  - Les vues gardent les droits de leur propriétaire (comme 007) et filtrent
--    elles-mêmes sur le rôle qui lit ; la table mention porte en plus une
--    sécurité par ligne pour tout accès direct.
--  - donner_acces / retirer_acces : jouées par le compte propriétaire (celui
--    qui crée les rôles) ; le mot de passe est un argument, jamais stocké ici.
--    Une personne désactivée perd sa connexion (déclencheur).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS mention (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id    bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    personne_id bigint NOT NULL REFERENCES personne(id),
    source      text NOT NULL CHECK (source IN ('transfert', 'transmission', 'destinataire', 'rendez_vous', 'nom_cite')),
    certitude   text NOT NULL CHECK (certitude IN ('certaine', 'detectee', 'a_confirmer')),
    extrait     text CHECK (extrait IS NULL OR char_length(extrait) <= 200),
    le          timestamptz NOT NULL DEFAULT now(),
    UNIQUE (appel_id, personne_id, source)
);
CREATE INDEX IF NOT EXISTS mention_personne_idx ON mention (personne_id, le DESC);
GRANT SELECT, INSERT, UPDATE, DELETE ON mention TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;

-- Quel rôle de connexion est quel salarié (un rôle, une personne).
CREATE TABLE IF NOT EXISTS role_personne (
    role        text PRIMARY KEY,
    personne_id bigint NOT NULL UNIQUE REFERENCES personne(id) ON DELETE CASCADE,
    donne_le    timestamptz NOT NULL DEFAULT now()
);
-- Ni l'écriture courante de Dograh ni l'interface ne touchent aux accès.
REVOKE ALL ON role_personne FROM mark_ecriture, mark_interface;

DO $$
DECLARE
    base text := current_database();
    salarie text := base || '_salarie';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = salarie) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', salarie);
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', base, salarie);
    EXECUTE format('GRANT USAGE ON SCHEMA mark TO %I', salarie);
END $$;

-- La personne d'un rôle (active seulement) ; NULL pour tout autre rôle.
CREATE OR REPLACE FUNCTION personne_du_role(qui name) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT rp.personne_id FROM role_personne rp JOIN personne p ON p.id = rp.personne_id
    WHERE rp.role = qui AND p.actif;
$$;

-- Les établissements d'un salarié : le sien, et ceux qu'on lui a ouverts (role_site).
CREATE OR REPLACE FUNCTION sites_du_salarie(qui name) RETURNS SETOF bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT p.site_id FROM role_personne rp JOIN personne p ON p.id = rp.personne_id
    WHERE rp.role = qui AND p.actif AND p.site_id IS NOT NULL
    UNION
    SELECT r.site_id FROM role_site r
    WHERE r.role = qui AND personne_du_role(qui) IS NOT NULL;
$$;

-- Sécurité par ligne de mention : un salarié ne lit que les siennes ; l'écriture de Dograh lit tout.
CREATE OR REPLACE FUNCTION voit_la_mention(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT NOT pg_has_role(qui, current_database() || '_salarie', 'MEMBER')
        OR cible = personne_du_role(qui);
$$;
ALTER TABLE mention ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS mention_par_personne ON mention;
CREATE POLICY mention_par_personne ON mention USING (voit_la_mention(personne_id, current_user));

-- Ses mentions : l'appel qui le concerne, ce qui l'y a mis, et sa synthèse.
CREATE OR REPLACE VIEW v_mes_mentions AS
SELECT m.id, m.le, m.source, m.certitude, m.extrait,
       a.id AS appel_id, a.debut AS appel_le, s.nom AS site, a.motif, a.synthese,
       a.numero_appelant, d.id AS demande_id, d.statut AS demande_statut
FROM mention m
JOIN appel a          ON a.id = m.appel_id
LEFT JOIN site s      ON s.id = a.site_id
LEFT JOIN demande d   ON d.id = a.demande_id
WHERE m.personne_id = personne_du_role(current_user);

-- Les appels de son établissement (90 jours, comme le cahier).
CREATE OR REPLACE VIEW v_appels_de_mon_etablissement AS
SELECT a.id, a.debut, s.nom AS site, a.issue, a.motif, a.degre_urgence,
       a.duree_s, a.hors_horaires, a.synthese, a.numero_appelant,
       c.nom AS contact_nom, d.id AS demande_id, d.statut AS demande_statut,
       p.prenom AS assignee
FROM appel a
LEFT JOIN site s      ON s.id = a.site_id
LEFT JOIN contact c   ON c.id = a.contact_id
LEFT JOIN demande d   ON d.id = a.demande_id
LEFT JOIN personne p  ON p.id = d.assignee_id
WHERE a.debut > now() - interval '90 days'
  AND a.site_id IN (SELECT sites_du_salarie(current_user));

DO $$
BEGIN
    EXECUTE format('GRANT SELECT ON v_mes_mentions, v_appels_de_mon_etablissement TO %I',
                   current_database() || '_salarie');
END $$;

-- Donner l'accès à un salarié (propriétaire seulement). p_sites : des établissements de plus
-- (clés) ; une personne de toute l'entreprise sans p_sites ne voit que ses mentions.
CREATE OR REPLACE FUNCTION donner_acces(p_cle text, p_mot_de_passe text, p_sites text[] DEFAULT NULL)
RETURNS text LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_personne bigint;
    v_role text;
BEGIN
    SELECT id INTO v_personne FROM personne WHERE cle = p_cle AND actif;
    IF v_personne IS NULL THEN
        RAISE EXCEPTION 'Personne active inconnue : %', p_cle;
    END IF;
    IF coalesce(length(p_mot_de_passe), 0) < 12 THEN
        RAISE EXCEPTION 'Mot de passe trop court (12 caractères au moins)';
    END IF;
    v_role := current_database() || '_p_' || v_personne;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', v_role, p_mot_de_passe);
    ELSE
        EXECUTE format('CREATE ROLE %I LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 PASSWORD %L',
                       v_role, p_mot_de_passe);
    END IF;
    EXECUTE format('GRANT %I TO %I', current_database() || '_salarie', v_role);
    INSERT INTO role_personne (role, personne_id) VALUES (v_role, v_personne)
        ON CONFLICT (role) DO UPDATE SET personne_id = EXCLUDED.personne_id, donne_le = now();
    DELETE FROM role_site WHERE role = v_role;
    INSERT INTO role_site (role, site_id)
        SELECT v_role, s.id FROM site s WHERE s.cle = ANY(coalesce(p_sites, '{}'));
    RETURN v_role;
END $$;

-- Retirer l'accès : le rôle ne se connecte plus, ses établissements de plus sont retirés.
CREATE OR REPLACE FUNCTION retirer_acces(p_cle text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE r record;
BEGIN
    FOR r IN SELECT rp.role FROM role_personne rp JOIN personne p ON p.id = rp.personne_id WHERE p.cle = p_cle LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r.role) THEN
            EXECUTE format('ALTER ROLE %I NOLOGIN', r.role);
        END IF;
        DELETE FROM role_site WHERE role = r.role;
    END LOOP;
END $$;
REVOKE EXECUTE ON FUNCTION donner_acces(text, text, text[]) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION retirer_acces(text) FROM PUBLIC;

-- Désactivé = accès retiré (C14), même quand la désactivation vient de l'écran de Dograh.
CREATE OR REPLACE FUNCTION retirer_acces_a_la_desactivation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
BEGIN
    IF OLD.actif AND NOT NEW.actif AND NEW.cle IS NOT NULL THEN
        PERFORM retirer_acces(NEW.cle);
    END IF;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS personne_desactivee_acces ON personne;
CREATE TRIGGER personne_desactivee_acces AFTER UPDATE OF actif ON personne
    FOR EACH ROW EXECUTE FUNCTION retirer_acces_a_la_desactivation();

INSERT INTO schema_version (version, description) VALUES
    (9, 'Mentions d''un salarié (source, certitude) ; rôle de connexion par salarié limité à ses mentions et aux appels de son établissement');
