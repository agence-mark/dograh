-- =====================================================================
--  04-mpd.sql : la base d'un client .mark, version 1 (2026-10-06)
--
--  Modèle physique PostgreSQL (16+) déduit de 03-mld.md.
--  Identique chez TOUS les clients : un besoin propre = une ligne de
--  liste_valeur, une clé de reglage_metier ou un champ de « mesures »,
--  jamais une table en plus.
--  ⛔ Aucune donnée client, aucun jeu d'essai nominatif dans ce fichier.
-- =====================================================================

BEGIN;

CREATE SCHEMA IF NOT EXISTS mark;
SET search_path = mark;

-- ---------------------------------------------------------------------
--  0. Version du schéma (une ligne par migration appliquée)
-- ---------------------------------------------------------------------
CREATE TABLE schema_version (
    version      integer PRIMARY KEY,
    appliquee_le timestamptz NOT NULL DEFAULT now(),
    description  text NOT NULL
);

-- ---------------------------------------------------------------------
--  A. Référentiel
-- ---------------------------------------------------------------------
CREATE TABLE liste_valeur (
    liste   text    NOT NULL,          -- type_demande, statut_demande, issue_appel…
    code    text    NOT NULL,
    libelle text    NOT NULL,
    ordre   integer NOT NULL DEFAULT 0,
    actif   boolean NOT NULL DEFAULT true,
    PRIMARY KEY (liste, code)
);

CREATE TABLE entreprise (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raison_sociale text NOT NULL,
    siren          char(9),
    nom_commercial text
);

CREATE TABLE site (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entreprise_id bigint NOT NULL REFERENCES entreprise(id),
    nom           text NOT NULL,
    adresse       text,
    telephone     text,
    numero_appele text UNIQUE,         -- le numéro de l'agent pour ce site (E.164)
    fuseau        text NOT NULL DEFAULT 'Europe/Paris',
    actif         boolean NOT NULL DEFAULT true
);

CREATE TABLE horaire (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id   bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    jour      smallint NOT NULL CHECK (jour BETWEEN 1 AND 7),   -- 1 = lundi
    ouverture time NOT NULL,
    fermeture time NOT NULL CHECK (fermeture > ouverture)
);

CREATE TABLE fermeture (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    du      timestamptz NOT NULL,
    au      timestamptz NOT NULL CHECK (au > du),
    motif   text
);

CREATE TABLE personne (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id             bigint REFERENCES site(id),        -- vide = portée entreprise
    prenom              text NOT NULL,
    nom                 text,
    role                text,
    mail                text,
    telephone           text,
    destinataire_defaut boolean NOT NULL DEFAULT false,
    actif               boolean NOT NULL DEFAULT true      -- départ d'un salarié : on désactive
);

CREATE TABLE sujet (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code              text NOT NULL UNIQUE,
    libelle           text NOT NULL,
    mots_declencheurs text[] NOT NULL DEFAULT '{}',
    urgent            boolean NOT NULL DEFAULT false,
    actif             boolean NOT NULL DEFAULT true
);

CREATE TABLE personne_sujet (
    personne_id bigint NOT NULL REFERENCES personne(id) ON DELETE CASCADE,
    sujet_id    bigint NOT NULL REFERENCES sujet(id) ON DELETE CASCADE,
    priorite    smallint NOT NULL DEFAULT 1,
    PRIMARY KEY (personne_id, sujet_id)
);

CREATE TABLE agent (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dograh_workflow_id integer NOT NULL UNIQUE,
    nom               text NOT NULL
);

CREATE TABLE version_agent (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    agent_id             bigint NOT NULL REFERENCES agent(id),
    dograh_definition_id integer NOT NULL UNIQUE,
    numero_version       integer,
    publiee_le           timestamptz
);

CREATE TABLE agent_site (
    agent_id bigint NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    site_id  bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    PRIMARY KEY (agent_id, site_id)
);

-- Réglages métier modifiables par le client (liste fermée, décidée par .mark)
CREATE TABLE reglage_metier (
    cle         text PRIMARY KEY,
    valeur      jsonb NOT NULL,
    bornes      jsonb,                 -- ce que notre serveur accepte (format, min, max)
    modifie_le  timestamptz NOT NULL DEFAULT now(),
    modifie_par text NOT NULL
);

CREATE TABLE journal_modif (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    table_nom text NOT NULL,
    ligne_id  text NOT NULL,
    champ     text,
    avant     jsonb,
    apres     jsonb,
    auteur    text NOT NULL,
    le        timestamptz NOT NULL DEFAULT now()
);

