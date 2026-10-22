-- =====================================================================
--  019 : les objets de l'agent (chantier cloture-code-avant-migration, lot F7 ; D106 à D119, D132).
--  Additive seulement (IF NOT EXISTS, CREATE OR REPLACE, DROP POLICY IF EXISTS) : rien renommé ni
--  retiré. Le nom « objet » est pris (001 : l'objet d'un contact) : tout ici s'appelle objet_agent.
--
--  - objet_agent : une donnée métier que l'agent reçoit en {{nom}}. Deux formes : la valeur simple
--    (type + valeur) et la liste (colonnes typées + lignes). Portée : toute l'entreprise (site_id
--    vide) ou un établissement (D110).
--  - objet_agent_colonne : les colonnes d'une liste ; « pose_par » = mark ou client (D108).
--  - objet_agent_ligne : une ligne = ses cellules, rangées par identifiant de colonne (jsonb).
--  - objet_agent_historique : chaque changement (qui, quand, avant, après), par déclencheur,
--    JAMAIS effacé (D111).
--  - objet_agent_utilisation : quels agents lisent l'objet, CALCULÉ par Dograh (D118 : la présence
--    de {{nom}} dans leurs textes) et écrit ici pour la vue du portail ; jamais saisi.
--  - objet_agent_reglage : le plafond d'un objet en caractères (D112, 3 000 par défaut), réglé par Dograh, lu par
--    le portail, APPLIQUÉ ici à la validation de toute transaction (objet_agent_texte = le rendu du fork).
--  - v_portail_objets : ce que le portail affiche (D119) : (a) la base est celle de l'organisation,
--    (b) l'objet est lu par au moins un agent rattaché au portail, (c) son établissement se voit.
--
--  La validation du type est en SQL (D114) : un montant est un nombre, une date est une date, une
--  ligne vide ne s'enregistre pas. Règle du 22/10 : Dograh (le rôle d'écriture) fait tout ; la seule
--  garde est celle du rôle <base>_portail : sécurité par ligne par établissement (motif de la 015),
--  droits par colonne, et les colonnes posées par .mark ni supprimées ni modifiées par lui.
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  1. La validation d'une valeur par son type (D114). Vide = absent, toujours permis.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION objet_agent_valeur_valide(p_type text, p_valeur text) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog AS $$
BEGIN
    IF p_valeur IS NULL THEN
        RETURN true;
    END IF;
    CASE p_type
        WHEN 'texte' THEN RETURN true;
        WHEN 'nombre' THEN RETURN p_valeur ~ '^-?[0-9]+([.,][0-9]+)?$';
        WHEN 'montant' THEN RETURN p_valeur ~ '^-?[0-9]+([.,][0-9]{1,2})?$';
        WHEN 'oui_non' THEN RETURN p_valeur IN ('oui', 'non');
        WHEN 'date' THEN
            IF p_valeur !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
                RETURN false;
            END IF;
            PERFORM p_valeur::date;
            RETURN true;
        ELSE RETURN false;
    END CASE;
EXCEPTION WHEN others THEN
    RETURN false;
END $$;

-- ---------------------------------------------------------------------
--  2. Les tables.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS objet_agent (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom         text NOT NULL UNIQUE CHECK (nom ~ '^[a-z][a-z0-9_]{0,62}$'),
    libelle     text NOT NULL CHECK (btrim(libelle) <> ''),
    description text,
    forme       text NOT NULL CHECK (forme IN ('valeur', 'liste')),
    type        text CHECK (type IN ('texte', 'nombre', 'montant', 'oui_non', 'date')),
    valeur      text,
    site_id     bigint REFERENCES site(id),
    cree_le     timestamptz NOT NULL DEFAULT now(),
    modifie_le  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT objet_agent_type_de_la_forme CHECK ((forme = 'valeur') = (type IS NOT NULL)),
    CONSTRAINT objet_agent_valeur_de_la_forme CHECK (forme = 'valeur' OR valeur IS NULL),
    CONSTRAINT objet_agent_valeur_du_type CHECK (objet_agent_valeur_valide(type, valeur))
);

