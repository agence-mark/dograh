-- =====================================================================
--  028 : salle, réservations, journal des changements, version de la carte, récapitulatif par jour
--  (module Restauration, lot 1). Additive seulement. Voir la 025 pour la règle des droits.
--
--  - Salle : salles, tables (couverts min et max, position, assemblable avec), services et créneaux, durée par
--    taille de groupe, règles, réservations. Le portail les écrit (directe) ; la réservation créée ou changée par
--    le restaurant passe par une route du fork (contrat portail § 1), le portail LIT donc resto_reservation.
--  - resto_journal : le journal des changements (objet, avant, après, source, qui, quand), tenu par des
--    DÉCLENCHEURS sur toutes les tables des 025 à 028 : une écriture du fork comme du portail est journalisée.
--    ``mark.auteur`` (qui) et ``mark.source`` (caisse, portail, mark, agent) se posent par session, comme le
--    journal du référentiel ; sans eux, l'auteur est le rôle de connexion et la source se déduit du rôle.
--  - resto_version_carte : un entier par établissement, augmenté par déclencheur à tout changement de la carte,
--    quelle que soit la source (D10). Un changement de la carte d'enseigne augmente la version de tous.
--  - resto_recap_jour : le récapitulatif chiffré par jour et par mode, sans aucune donnée personnelle ; il survit
--    à la purge des 30 jours (T-23) et fait vivre le Dashboard.
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS resto_salle (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    nom     text NOT NULL CHECK (btrim(nom) <> ''),
    ordre   integer NOT NULL DEFAULT 0,
    plan    jsonb CHECK (plan IS NULL OR jsonb_typeof(plan) = 'object'),
    maj_le  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_salle_site_idx ON resto_salle (site_id, ordre);

CREATE TABLE IF NOT EXISTS resto_table (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    salle_id        bigint NOT NULL REFERENCES resto_salle(id) ON DELETE CASCADE,
    nom             text NOT NULL CHECK (btrim(nom) <> ''),
    couverts_min    integer NOT NULL DEFAULT 1 CHECK (couverts_min >= 1),
    couverts_max    integer NOT NULL CHECK (couverts_max >= 1),
    x               numeric(7, 2),
    y               numeric(7, 2),
    assemblable_avec bigint[] NOT NULL DEFAULT '{}',
    actif           boolean NOT NULL DEFAULT true,
    maj_le          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_table_couverts CHECK (couverts_max >= couverts_min)
);
CREATE INDEX IF NOT EXISTS resto_table_salle_idx ON resto_table (site_id, salle_id);

-- Un service : des jours, de l'heure à l'heure, un pas de créneau.
CREATE TABLE IF NOT EXISTS resto_service (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    nom         text NOT NULL CHECK (btrim(nom) <> ''),
    jours       smallint[] NOT NULL DEFAULT '{1,2,3,4,5,6,7}',    -- 1 = lundi
    debut       time NOT NULL,
    fin         time NOT NULL,
    pas_minutes integer NOT NULL DEFAULT 15 CHECK (pas_minutes BETWEEN 5 AND 120),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_service_heures CHECK (fin > debut)
);
CREATE INDEX IF NOT EXISTS resto_service_site_idx ON resto_service (site_id);

CREATE TABLE IF NOT EXISTS resto_duree_groupe (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id       bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    couverts_min  integer NOT NULL CHECK (couverts_min >= 1),
    couverts_max  integer NOT NULL CHECK (couverts_max >= couverts_min),
    duree_minutes integer NOT NULL CHECK (duree_minutes BETWEEN 15 AND 600),
    maj_le        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_duree_groupe_site_idx ON resto_duree_groupe (site_id, couverts_min);

CREATE TABLE IF NOT EXISTS resto_regle_reservation (
    site_id            bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    delai_minimal      integer NOT NULL DEFAULT 60 CHECK (delai_minimal >= 0),
    jours_a_l_avance   integer NOT NULL DEFAULT 30 CHECK (jours_a_l_avance >= 0),
    couverts_max_groupe integer CHECK (couverts_max_groupe IS NULL OR couverts_max_groupe >= 1),
    couverts_max_creneau integer CHECK (couverts_max_creneau IS NULL OR couverts_max_creneau >= 1),
    maj_le             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resto_reservation (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero        uuid NOT NULL UNIQUE,
    site_id       bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    debut         timestamptz NOT NULL,
    duree_minutes integer NOT NULL CHECK (duree_minutes > 0),
    couverts      integer NOT NULL CHECK (couverts >= 1),
    telephone     text,
    prenom        text,
    table_ids     bigint[] NOT NULL DEFAULT '{}',
    statut        text NOT NULL DEFAULT 'confirmee' CHECK (statut IN ('confirmee', 'annulee', 'honoree', 'absente')),
    note          text,
    cree_par      text NOT NULL DEFAULT 'agent' CHECK (cree_par IN ('agent', 'portail', 'caisse')),
    appel_id      text,
    cree_le       timestamptz NOT NULL DEFAULT now(),
    maj_le        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_reservation_site_debut_idx ON resto_reservation (site_id, debut);

-- ---------------------------------------------------------------------
--  Mesures et suivis.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resto_journal (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id   bigint,
    objet     text NOT NULL,                        -- le nom de la table
    ligne_id  text NOT NULL,
    operation text NOT NULL CHECK (operation IN ('insert', 'update', 'delete')),
    avant     jsonb,
    apres     jsonb,
    source    text NOT NULL,
    auteur    text NOT NULL,
    le        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_journal_site_idx ON resto_journal (site_id, le DESC);
CREATE INDEX IF NOT EXISTS resto_journal_objet_idx ON resto_journal (objet, ligne_id);

CREATE TABLE IF NOT EXISTS resto_recap_jour (
    site_id          bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    jour             date NOT NULL,
    mode             text NOT NULL,
    nb_commandes     integer NOT NULL DEFAULT 0 CHECK (nb_commandes >= 0),
    nb_annulees      integer NOT NULL DEFAULT 0 CHECK (nb_annulees >= 0),
    chiffre_affaires integer NOT NULL DEFAULT 0,
    frais            integer NOT NULL DEFAULT 0,
    remises          integer NOT NULL DEFAULT 0,
    PRIMARY KEY (site_id, jour, mode)
);

CREATE TABLE IF NOT EXISTS resto_version_carte (
    site_id bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    version bigint NOT NULL DEFAULT 1 CHECK (version >= 1)
);

-- ---------------------------------------------------------------------
--  Déclencheurs : le journal et la version de la carte.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION resto_journaliser() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    ancien jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    nouveau jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    ligne jsonb;
    source_ecriture text;
BEGIN
    -- Une écriture qui ne change rien (hors date de mise à jour) ne journalise rien.
    IF TG_OP = 'UPDATE' AND (ancien - 'maj_le') = (nouveau - 'maj_le') THEN
        RETURN NULL;
    END IF;
    -- La purge de conservation efface le détail : elle ne laisse pas, dans le journal, une copie de ce qu'elle efface
    -- (ni de ce que l'effacement entraîne : le lien d'une fiche vers la commande effacée).
    IF current_setting('mark.purge', true) = 'on' THEN
        RETURN NULL;
    END IF;
    ligne := coalesce(nouveau, ancien);
    source_ecriture := coalesce(
        nullif(current_setting('mark.source', true), ''),
        CASE WHEN est_du_portail(session_user) THEN 'portail' ELSE 'mark' END);
    INSERT INTO resto_journal (site_id, objet, ligne_id, operation, avant, apres, source, auteur)
    VALUES (nullif(ligne ->> 'site_id', '')::bigint,
            TG_TABLE_NAME,
            CASE WHEN TG_TABLE_NAME = 'resto_commande' THEN ligne ->> 'numero'
                 WHEN TG_TABLE_NAME = 'resto_reglage_type' THEN (ligne ->> 'site_id') || ':' || (ligne ->> 'type')
                 WHEN TG_TABLE_NAME IN ('resto_etat_caisse', 'resto_liaison', 'resto_reglage', 'resto_regle_reservation')
                     THEN ligne ->> 'site_id'
                 ELSE ligne ->> 'id' END,
            lower(TG_OP), ancien, nouveau, source_ecriture,
            coalesce(nullif(current_setting('mark.auteur', true), ''), session_user));
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION resto_monter_version_carte() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    cible bigint := CASE WHEN TG_OP = 'DELETE' THEN OLD.site_id ELSE NEW.site_id END;
BEGIN
    INSERT INTO resto_version_carte (site_id, version)
    SELECT s.id, 1 FROM site s WHERE cible IS NULL OR s.id = cible
    ON CONFLICT (site_id) DO UPDATE SET version = resto_version_carte.version + 1;
    RETURN NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'resto_categorie', 'resto_produit', 'resto_declinaison', 'resto_groupe_choix', 'resto_option', 'resto_formule',
        'resto_surcouche', 'resto_rupture', 'resto_etat_caisse', 'resto_reglage_type', 'resto_zone', 'resto_commande',
        'resto_liaison', 'resto_client', 'resto_remise', 'resto_envoi', 'resto_reglage', 'resto_salle', 'resto_table',
        'resto_service', 'resto_duree_groupe', 'resto_regle_reservation', 'resto_reservation'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_journal', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION resto_journaliser()',
                       t || '_journal', t);
    END LOOP;
    -- La version de la carte : la carte et ses surcouches (l'index de recherche en dépend), toute source.
    FOREACH t IN ARRAY ARRAY['resto_categorie', 'resto_produit', 'resto_declinaison', 'resto_groupe_choix',
                             'resto_option', 'resto_formule', 'resto_surcouche'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_version', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION resto_monter_version_carte()',
                       t || '_version', t);
    END LOOP;
    -- Une carte déjà là (avant ce déclencheur) a sa version.
    INSERT INTO resto_version_carte (site_id, version) SELECT id, 1 FROM site ON CONFLICT (site_id) DO NOTHING;

    FOREACH t IN ARRAY ARRAY['resto_salle', 'resto_table', 'resto_service', 'resto_duree_groupe', 'resto_regle_reservation', 'resto_reservation'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_maj_le', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION resto_maj_le()', t || '_maj_le', t);
    END LOOP;
    PERFORM resto_droits('resto_salle', 'ecriture');
    PERFORM resto_droits('resto_table', 'ecriture');
    PERFORM resto_droits('resto_service', 'ecriture');
    PERFORM resto_droits('resto_duree_groupe', 'ecriture');
    PERFORM resto_droits('resto_regle_reservation', 'ecriture');
    PERFORM resto_droits('resto_reservation', 'lecture');
    PERFORM resto_droits('resto_journal', 'lecture', true);
    PERFORM resto_droits('resto_recap_jour', 'lecture');
    PERFORM resto_droits('resto_version_carte', 'lecture');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (28, 'Module Restauration : salles, tables, services, durées, règles, réservations ; journal des changements par déclencheurs (mark.auteur, mark.source), version de la carte, récapitulatif chiffré par jour')
ON CONFLICT (version) DO NOTHING;
