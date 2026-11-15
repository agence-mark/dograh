-- =====================================================================
--  025 : la carte au format commun (chantier module-restauration, lot 1, SA-1).
--  Additive seulement : des tables neuves et deux fonctions d'aide, rien d'existant n'est modifié.
--
--  Un établissement = une ligne de ``site`` (l'identifiant du contrat s'appelle ``etablissement_id``).
--  Portée d'un objet de la carte (contrat § 2) :
--    - ``enseigne``      : commune à tous les établissements de la base (``site_id`` vide) ;
--    - ``etablissement`` : propre à un établissement ;
--    - ``exception``     : propre à un établissement ET de même ``ref`` qu'un objet d'enseigne : il le
--                          remplace pour cet établissement (ou le masque : ``masque``).
--  ``ref`` = l'identifiant de l'objet dans le format commun (stable d'un import à l'autre).
--  Une même ``ref`` existe donc au plus une fois par établissement et au plus une fois pour l'enseigne.
--
--  Les surcouches (synonymes et leur état « à relire », étoile, lexique, phrase) vivent dans une table
--  À PART, rattachées par ``ref`` : un réimport de la carte ne les écrit jamais (W31).
--
--  Droits : ``<base>_ecriture`` (le fork) lit et écrit tout ; ``<base>_portail`` lit ce que ses
--  établissements voient (la carte d'enseigne dès qu'il voit un lieu) et écrit la carte quand le portail
--  en est le maître (contrat portail, § 1) ; PUBLIC, l'interface et les salariés : rien.
--  La fonction ``resto_droits`` pose RLS + GRANT de chaque table du module (025 à 028) : une politique
--  par rôle, ``REVOKE ... FROM PUBLIC``.
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  0. Les deux fonctions d'aide du module.
-- ---------------------------------------------------------------------
-- Pose les droits d'une table du module. ``p_portail`` : 'lecture' | 'ecriture' | 'aucun'.
-- ``p_enseigne`` : la colonne site_id peut être vide (ligne d'enseigne) : le portail la voit dès qu'il voit un lieu.
CREATE OR REPLACE FUNCTION resto_droits(cible text, p_portail text, p_enseigne boolean DEFAULT false) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    base text := current_database();
    portail text := base || '_portail';
    voit text := CASE WHEN p_enseigne THEN 'portail_voit_lieu_ou_entreprise' ELSE 'portail_voit_site' END;
    sequence text;
BEGIN
    IF p_portail NOT IN ('lecture', 'ecriture', 'aucun') THEN
        RAISE EXCEPTION 'resto_droits : % inconnu', p_portail;
    END IF;
    EXECUTE format('REVOKE ALL ON %I FROM PUBLIC', cible);
    EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO mark_ecriture', cible);
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', cible);
    -- Une politique par rôle : tout ce qui n'est pas le portail (le fork) ...
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', cible || '_autres', cible);
    EXECUTE format('CREATE POLICY %I ON %I USING ((SELECT NOT est_du_portail(current_user)))', cible || '_autres', cible);
    -- ... et le portail, établissement par établissement.
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I', cible || '_portail', cible);
    IF p_portail = 'lecture' THEN
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (%s(site_id, current_user))', cible || '_portail', cible, voit);
        EXECUTE format('GRANT SELECT ON %I TO %I', cible, portail);
    ELSIF p_portail = 'ecriture' THEN
        EXECUTE format('CREATE POLICY %I ON %I USING (%s(site_id, current_user)) WITH CHECK (%s(site_id, current_user))',
                       cible || '_portail', cible, voit, voit);
        EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON %I TO %I', cible, portail);
    END IF;
    -- Les séquences d'identité des colonnes ``id`` : le fork toujours, le portail s'il écrit.
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = cible AND column_name = 'id') THEN
        sequence := pg_get_serial_sequence(format('%I.%I', 'mark', cible), 'id');
    END IF;
    IF sequence IS NOT NULL THEN
        EXECUTE format('GRANT USAGE ON SEQUENCE %s TO mark_ecriture', sequence);
        IF p_portail = 'ecriture' THEN
            EXECUTE format('GRANT USAGE ON SEQUENCE %s TO %I', sequence, portail);
        END IF;
    END IF;
END $$;

-- ``maj_le`` suit l'écriture quand l'écrivain ne l'a pas posé lui-même (le portail écrit en direct ;
-- le fork pose la valeur de la source d'heure de l'organisation, jamais écrasée ici).
CREATE OR REPLACE FUNCTION resto_maj_le() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.maj_le IS NOT DISTINCT FROM OLD.maj_le THEN
        NEW.maj_le := now();
    END IF;
    RETURN NEW;