CREATE TABLE IF NOT EXISTS objet_agent_colonne (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    objet_id  bigint NOT NULL REFERENCES objet_agent(id) ON DELETE CASCADE,
    libelle   text NOT NULL CHECK (btrim(libelle) <> ''),
    type      text NOT NULL CHECK (type IN ('texte', 'nombre', 'montant', 'oui_non', 'date')),
    ordre     integer NOT NULL DEFAULT 0,
    pose_par  text NOT NULL DEFAULT 'client' CHECK (pose_par IN ('mark', 'client')),
    UNIQUE (objet_id, libelle)
);

CREATE TABLE IF NOT EXISTS objet_agent_ligne (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    objet_id    bigint NOT NULL REFERENCES objet_agent(id) ON DELETE CASCADE,
    ordre       integer NOT NULL DEFAULT 0,
    valeurs     jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(valeurs) = 'object'),
    cree_le     timestamptz NOT NULL DEFAULT now(),
    modifie_le  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS objet_agent_ligne_objet ON objet_agent_ligne (objet_id);

-- Sans clé étrangère vers objet_agent : l'historique survit à l'objet (D111, jamais effacé).
CREATE TABLE IF NOT EXISTS objet_agent_historique (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    objet_id   bigint NOT NULL,
    site_id    bigint,
    table_nom  text NOT NULL,
    ligne_id   bigint NOT NULL,
    operation  text NOT NULL,
    avant      jsonb,
    apres      jsonb,
    auteur     text NOT NULL,
    le         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS objet_agent_historique_objet ON objet_agent_historique (objet_id, id);

CREATE TABLE IF NOT EXISTS objet_agent_utilisation (
    objet_id  bigint NOT NULL REFERENCES objet_agent(id) ON DELETE CASCADE,
    agent_id  bigint NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    PRIMARY KEY (objet_id, agent_id)
);

-- Le plafond d'un objet en caractères (D112) : une ligne, réglée depuis l'écran de Dograh, lue par le
-- portail (sa jauge) ; appliqué ici, à la fin de chaque transaction, quel que soit l'écrivain.
CREATE TABLE IF NOT EXISTS objet_agent_reglage (
    id                  smallint PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    plafond_caracteres  integer NOT NULL DEFAULT 3000 CHECK (plafond_caracteres BETWEEN 100 AND 50000)
);
INSERT INTO objet_agent_reglage (id) VALUES (1) ON CONFLICT DO NOTHING;

-- Le texte que l'objet donne à l'agent, le MÊME que le fork rend (api/services/objets_agent/rendu.py,
-- un test compare les deux) : la valeur ; ou l'en-tête des colonnes puis une ligne par ligne, « | ».
CREATE OR REPLACE FUNCTION objet_agent_texte(cible bigint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT CASE
        WHEN o.forme = 'valeur' THEN coalesce(o.valeur, '')
        WHEN NOT EXISTS (SELECT 1 FROM objet_agent_colonne c WHERE c.objet_id = o.id) THEN ''
        ELSE (SELECT string_agg(c.libelle, ' | ' ORDER BY c.ordre, c.id) FROM objet_agent_colonne c WHERE c.objet_id = o.id)
             || coalesce((SELECT string_agg(
                    E'\n' || (SELECT string_agg(coalesce(l.valeurs ->> c.id::text, ''), ' | ' ORDER BY c.ordre, c.id)
                              FROM objet_agent_colonne c WHERE c.objet_id = o.id),
                    '' ORDER BY l.ordre, l.id)
                  FROM objet_agent_ligne l WHERE l.objet_id = o.id), '')
    END
    FROM objet_agent o WHERE o.id = cible;
$$;

CREATE OR REPLACE FUNCTION objet_agent_taille(cible bigint) RETURNS integer
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT char_length(coalesce(objet_agent_texte(cible), ''));
$$;

-- ---------------------------------------------------------------------
--  3. Les déclencheurs : cohérence, validation, garde des colonnes de .mark, historique.
-- ---------------------------------------------------------------------

-- L'objet : sa date de modification ; une valeur vide est absente ; une forme ne change pas (des
-- colonnes et des lignes en dépendent : on crée un autre objet).
CREATE OR REPLACE FUNCTION objet_agent_avant() RETURNS trigger
LANGUAGE plpgsql SET search_path = mark AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.forme IS DISTINCT FROM OLD.forme THEN
        RAISE EXCEPTION 'objet_agent : la forme d''un objet ne change pas (créez un autre objet)';
    END IF;
    NEW.valeur := CASE WHEN NEW.type = 'texte' THEN CASE WHEN btrim(NEW.valeur) = '' THEN NULL ELSE NEW.valeur END
                       ELSE nullif(btrim(NEW.valeur), '') END;
    NEW.modifie_le := now();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS objet_agent_avant ON objet_agent;
CREATE TRIGGER objet_agent_avant BEFORE INSERT OR UPDATE ON objet_agent
    FOR EACH ROW EXECUTE FUNCTION objet_agent_avant();

-- La colonne : seulement sur une liste ; un type changé doit garder toutes les cellules valides ;
-- ⛔ le rôle du portail ne supprime ni ne modifie une colonne posée par .mark, et n'en pose pas (D108).
-- SECURITY INVOKER (le défaut) : current_user est le rôle qui écrit, c'est lui qu'on juge.
CREATE OR REPLACE FUNCTION objet_agent_colonne_avant() RETURNS trigger
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_mauvaise bigint;
BEGIN
    IF est_du_portail(current_user)
       AND ((TG_OP <> 'INSERT' AND OLD.pose_par = 'mark') OR (TG_OP <> 'DELETE' AND NEW.pose_par = 'mark')) THEN
        RAISE EXCEPTION 'objet_agent_colonne : une colonne posée par .mark ne se supprime ni ne se modifie depuis le portail'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM objet_agent o WHERE o.id = NEW.objet_id AND o.forme = 'liste') THEN
        RAISE EXCEPTION 'objet_agent_colonne : seule une liste a des colonnes';
    END IF;
    IF TG_OP = 'UPDATE' AND NEW.type IS DISTINCT FROM OLD.type THEN
        SELECT l.id INTO v_mauvaise FROM objet_agent_ligne l
        WHERE l.objet_id = NEW.objet_id AND NOT objet_agent_valeur_valide(NEW.type, l.valeurs ->> NEW.id::text)
        LIMIT 1;
        IF v_mauvaise IS NOT NULL THEN
            RAISE EXCEPTION 'objet_agent_colonne : une cellule de la colonne « % » n''est pas du type %', NEW.libelle, NEW.type
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS objet_agent_colonne_avant ON objet_agent_colonne;
CREATE TRIGGER objet_agent_colonne_avant BEFORE INSERT OR UPDATE OR DELETE ON objet_agent_colonne
    FOR EACH ROW EXECUTE FUNCTION objet_agent_colonne_avant();