-- Durées de conservation, table par table (IX.1 : jamais « sur toute la base »)
CREATE TABLE politique_conservation (
    table_nom   text PRIMARY KEY,
    duree       interval NOT NULL,
    colonne_date text NOT NULL,
    decidee_le  date NOT NULL,
    source      text NOT NULL
);

-- ---------------------------------------------------------------------
--  B. Contacts
-- ---------------------------------------------------------------------
-- La société pour laquelle appelle un contact professionnel (transporteur, fournisseur…)
CREATE TABLE societe (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nom     text NOT NULL,
    siret   char(14),
    cree_le timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE contact (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    societe_id        bigint REFERENCES societe(id) ON DELETE SET NULL,
    nom               text,
    prenom            text,
    mail              text,
    nature_liste      text GENERATED ALWAYS AS ('nature_contact') STORED,
    nature            text NOT NULL DEFAULT 'particulier',
    cree_le           timestamptz NOT NULL DEFAULT now(),
    derniere_activite timestamptz NOT NULL DEFAULT now(),  -- point de départ des 3 ans (CNIL)
    FOREIGN KEY (nature_liste, nature) REFERENCES liste_valeur(liste, code)
);

CREATE TABLE telephone (
    numero     text PRIMARY KEY,       -- E.164, ex. +33612345678
    contact_id bigint REFERENCES contact(id) ON DELETE CASCADE,
    type       text                    -- mobile, fixe, standard : indicatif, libre
);

CREATE TABLE adresse (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id       bigint REFERENCES contact(id) ON DELETE CASCADE,
    numero           text,
    voie             text,
    code_postal      char(5),
    commune          text,
    code_insee       char(5),
    latitude         numeric(9, 6),
    longitude        numeric(9, 6),
    verifiee         boolean NOT NULL DEFAULT false,  -- « sûre » au sens de nos modules
    precisions_acces text
);

-- La chose concernée par une demande : appareil, véhicule, commande, logement…
CREATE TABLE objet (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id       bigint REFERENCES contact(id) ON DELETE CASCADE,
    societe_id       bigint REFERENCES societe(id) ON DELETE CASCADE,
    type_liste       text GENERATED ALWAYS AS ('type_objet') STORED,
    type             text NOT NULL,
    identifiant      text,             -- n° de série, immatriculation, n° de commande…
    libelle          text,             -- « poêle à granulés », « Clio IV »
    caracteristiques jsonb NOT NULL DEFAULT '{}',   -- propre au métier, sans colonne
    cree_le          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (type_liste, type) REFERENCES liste_valeur(liste, code)
);

-- Ce qui limite les créneaux : table, pont, salle, véhicule, technicien…
CREATE TABLE ressource (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint REFERENCES site(id),
    personne_id bigint REFERENCES personne(id),   -- quand la ressource est une personne
    type_liste  text GENERATED ALWAYS AS ('type_ressource') STORED,
    type        text NOT NULL,
    nom         text NOT NULL,
    capacite    integer NOT NULL DEFAULT 1 CHECK (capacite > 0),
    actif       boolean NOT NULL DEFAULT true,
    FOREIGN KEY (type_liste, type) REFERENCES liste_valeur(liste, code)
);

-- ---------------------------------------------------------------------
--  D (avant C, car l'appel y renvoie). Demandes
-- ---------------------------------------------------------------------
CREATE TABLE demande (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    contact_id      bigint REFERENCES contact(id) ON DELETE SET NULL,
    adresse_id      bigint REFERENCES adresse(id) ON DELETE SET NULL,
    objet_id        bigint REFERENCES objet(id) ON DELETE SET NULL,
    rattachee_a_id  bigint REFERENCES demande(id) ON DELETE SET NULL,  -- fusion décidée par un humain
    sujet_id        bigint REFERENCES sujet(id),
    site_id         bigint REFERENCES site(id),
    assignee_id     bigint REFERENCES personne(id),
    rappelee_par_id bigint REFERENCES personne(id),
    type_liste      text GENERATED ALWAYS AS ('type_demande') STORED,
    type            text NOT NULL,
    statut_liste    text GENERATED ALWAYS AS ('statut_demande') STORED,
    statut          text NOT NULL DEFAULT 'a_traiter',
    priorite        smallint NOT NULL DEFAULT 2 CHECK (priorite BETWEEN 1 AND 3),
    degre_urgence   text,
    resume          text,
    creee_le        timestamptz NOT NULL DEFAULT now(),
    rappelee_le     timestamptz,
    close_le        timestamptz,
    FOREIGN KEY (type_liste, type)     REFERENCES liste_valeur(liste, code),
    FOREIGN KEY (statut_liste, statut) REFERENCES liste_valeur(liste, code)
);

-- ---------------------------------------------------------------------
--  C. Appels
-- ---------------------------------------------------------------------
CREATE TABLE appel (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dograh_run_id        integer NOT NULL UNIQUE,      -- idempotence du webhook
    version_agent_id     bigint NOT NULL REFERENCES version_agent(id),
    site_id              bigint REFERENCES site(id),
    contact_id           bigint REFERENCES contact(id) ON DELETE SET NULL,
    demande_id           bigint REFERENCES demande(id) ON DELETE SET NULL,
    appel_precedent_id   bigint REFERENCES appel(id) ON DELETE SET NULL,
    canal                text NOT NULL,                -- telephone, navigateur, clavier, simule
    sens                 text NOT NULL DEFAULT 'entrant' CHECK (sens IN ('entrant', 'sortant')),
    numero_appelant      text,
    numero_appele        text,
    debut                timestamptz NOT NULL,
    duree_s              integer,
    issue_liste          text GENERATED ALWAYS AS ('issue_appel') STORED,
    issue                text,
    motif                text,
    degre_urgence        text,
    hors_horaires        boolean,
    synthese             text,
    -- Ce qui ne se rattrape pas (IX.3)
    nb_tours             integer,
    latence_mediane_s    numeric(6, 3),
    pire_silence_s       numeric(6, 3),
    jetons_entree        integer,
    jetons_cache         integer,
    jetons_sortie        integer,
    secondes_transcrites numeric(8, 2),
    caracteres_dits      integer,
    cout_estime          numeric(10, 5),               -- figé à l'écriture
    cout_tarif_du        date,                         -- date du tarif utilisé
    fournisseurs         jsonb NOT NULL DEFAULT '{}',  -- estampille : modèles, voix, transcription
    mesures              jsonb NOT NULL DEFAULT '{}',  -- toute mesure nouvelle, avant d'avoir sa colonne
    recu_le              timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (issue_liste, issue) REFERENCES liste_valeur(liste, code)
);

CREATE TABLE champ_appel (
    appel_id bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    nom      text NOT NULL,
    valeur   text,
    origine  text CHECK (origine IN ('dicte', 'deduit')),
    sure     boolean,
    source   text,                    -- module qui a lu la valeur (commune, rue, lexique…)
    PRIMARY KEY (appel_id, nom)
);

CREATE TABLE tour (
    appel_id  bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    numero    integer NOT NULL,
    etape     text,
    locuteur  text CHECK (locuteur IN ('agent', 'appelant')),
    debut_s   numeric(8, 3),
    silence_s numeric(6, 3),
    latence_s numeric(6, 3),
    interrompu boolean,
    PRIMARY KEY (appel_id, numero)   -- ⛔ jamais le texte du tour
);

CREATE TABLE verbatim (
    appel_id  bigint PRIMARY KEY REFERENCES appel(id) ON DELETE CASCADE,
    contenu   jsonb NOT NULL,          -- tours horodatés
    expire_le timestamptz NOT NULL     -- posé à l'écriture depuis politique_conservation
);

CREATE TABLE transfert (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id       bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    personne_id    bigint REFERENCES personne(id),
    numero_compose text,
    debut          timestamptz,
    decroche       boolean,
    duree_s        integer
);

-- ---------------------------------------------------------------------
--  D. Travail à faire (suite)
-- ---------------------------------------------------------------------
CREATE TABLE rendez_vous (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    demande_id     bigint NOT NULL REFERENCES demande(id) ON DELETE CASCADE,
    intervenant_id bigint REFERENCES personne(id),
    adresse_id     bigint REFERENCES adresse(id) ON DELETE SET NULL,
    debut          timestamptz NOT NULL,
    fin            timestamptz NOT NULL CHECK (fin > debut),
    quantite       integer NOT NULL DEFAULT 1 CHECK (quantite > 0),  -- couverts, places…
    statut_liste   text GENERATED ALWAYS AS ('statut_rdv') STORED,
    statut         text NOT NULL DEFAULT 'pose',
    origine        text NOT NULL CHECK (origine IN ('agent', 'humain')),
    FOREIGN KEY (statut_liste, statut) REFERENCES liste_valeur(liste, code)
);

CREATE TABLE rendez_vous_ressource (
    rendez_vous_id bigint NOT NULL REFERENCES rendez_vous(id) ON DELETE CASCADE,
    ressource_id   bigint NOT NULL REFERENCES ressource(id),
    PRIMARY KEY (rendez_vous_id, ressource_id)
);

CREATE TABLE action (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id     bigint REFERENCES appel(id) ON DELETE SET NULL,
    demande_id   bigint REFERENCES demande(id) ON DELETE SET NULL,
    canal_liste  text GENERATED ALWAYS AS ('canal_action') STORED,
    canal        text NOT NULL,        -- mail, sms, agenda, crm…
    destinataire text,
    statut       text NOT NULL DEFAULT 'en_attente'
                 CHECK (statut IN ('en_attente', 'envoyee', 'delivree', 'echec')),
    envoyee_le   timestamptz,
    delivree_le  timestamptz,          -- « n8n a répondu OK » ≠ « c'est arrivé »
    reessais     smallint NOT NULL DEFAULT 0,
    cout         numeric(10, 5),
    erreur       text,
    FOREIGN KEY (canal_liste, canal) REFERENCES liste_valeur(liste, code)
);

CREATE TABLE lien_externe (
    systeme        text NOT NULL,      -- google_agenda, hubspot…
    id_externe     text NOT NULL,
    objet_type     text NOT NULL,      -- nom de la table liée (contact, demande, objet…)
    objet_id       bigint NOT NULL,
    synchronise_le timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (systeme, id_externe),
    UNIQUE (systeme, objet_type, objet_id)
);

-- ---------------------------------------------------------------------
--  E. Qualité
-- ---------------------------------------------------------------------
CREATE TABLE observation (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id bigint REFERENCES appel(id) ON DELETE SET NULL,  -- le verdict survit à la purge de l'appel
    auteur   text NOT NULL,
    note     smallint CHECK (note BETWEEN 0 AND 5),
    critere  text,
    motif    text,                     -- ⛔ notre note, jamais les mots de l'appelant
    le       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE retour_client (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    le       date NOT NULL,
    qui      text NOT NULL,
    canal    text,
    propos   text NOT NULL,
    gravite  smallint CHECK (gravite BETWEEN 1 AND 3),
    suite    text
);

CREATE TABLE incident (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    debut     timestamptz NOT NULL,
    fin       timestamptz,
    brique    text,
    cause     text,
    correctif text
);

CREATE TABLE incident_appel (
    incident_id bigint NOT NULL REFERENCES incident(id) ON DELETE CASCADE,
    appel_id    bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    PRIMARY KEY (incident_id, appel_id)
);

-- ---------------------------------------------------------------------
--  Dernière activité d'un contact (point de départ des 3 ans CNIL), tenue par la base
-- ---------------------------------------------------------------------
CREATE FUNCTION toucher_contact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.contact_id IS NOT NULL THEN
        UPDATE mark.contact SET derniere_activite = greatest(derniere_activite, now())
        WHERE id = NEW.contact_id;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER appel_touche_contact   AFTER INSERT OR UPDATE OF contact_id ON appel
    FOR EACH ROW EXECUTE FUNCTION toucher_contact();
CREATE TRIGGER demande_touche_contact AFTER INSERT OR UPDATE OF contact_id ON demande
    FOR EACH ROW EXECUTE FUNCTION toucher_contact();

-- ---------------------------------------------------------------------
--  Journal des écritures faites depuis l'interface (qui, quoi, quand)
-- ---------------------------------------------------------------------
CREATE FUNCTION journaliser_demande() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
BEGIN
    INSERT INTO journal_modif (table_nom, ligne_id, champ, avant, apres, auteur)
    VALUES ('demande', NEW.id::text, 'rappel_ou_rattachement',
            jsonb_build_object('rappelee_le', OLD.rappelee_le, 'rappelee_par_id', OLD.rappelee_par_id,
                               'rattachee_a_id', OLD.rattachee_a_id),
            jsonb_build_object('rappelee_le', NEW.rappelee_le, 'rappelee_par_id', NEW.rappelee_par_id,
                               'rattachee_a_id', NEW.rattachee_a_id),
            session_user);
    RETURN NEW;
END $$;

CREATE TRIGGER demande_journal AFTER UPDATE OF rappelee_le, rappelee_par_id, rattachee_a_id ON demande
    FOR EACH ROW WHEN (OLD IS DISTINCT FROM NEW) EXECUTE FUNCTION journaliser_demande();

-- ---------------------------------------------------------------------
--  Index (les lectures du tableau de bord et de n8n)
-- ---------------------------------------------------------------------
CREATE INDEX appel_debut_idx        ON appel (debut DESC);
CREATE INDEX appel_numero_idx       ON appel (numero_appelant, debut DESC);  -- rappel dans l'heure
CREATE INDEX appel_demande_idx      ON appel (demande_id);
CREATE INDEX appel_contact_idx      ON appel (contact_id);
CREATE INDEX demande_statut_idx     ON demande (statut, creee_le DESC);
CREATE INDEX demande_contact_idx    ON demande (contact_id);
CREATE INDEX rdv_debut_idx          ON rendez_vous (debut);
CREATE INDEX action_statut_idx      ON action (statut) WHERE statut <> 'delivree';
CREATE INDEX verbatim_expire_idx    ON verbatim (expire_le);
CREATE INDEX lien_objet_idx         ON lien_externe (objet_type, objet_id);
CREATE INDEX adresse_insee_idx      ON adresse (code_insee);
CREATE INDEX objet_identifiant_idx  ON objet (type, identifiant);
CREATE INDEX contact_activite_idx   ON contact (derniere_activite);
CREATE INDEX demande_ouverte_idx    ON demande (contact_id) WHERE close_le IS NULL;

-- ---------------------------------------------------------------------
--  Vues pour l'interface (Metabase aujourd'hui, portail demain)
-- ---------------------------------------------------------------------
-- Le cahier d'appels : 90 jours, numéro masqué (IX.6, parades 3 et 4)
CREATE VIEW v_cahier_appels AS
SELECT a.id, a.debut, s.nom AS site, a.issue, a.motif, a.degre_urgence,
       a.duree_s, a.hors_horaires, a.synthese,
       left(a.numero_appelant, 6) || '••••' || right(a.numero_appelant, 2) AS numero_masque,
       c.nom AS contact_nom, d.id AS demande_id, d.statut AS demande_statut
FROM appel a
LEFT JOIN site s    ON s.id = a.site_id
LEFT JOIN contact c ON c.id = a.contact_id
LEFT JOIN demande d ON d.id = a.demande_id
WHERE a.debut > now() - interval '90 days';

-- Ce qui attend encore un rappel
-- Avec l'INDICE : une autre demande ouverte venue du même numéro exact.
-- La machine signale, l'humain tranche (rattachee_a_id). Aucune fusion automatique.
CREATE VIEW v_a_rappeler AS
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
                   ORDER BY d2.creee_le DESC LIMIT 1) autre ON true
WHERE d.rappelee_le IS NULL AND d.close_le IS NULL AND d.rattachee_a_id IS NULL
ORDER BY d.priorite, d.creee_le;

-- Les compteurs du jour (IX.5), sans donnée personnelle
CREATE MATERIALIZED VIEW kpi_jour AS
SELECT (a.debut AT TIME ZONE 'Europe/Paris')::date AS jour,
       a.site_id,
       count(*)                                              AS appels,
       count(*) FILTER (WHERE a.hors_horaires)               AS hors_horaires,
       count(*) FILTER (WHERE a.duree_s < 15)                AS moins_15s,
       count(*) FILTER (WHERE a.duree_s > 180)               AS plus_3min,
       count(*) FILTER (WHERE a.motif IS NULL OR a.issue = 'autre') AS hors_cadre,
       count(*) FILTER (WHERE a.debut - p.debut < interval '1 hour') AS rappels_dans_l_heure,
       count(*) FILTER (WHERE EXISTS (SELECT 1 FROM transfert tr
                                      WHERE tr.appel_id = a.id AND tr.decroche IS FALSE))
                                                             AS transferts_non_decroches,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY a.latence_mediane_s) AS latence_mediane_s,
       sum(a.cout_estime)                                    AS cout_estime