END $$;

-- ---------------------------------------------------------------------
--  1. La carte.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resto_categorie (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id    bigint REFERENCES site(id) ON DELETE CASCADE,
    portee     text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref        text NOT NULL CHECK (btrim(ref) <> ''),
    nom        text NOT NULL CHECK (btrim(nom) <> ''),
    parent_ref text,
    ordre      integer NOT NULL DEFAULT 0,
    masque     boolean NOT NULL DEFAULT false,
    source     text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_categorie_portee CHECK ((portee = 'enseigne') = (site_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_categorie_ref_idx ON resto_categorie (site_id, ref) NULLS NOT DISTINCT;

CREATE TABLE IF NOT EXISTS resto_produit (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id       bigint REFERENCES site(id) ON DELETE CASCADE,
    portee        text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref           text NOT NULL CHECK (btrim(ref) <> ''),
    nom           text NOT NULL CHECK (btrim(nom) <> ''),
    description   text,
    categorie_ref text,
    -- [{"nom": ..., "retirable": bool}] ; ``allergenes`` : NULL = inconnu, '{}' = aucun, sinon codes parmi les 14.
    ingredients   jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(ingredients) = 'array'),
    allergenes    text[] CHECK (allergenes IS NULL OR allergenes <@ ARRAY[
                      'gluten', 'crustaces', 'oeufs', 'poissons', 'arachides', 'soja', 'lait', 'fruits_a_coque',
                      'celeri', 'moutarde', 'sesame', 'sulfites', 'lupin', 'mollusques']::text[]),
    origine       text,
    -- {"sur_place": 10000, "emporter": 10000, "livraison": 10000} : millièmes de pour cent.
    tva_par_mode  jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(tva_par_mode) = 'object'),
    groupes_refs  text[] NOT NULL DEFAULT '{}',
    ordre         integer NOT NULL DEFAULT 0,
    masque        boolean NOT NULL DEFAULT false,
    source        text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_produit_portee CHECK ((portee = 'enseigne') = (site_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_produit_ref_idx ON resto_produit (site_id, ref) NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS resto_produit_categorie_idx ON resto_produit (site_id, categorie_ref);

-- La taille : le code de caisse est NULL tant qu'il n'est pas connu ; sans lui, la déclinaison n'est pas vendable.
CREATE TABLE IF NOT EXISTS resto_declinaison (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id       bigint REFERENCES site(id) ON DELETE CASCADE,
    portee        text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref           text NOT NULL CHECK (btrim(ref) <> ''),
    produit_ref   text NOT NULL,
    nom           text NOT NULL CHECK (btrim(nom) <> ''),
    code_caisse   text CHECK (code_caisse IS NULL OR btrim(code_caisse) <> ''),
    prix          integer NOT NULL CHECK (prix >= 0),
    -- {"sur_place": 1190, "emporter": 1090, "livraison": 1190} : centimes, par mode, quand il diffère.
    prix_par_mode jsonb CHECK (prix_par_mode IS NULL OR jsonb_typeof(prix_par_mode) = 'object'),
    -- {"jours": [1..7], "heures": [["11:00","14:30"]], "dates": {"du": ..., "au": ...}} ; NULL = toujours.
    disponibilite jsonb CHECK (disponibilite IS NULL OR jsonb_typeof(disponibilite) = 'object'),
    ordre         integer NOT NULL DEFAULT 0,
    masque        boolean NOT NULL DEFAULT false,
    source        text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_declinaison_portee CHECK ((portee = 'enseigne') = (site_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_declinaison_ref_idx ON resto_declinaison (site_id, ref) NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS resto_declinaison_produit_idx ON resto_declinaison (site_id, produit_ref);
CREATE INDEX IF NOT EXISTS resto_declinaison_code_idx ON resto_declinaison (site_id, code_caisse);

CREATE TABLE IF NOT EXISTS resto_groupe_choix (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id           bigint REFERENCES site(id) ON DELETE CASCADE,
    portee            text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref               text NOT NULL CHECK (btrim(ref) <> ''),
    nom               text NOT NULL CHECK (btrim(nom) <> ''),
    min               integer NOT NULL DEFAULT 0 CHECK (min >= 0),
    max               integer NOT NULL DEFAULT 1 CHECK (max >= 0),
    max_par_option    integer NOT NULL DEFAULT 1 CHECK (max_par_option >= 0),
    defaut_refs       text[] NOT NULL DEFAULT '{}',
    parent_option_ref text,                       -- imbrication : ce groupe s'ouvre sous cette option
    role              text NOT NULL DEFAULT 'choix' CHECK (role IN ('choix', 'supplement', 'moities')),
    ordre             integer NOT NULL DEFAULT 0,
    masque            boolean NOT NULL DEFAULT false,
    source            text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_groupe_choix_portee CHECK ((portee = 'enseigne') = (site_id IS NULL)),
    CONSTRAINT resto_groupe_choix_bornes CHECK (max >= min)
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_groupe_choix_ref_idx ON resto_groupe_choix (site_id, ref) NULLS NOT DISTINCT;

CREATE TABLE IF NOT EXISTS resto_option (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint REFERENCES site(id) ON DELETE CASCADE,
    portee      text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref         text NOT NULL CHECK (btrim(ref) <> ''),
    groupe_ref  text NOT NULL,
    nom         text NOT NULL CHECK (btrim(nom) <> ''),
    code_caisse text CHECK (code_caisse IS NULL OR btrim(code_caisse) <> ''),
    prix        integer NOT NULL DEFAULT 0 CHECK (prix >= 0),
    par_defaut  boolean NOT NULL DEFAULT false,
    retirable   boolean NOT NULL DEFAULT false,
    ordre       integer NOT NULL DEFAULT 0,
    masque      boolean NOT NULL DEFAULT false,
    source      text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_option_portee CHECK ((portee = 'enseigne') = (site_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_option_ref_idx ON resto_option (site_id, ref) NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS resto_option_groupe_idx ON resto_option (site_id, groupe_ref);
CREATE INDEX IF NOT EXISTS resto_option_code_idx ON resto_option (site_id, code_caisse);

-- Une formule : un produit vendu à un prix, dont chaque ligne est un choix (min = max). ``lignes`` garde la
-- forme du format commun : [{"nom", "codes"|"categories", "effet", "prix"?}].
CREATE TABLE IF NOT EXISTS resto_formule (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id       bigint REFERENCES site(id) ON DELETE CASCADE,
    portee        text NOT NULL DEFAULT 'etablissement' CHECK (portee IN ('enseigne', 'etablissement', 'exception')),
    ref           text NOT NULL CHECK (btrim(ref) <> ''),
    nom           text NOT NULL CHECK (btrim(nom) <> ''),
    code_caisse   text CHECK (code_caisse IS NULL OR btrim(code_caisse) <> ''),
    prix          integer NOT NULL CHECK (prix >= 0),
    categorie_ref text,
    lignes        jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(lignes) = 'array'),
    supplement    integer CHECK (supplement IS NULL OR supplement >= 0),
    masque        boolean NOT NULL DEFAULT false,
    source        text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_formule_portee CHECK ((portee = 'enseigne') = (site_id IS NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_formule_ref_idx ON resto_formule (site_id, ref) NULLS NOT DISTINCT;

-- Les surcouches : ce que .mark ou le restaurant ajoute à la carte, rattaché par ``ref``, jamais écrit par un réimport.
CREATE TABLE IF NOT EXISTS resto_surcouche (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id           bigint REFERENCES site(id) ON DELETE CASCADE,
    objet             text NOT NULL CHECK (objet IN ('categorie', 'produit', 'declinaison', 'option', 'formule')),
    ref               text NOT NULL CHECK (btrim(ref) <> ''),
    synonymes         text[] NOT NULL DEFAULT '{}',
    synonymes_a_relire boolean NOT NULL DEFAULT false,   -- proposés à l'import, actifs après relecture (T-14)
    etoile            boolean NOT NULL DEFAULT false,
    lexique           text[] NOT NULL DEFAULT '{}',
    phrase            text,
    maj_le            timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_surcouche_ref_idx ON resto_surcouche (site_id, objet, ref) NULLS NOT DISTINCT;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['resto_categorie', 'resto_produit', 'resto_declinaison', 'resto_groupe_choix',
                             'resto_option', 'resto_formule', 'resto_surcouche'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_maj_le', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION resto_maj_le()', t || '_maj_le', t);
        -- La carte (enseigne comprise) est lue par le portail dès qu'il voit un lieu, et écrite par lui
        -- quand il en est le maître.
        PERFORM resto_droits(t, 'ecriture', true);
    END LOOP;
END $$;

INSERT INTO schema_version (version, description) VALUES
    (25, 'Module Restauration : la carte au format commun (catégories, produits, déclinaisons, groupes de choix, options, formules), portées enseigne/établissement/exception, surcouches à part ; fonctions resto_droits et resto_maj_le')
ON CONFLICT (version) DO NOTHING;