-- Une colonne supprimée : ses cellules partent des lignes ; une ligne qui n'a plus rien est supprimée
-- (une ligne vide ne s'enregistre pas). Rien quand l'objet lui-même part (cascade).
CREATE OR REPLACE FUNCTION objet_agent_colonne_apres() RETURNS trigger
LANGUAGE plpgsql SET search_path = mark AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM objet_agent WHERE id = OLD.objet_id) THEN
        RETURN NULL;
    END IF;
    DELETE FROM objet_agent_ligne
    WHERE objet_id = OLD.objet_id AND valeurs ? OLD.id::text AND (valeurs - OLD.id::text) = '{}'::jsonb;
    UPDATE objet_agent_ligne SET valeurs = valeurs - OLD.id::text
    WHERE objet_id = OLD.objet_id AND valeurs ? OLD.id::text;
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS objet_agent_colonne_apres ON objet_agent_colonne;
CREATE TRIGGER objet_agent_colonne_apres AFTER DELETE ON objet_agent_colonne
    FOR EACH ROW EXECUTE FUNCTION objet_agent_colonne_apres();

-- La ligne : seulement sur une liste ; chaque cellule est une colonne de l'objet et une chaîne
-- valide pour son type ; les cellules vides sont retirées ; une ligne sans rien est refusée.
CREATE OR REPLACE FUNCTION objet_agent_ligne_avant() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    v_cle     text;
    v_valeur  jsonb;
    v_type    text;
    v_libelle text;
    v_texte   text;
    v_propres jsonb := '{}'::jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM objet_agent o WHERE o.id = NEW.objet_id AND o.forme = 'liste') THEN
        RAISE EXCEPTION 'objet_agent_ligne : seule une liste a des lignes';
    END IF;
    FOR v_cle, v_valeur IN SELECT * FROM jsonb_each(NEW.valeurs) LOOP
        CONTINUE WHEN jsonb_typeof(v_valeur) = 'null';
        IF jsonb_typeof(v_valeur) <> 'string' THEN
            RAISE EXCEPTION 'objet_agent_ligne : une cellule est un texte' USING ERRCODE = 'check_violation';
        END IF;
        SELECT c.type, c.libelle INTO v_type, v_libelle FROM objet_agent_colonne c
        WHERE c.objet_id = NEW.objet_id AND c.id::text = v_cle;
        IF v_type IS NULL THEN
            RAISE EXCEPTION 'objet_agent_ligne : la colonne % n''est pas une colonne de cet objet', v_cle
                USING ERRCODE = 'check_violation';
        END IF;
        v_texte := v_valeur #>> '{}';
        v_texte := CASE WHEN v_type = 'texte' THEN CASE WHEN btrim(v_texte) = '' THEN NULL ELSE v_texte END ELSE nullif(btrim(v_texte), '') END;
        CONTINUE WHEN v_texte IS NULL;
        IF NOT objet_agent_valeur_valide(v_type, v_texte) THEN
            RAISE EXCEPTION 'objet_agent_ligne : « % » n''est pas une valeur de type % (colonne « % »)', v_texte, v_type, v_libelle
                USING ERRCODE = 'check_violation';
        END IF;
        v_propres := v_propres || jsonb_build_object(v_cle, v_texte);
    END LOOP;
    IF v_propres = '{}'::jsonb THEN
        RAISE EXCEPTION 'objet_agent_ligne : une ligne vide ne s''enregistre pas' USING ERRCODE = 'check_violation';
    END IF;
    NEW.valeurs := v_propres;
    NEW.modifie_le := now();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS objet_agent_ligne_avant ON objet_agent_ligne;