FROM appel a
LEFT JOIN appel p ON p.id = a.appel_precedent_id
GROUP BY 1, 2;

CREATE UNIQUE INDEX kpi_jour_idx ON kpi_jour (jour, site_id) NULLS NOT DISTINCT;

-- ---------------------------------------------------------------------
--  Purge, table par table (IX.1, question 58.f)
-- ---------------------------------------------------------------------
CREATE FUNCTION purger() RETURNS TABLE (table_nom text, lignes bigint)
LANGUAGE plpgsql AS $$
DECLARE
    p record;
    n bigint;
BEGIN
    DELETE FROM verbatim WHERE expire_le < now();
    GET DIAGNOSTICS n = ROW_COUNT;
    table_nom := 'verbatim'; lignes := n; RETURN NEXT;

    FOR p IN SELECT * FROM politique_conservation WHERE politique_conservation.table_nom <> 'verbatim' LOOP
        EXECUTE format('DELETE FROM mark.%I WHERE %I < now() - $1', p.table_nom, p.colonne_date)
            USING p.duree;
        GET DIAGNOSTICS n = ROW_COUNT;
        table_nom := p.table_nom; lignes := n; RETURN NEXT;
    END LOOP;
END $$;

-- ---------------------------------------------------------------------
--  Rôles : n8n écrit, l'interface lit (et n'écrit que « rappelé »)
-- ---------------------------------------------------------------------
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mark_ecriture') THEN
        CREATE ROLE mark_ecriture NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mark_interface') THEN
        CREATE ROLE mark_interface NOLOGIN;
    END IF;
