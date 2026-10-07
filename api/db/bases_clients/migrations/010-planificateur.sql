-- =====================================================================
--  010 : le planificateur de rendez-vous (chantier l-agent-collegue, L5,
--  P2, P3, P7). Additive seulement.
--
--  - type_rendez_vous : les types qu'un appelant peut prendre (code,
--    libellé, durée, sujet qui désigne qui sait le faire, marges avant et
--    après). Une ligne sans établissement vaut pour toute l'organisation ;
--    une ligne du même code avec un établissement la remplace pour lui.
--  - reglage_planificateur : les règles (nombre de créneaux, délai, horizon,
--    plages, zone, trajets, répartition, repli, jours fériés). Une ligne
--    sans établissement = l'organisation ; une ligne par établissement ne
--    porte que ce qu'il surcharge (vide = hérité). Les défauts communs sont
--    posés par le code, jamais ici.
--  - attribution : chaque rendez-vous posé par l'agent, à qui et pourquoi
--    (mode de répartition, rang) : la preuve d'équité pour le client.
--  - rendez_vous.type_code : le type du rendez-vous posé.
--  Modifiables à l'écran, à la main, et plus tard par le client dans
--  Metabase : journalisés et notifiés comme le reste du référentiel.
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS type_rendez_vous (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code             text NOT NULL CHECK (code ~ '^[a-z][a-z0-9_]{1,39}$'),
    site_id          bigint REFERENCES site(id) ON DELETE CASCADE,   -- vide = toute l'organisation
    libelle          text NOT NULL CHECK (char_length(libelle) BETWEEN 1 AND 100),
    duree_min        integer NOT NULL CHECK (duree_min BETWEEN 5 AND 1440),
    sujet_id         bigint REFERENCES sujet(id),                    -- qui sait le faire ; vide = toute l'équipe
    marge_avant_min  integer NOT NULL DEFAULT 0 CHECK (marge_avant_min BETWEEN 0 AND 480),
    marge_apres_min  integer NOT NULL DEFAULT 0 CHECK (marge_apres_min BETWEEN 0 AND 480),
    actif            boolean NOT NULL DEFAULT true,
    ordre            integer NOT NULL DEFAULT 0
);
CREATE UNIQUE INDEX IF NOT EXISTS type_rendez_vous_code_site_idx
    ON type_rendez_vous (code, coalesce(site_id, 0));

CREATE TABLE IF NOT EXISTS reglage_planificateur (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id             bigint REFERENCES site(id) ON DELETE CASCADE,  -- vide = l'organisation
    nombre_creneaux     smallint CHECK (nombre_creneaux BETWEEN 1 AND 6),
    delai_minimal_h     numeric(6, 2) CHECK (delai_minimal_h BETWEEN 0 AND 720),
    horizon_jours       smallint CHECK (horizon_jours BETWEEN 1 AND 90),
    pas_min             smallint CHECK (pas_min BETWEEN 5 AND 240),
    plages              text CHECK (plages IS NULL OR char_length(plages) <= 4000),  -- format lisible des horaires ; vide = horaires de l'établissement
    zone_rayon_km       numeric(6, 1) CHECK (zone_rayon_km BETWEEN 1 AND 1000),
    zone_communes       text[],                                        -- codes INSEE
    trajets_comptes     boolean,
    coefficient_trajet  numeric(4, 2) CHECK (coefficient_trajet BETWEEN 1 AND 3),
    vitesse_kmh         numeric(5, 1) CHECK (vitesse_kmh BETWEEN 5 AND 130),
    repartition         text CHECK (repartition IN ('premier_libre', 'tour_de_role', 'charge', 'zone')),
    repli               text CHECK (repli IN ('humain_puis_rappel', 'toujours_rappel')),
    personne_visible    boolean,
    jours_feries        text CHECK (jours_feries IN ('metropole', 'alsace_moselle'))
);
CREATE UNIQUE INDEX IF NOT EXISTS reglage_planificateur_site_idx
    ON reglage_planificateur (coalesce(site_id, 0));

CREATE TABLE IF NOT EXISTS attribution (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id        bigint REFERENCES appel(id) ON DELETE SET NULL,
    rendez_vous_id  bigint NOT NULL UNIQUE REFERENCES rendez_vous(id) ON DELETE CASCADE,
    personne_id     bigint REFERENCES personne(id),
    type_code       text,
    mode            text NOT NULL CHECK (mode IN ('premier_libre', 'tour_de_role', 'charge', 'zone')),
    rang            smallint,                  -- sa place dans l'ordre de répartition (1 = celui dont c'était le tour)
    motif           text CHECK (motif IS NULL OR char_length(motif) <= 200),
    le              timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS attribution_type_idx ON attribution (type_code, le DESC);

ALTER TABLE rendez_vous ADD COLUMN IF NOT EXISTS type_code text;

GRANT SELECT, INSERT, UPDATE, DELETE ON type_rendez_vous, reglage_planificateur, attribution TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;
GRANT SELECT ON type_rendez_vous, reglage_planificateur TO mark_interface;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['type_rendez_vous', 'reglage_planificateur'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_referentiel', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel()', t || '_referentiel', t);
    END LOOP;
END $$;

INSERT INTO schema_version (version, description) VALUES
    (10, 'Planificateur : types de rendez-vous, règles avec héritage à l''établissement, attributions tracées');