CREATE TRIGGER objet_agent_ligne_avant BEFORE INSERT OR UPDATE ON objet_agent_ligne
    FOR EACH ROW EXECUTE FUNCTION objet_agent_ligne_avant();

-- L'établissement d'un objet, même parti (l'historique de sa création le garde) : une ligne
-- d'historique d'un objet d'établissement ne se montre jamais à un autre établissement.
CREATE OR REPLACE FUNCTION objet_agent_site_connu(cible bigint) RETURNS bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT CASE WHEN EXISTS (SELECT 1 FROM objet_agent WHERE id = cible)
                THEN (SELECT site_id FROM objet_agent WHERE id = cible)
                ELSE (SELECT coalesce(h.apres ->> 'site_id', h.avant ->> 'site_id')::bigint
                      FROM objet_agent_historique h
                      WHERE h.objet_id = cible AND h.table_nom = 'objet_agent'
                      ORDER BY h.id DESC LIMIT 1) END;
$$;

-- L'historique (D111) : qui (mark.auteur posé par l'écrivain, sinon le compte), quand, avant, après.
-- Une écriture qui ne change rien ne s'écrit pas. Puis la notification du référentiel : la copie que
-- lisent les appels se refait (B3), comme pour une fiche.
CREATE OR REPLACE FUNCTION journaliser_objet_agent() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    ancien  jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    nouveau jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    ligne   jsonb;
    v_objet bigint;
    v_site  bigint;