END $$;

GRANT USAGE ON SCHEMA mark TO mark_ecriture, mark_interface;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA mark TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;
GRANT SELECT ON v_cahier_appels, v_a_rappeler, kpi_jour, site, personne, sujet TO mark_interface;
GRANT SELECT, UPDATE (rappelee_le, rappelee_par_id, rattachee_a_id) ON demande TO mark_interface;
-- ⛔ Pas de SELECT direct sur appel, contact, telephone, verbatim pour l'interface.

-- ---------------------------------------------------------------------
--  Valeurs de départ (communes à tous les clients)
-- ---------------------------------------------------------------------
INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES
    ('statut_demande', 'a_traiter', 'À traiter', 1),
    ('statut_demande', 'en_cours',  'En cours',  2),
    ('statut_demande', 'rappelee',  'Rappelée',  3),
    ('statut_demande', 'close',     'Close',     4),
    ('nature_contact', 'particulier',   'Particulier',   1),
    ('nature_contact', 'professionnel', 'Professionnel', 2),
    ('statut_rdv',     'propose', 'Proposé', 1),
    ('statut_rdv',     'pose',    'Posé',    2),
    ('statut_rdv',     'annule',  'Annulé',  3),
    ('statut_rdv',     'fait',    'Fait',    4),
    ('canal_action',   'mail',    'Mail',    1),
    ('canal_action',   'sms',     'SMS',     2),
    ('canal_action',   'agenda',  'Agenda',  3),
    ('canal_action',   'crm',     'CRM',     4),
    ('type_objet',     'autre',   'Autre',   9),
    ('type_ressource', 'personne','Personne',1),
    ('type_ressource', 'autre',   'Autre',   9),
    ('type_demande',   'devis',      'Devis',             1),
    ('type_demande',   'sav',        'Panne ou SAV',      2),
    ('type_demande',   'entretien',  'Entretien',         3),
    ('type_demande',   'facture',    'Facture',           4),
    ('type_demande',   'suivi',      'Suivi de commande', 5),
    ('type_demande',   'information','Information',       6),
    ('type_demande',   'autre',      'Autre',             9),
    ('issue_appel',    'user_hangup','Raccroché par l''appelant', 9),
    ('issue_appel',    'autre',      'Autre',             10);
-- Les valeurs d'un métier (issues de l'agent, types d'objet : appareil, véhicule, commande…,
-- ressources : table, pont…) s'ajoutent à l'installation, sans migration.

INSERT INTO politique_conservation (table_nom, duree, colonne_date, decidee_le, source) VALUES
    ('appel',         interval '12 months', 'debut',    '2026-09-03', 'reference/11 IX.1'),
    ('demande',       interval '12 months', 'creee_le', '2026-09-03', 'reference/11 IX.1'),
    ('contact',       interval '3 years',   'derniere_activite', '2026-10-06', 'CNIL, référentiel gestion commerciale : 3 ans après le dernier contact ; défaut validé par le client'),
    ('action',        interval '12 months', 'envoyee_le','2026-09-03', 'reference/11 IX.1');
-- verbatim : durée NON TRANCHÉE (question 58.b). expire_le est posé par n8n à l'écriture.

INSERT INTO schema_version (version, description) VALUES
    (1, 'Schéma initial (06/10/2026) : objet, ressource, société, rattachement, dernière activité');

COMMIT;