BEGIN
    IF TG_OP = 'UPDATE' AND (ancien - 'modifie_le') = (nouveau - 'modifie_le') THEN
        RETURN NULL;
    END IF;
    ligne := coalesce(nouveau, ancien);
    IF TG_TABLE_NAME = 'objet_agent' THEN
        v_objet := (ligne ->> 'id')::bigint;
        v_site := coalesce(nouveau ->> 'site_id', ancien ->> 'site_id')::bigint;
    ELSE
        v_objet := (ligne ->> 'objet_id')::bigint;
        v_site := objet_agent_site_connu(v_objet);
    END IF;
    INSERT INTO objet_agent_historique (objet_id, site_id, table_nom, ligne_id, operation, avant, apres, auteur)
    VALUES (v_objet, v_site, TG_TABLE_NAME, (ligne ->> 'id')::bigint, lower(TG_OP), ancien, nouveau,
            coalesce(nullif(current_setting('mark.auteur', true), ''), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['objet_agent', 'objet_agent_colonne', 'objet_agent_ligne'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_historique', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION journaliser_objet_agent()',
                       t || '_historique', t);
    END LOOP;
END $$;

-- Le plafond (D112), bloquant : vérifié à la VALIDATION de la transaction (un objet réécrit ligne par
-- ligne n'est jugé qu'une fois entier), pour Dograh comme pour le portail.
CREATE OR REPLACE FUNCTION objet_agent_sous_le_plafond() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    v_objet   bigint := (to_jsonb(NEW) ->> CASE WHEN TG_TABLE_NAME = 'objet_agent' THEN 'id' ELSE 'objet_id' END)::bigint;
    v_plafond integer := coalesce((SELECT plafond_caracteres FROM objet_agent_reglage WHERE id = 1), 3000);
    v_n       integer;
    v_libelle text;
BEGIN
    SELECT libelle INTO v_libelle FROM objet_agent WHERE id = v_objet;
    IF v_libelle IS NULL THEN
        RETURN NULL;
    END IF;
    v_n := objet_agent_taille(v_objet);
    IF v_n > v_plafond THEN
        RAISE EXCEPTION 'objet_agent : « % » donne % caractères à l''agent, au-delà du plafond de % (rien n''est enregistré)',
            v_libelle, v_n, v_plafond USING ERRCODE = 'check_violation';
    END IF;
    RETURN NULL;
END $$;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['objet_agent', 'objet_agent_colonne', 'objet_agent_ligne'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_plafond', t);
        EXECUTE format('CREATE CONSTRAINT TRIGGER %I AFTER INSERT OR UPDATE ON %I DEFERRABLE INITIALLY DEFERRED '
                       'FOR EACH ROW EXECUTE FUNCTION objet_agent_sous_le_plafond()', t || '_plafond', t);
    END LOOP;
END $$;

-- L'historique ne s'efface jamais (D111) : ni modifié, ni supprimé, ni vidé, par aucun rôle.
CREATE OR REPLACE FUNCTION objet_agent_historique_garde() RETURNS trigger
LANGUAGE plpgsql SET search_path = mark AS $$
BEGIN
    RAISE EXCEPTION 'objet_agent_historique : l''historique des objets ne s''efface jamais'
        USING ERRCODE = 'insufficient_privilege';
END $$;
DROP TRIGGER IF EXISTS objet_agent_historique_garde ON objet_agent_historique;
CREATE TRIGGER objet_agent_historique_garde BEFORE UPDATE OR DELETE ON objet_agent_historique
    FOR EACH ROW EXECUTE FUNCTION objet_agent_historique_garde();
DROP TRIGGER IF EXISTS objet_agent_historique_garde_vidage ON objet_agent_historique;
CREATE TRIGGER objet_agent_historique_garde_vidage BEFORE TRUNCATE ON objet_agent_historique
    FOR EACH STATEMENT EXECUTE FUNCTION objet_agent_historique_garde();

-- ---------------------------------------------------------------------
--  4. Droits et sécurité par ligne. Dograh (mark_ecriture) : tout. Le portail : son établissement.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION portail_voit_lieu_ou_entreprise(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT CASE WHEN cible IS NULL THEN portail_voit_un_lieu(qui) ELSE portail_voit_site(cible, qui) END;
$$;

CREATE OR REPLACE FUNCTION portail_voit_objet(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND EXISTS (
        SELECT 1 FROM objet_agent o WHERE o.id = cible AND portail_voit_lieu_ou_entreprise(o.site_id, qui));
$$;

GRANT SELECT, INSERT, UPDATE, DELETE ON objet_agent, objet_agent_colonne, objet_agent_ligne,
    objet_agent_utilisation TO mark_ecriture;
GRANT SELECT, INSERT ON objet_agent_historique TO mark_ecriture;
GRANT SELECT, UPDATE ON objet_agent_reglage TO mark_ecriture;
GRANT USAGE ON SEQUENCE objet_agent_id_seq, objet_agent_colonne_id_seq, objet_agent_ligne_id_seq,
    objet_agent_historique_id_seq TO mark_ecriture;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    ALTER TABLE objet_agent ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS objet_agent_autres ON objet_agent;
    CREATE POLICY objet_agent_autres ON objet_agent USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS objet_agent_portail ON objet_agent;
    CREATE POLICY objet_agent_portail ON objet_agent
        USING (portail_voit_lieu_ou_entreprise(site_id, current_user))
        WITH CHECK (portail_voit_lieu_ou_entreprise(site_id, current_user));
    -- Le client maintient la valeur ; il ne crée, ne renomme, ne déplace ni ne supprime un objet (D107).
    EXECUTE format('GRANT SELECT ON objet_agent TO %I', portail);
    EXECUTE format('GRANT UPDATE (valeur) ON objet_agent TO %I', portail);

    -- Les colonnes et les lignes : par leur objet visible.
    ALTER TABLE objet_agent_colonne ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS objet_agent_colonne_autres ON objet_agent_colonne;
    CREATE POLICY objet_agent_colonne_autres ON objet_agent_colonne USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS objet_agent_colonne_portail ON objet_agent_colonne;
    CREATE POLICY objet_agent_colonne_portail ON objet_agent_colonne
        USING (portail_voit_objet(objet_id, current_user)) WITH CHECK (portail_voit_objet(objet_id, current_user));
    -- Sans « pose_par » : une colonne ajoutée par le portail est la sienne (défaut « client »).
    EXECUTE format('GRANT SELECT, DELETE ON objet_agent_colonne TO %I', portail);
    EXECUTE format('GRANT INSERT (objet_id, libelle, type, ordre) ON objet_agent_colonne TO %I', portail);
    EXECUTE format('GRANT UPDATE (libelle, type, ordre) ON objet_agent_colonne TO %I', portail);
    EXECUTE format('GRANT USAGE ON SEQUENCE objet_agent_colonne_id_seq TO %I', portail);

    ALTER TABLE objet_agent_ligne ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS objet_agent_ligne_autres ON objet_agent_ligne;
    CREATE POLICY objet_agent_ligne_autres ON objet_agent_ligne USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS objet_agent_ligne_portail ON objet_agent_ligne;
    CREATE POLICY objet_agent_ligne_portail ON objet_agent_ligne
        USING (portail_voit_objet(objet_id, current_user)) WITH CHECK (portail_voit_objet(objet_id, current_user));
    EXECUTE format('GRANT SELECT, DELETE ON objet_agent_ligne TO %I', portail);
    EXECUTE format('GRANT INSERT (objet_id, ordre, valeurs) ON objet_agent_ligne TO %I', portail);
    EXECUTE format('GRANT UPDATE (ordre, valeurs) ON objet_agent_ligne TO %I', portail);
    EXECUTE format('GRANT USAGE ON SEQUENCE objet_agent_ligne_id_seq TO %I', portail);

    -- L'historique : en lecture, par l'établissement de l'objet (gardé même l'objet parti).
    ALTER TABLE objet_agent_historique ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS objet_agent_historique_autres ON objet_agent_historique;
    CREATE POLICY objet_agent_historique_autres ON objet_agent_historique USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS objet_agent_historique_portail ON objet_agent_historique;
    CREATE POLICY objet_agent_historique_portail ON objet_agent_historique FOR SELECT
        USING (est_du_portail(current_user) AND portail_voit_lieu_ou_entreprise(site_id, current_user));
    EXECUTE format('GRANT SELECT ON objet_agent_historique TO %I', portail);

    ALTER TABLE objet_agent_utilisation ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS objet_agent_utilisation_autres ON objet_agent_utilisation;
    CREATE POLICY objet_agent_utilisation_autres ON objet_agent_utilisation USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS objet_agent_utilisation_portail ON objet_agent_utilisation;
    CREATE POLICY objet_agent_utilisation_portail ON objet_agent_utilisation FOR SELECT
        USING (portail_voit_objet(objet_id, current_user));
    EXECUTE format('GRANT SELECT ON objet_agent_utilisation TO %I', portail);

    -- Le plafond : lu par le portail (sa jauge), réglé par Dograh seulement.
    EXECUTE format('GRANT SELECT ON objet_agent_reglage TO %I', portail);
END $$;

-- ---------------------------------------------------------------------
--  5. Ce que le portail affiche (D119) : un objet de l'organisation (a), lu par au moins un agent
--     rattaché au portail (b : une copie de test n'allume rien, D90), dont l'établissement se voit
--     (c). Il apparaît dès que les trois tiennent et disparaît sinon, sans bouton « publier ».
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portail_objets AS
SELECT o.id, o.nom, o.libelle, o.description, o.forme, o.type, o.valeur, o.site_id,
       s.nom AS site_nom,
       ARRAY(SELECT a.nom FROM objet_agent_utilisation u JOIN agent a ON a.id = u.agent_id
             WHERE u.objet_id = o.id AND a.rattache_le IS NOT NULL ORDER BY a.nom) AS utilise_par,
       (SELECT max(h.le) FROM objet_agent_historique h WHERE h.objet_id = o.id) AS dernier_changement,
       objet_agent_taille(o.id) AS taille,
       (SELECT r.plafond_caracteres FROM objet_agent_reglage r WHERE r.id = 1) AS plafond_caracteres
FROM objet_agent o
LEFT JOIN site s ON s.id = o.site_id
WHERE est_du_portail(current_user)
  AND portail_voit_lieu_ou_entreprise(o.site_id, current_user)
  AND EXISTS (SELECT 1 FROM objet_agent_utilisation u JOIN agent a ON a.id = u.agent_id
              WHERE u.objet_id = o.id AND a.rattache_le IS NOT NULL);

DO $$
BEGIN
    EXECUTE format('GRANT SELECT ON v_portail_objets TO %I', current_database() || '_portail');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (19, 'Objets de l''agent : objet_agent, colonnes, lignes, historique jamais effacé, utilisation calculée par Dograh, plafond appliqué en SQL ; type validé en SQL ; sécurité par ligne du portail par établissement, colonnes de .mark protégées ; v_portail_objets');
