-- =====================================================================
--  027 : clients, remises, envois, réglages du module (module Restauration, lot 1).
--  Additive seulement. Voir la 025 pour la règle des droits.
--
--  - resto_client : la fiche d'un client d'un établissement (numéro E.164, prénom, adresses, consignes
--    habituelles, dernière commande). Aucune allergie ici (T-16 : l'allergie ne vit que dans la commande).
--    Durée de conservation réglable par établissement (T-15) dans resto_reglage.
--  - resto_remise : les mécanismes de remise du contrat (la liste des mécanismes se vérifie à la couche, lot 7).
--    Une remise vient en ``brouillon`` : elle ne s'applique qu'une fois ``active`` (éteint par défaut).
--  - resto_envoi : textes et déclencheurs des envois (SMS, mail) ; ``actif`` éteint par défaut.
--  Le portail écrit ces quatre tables (directe, contrat portail § 1).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS resto_client (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id              bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    telephone            text NOT NULL CHECK (telephone ~ '^\+[1-9][0-9]{6,14}$'),
    prenom               text,
    adresses             jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(adresses) = 'array'),
    consignes            jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(consignes) = 'array'),   -- [{"texte","le"}]
    derniere_commande_id uuid REFERENCES resto_commande(numero) ON DELETE SET NULL,
    derniere_commande_le timestamptz,
    nb_commandes         integer NOT NULL DEFAULT 0 CHECK (nb_commandes >= 0),
    cree_le              timestamptz NOT NULL DEFAULT now(),
    maj_le               timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_client_telephone_idx ON resto_client (site_id, telephone);
CREATE INDEX IF NOT EXISTS resto_client_activite_idx ON resto_client (site_id, derniere_commande_le);

CREATE TABLE IF NOT EXISTS resto_remise (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    ref         text,
    nom         text NOT NULL CHECK (btrim(nom) <> ''),
    mecanisme   text NOT NULL CHECK (btrim(mecanisme) <> ''),
    declencheur jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(declencheur) = 'object'),
    effet       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(effet) = 'object'),
    perimetre   jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(perimetre) = 'object'),
    cumul       text NOT NULL DEFAULT 'exclusive' CHECK (cumul IN ('exclusive', 'cumulable')),
    limite      jsonb CHECK (limite IS NULL OR jsonb_typeof(limite) = 'object'),
    phrase      text,
    moment      jsonb CHECK (moment IS NULL OR jsonb_typeof(moment) = 'object'),
    debut       timestamptz,
    fin         timestamptz,
    etat        text NOT NULL DEFAULT 'brouillon' CHECK (etat IN ('brouillon', 'active', 'suspendue', 'terminee')),
    ref_caisse  text,
    source      text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_remise_dates CHECK (fin IS NULL OR debut IS NULL OR fin > debut)
);
CREATE INDEX IF NOT EXISTS resto_remise_site_idx ON resto_remise (site_id, etat);

CREATE TABLE IF NOT EXISTS resto_envoi (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    type        text NOT NULL CHECK (type IN ('sms', 'mail')),
    declencheur text NOT NULL CHECK (btrim(declencheur) <> ''),
    texte       text NOT NULL CHECK (btrim(texte) <> ''),
    actif       boolean NOT NULL DEFAULT false,
    maj_le      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_envoi_site_idx ON resto_envoi (site_id, declencheur);

-- Réglages propres au module, un jeu par établissement.
CREATE TABLE IF NOT EXISTS resto_reglage (
    site_id                 bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    -- T-15 : durée réglable ; le maximum (36 mois, référentiel CNIL de la gestion commerciale) est à valider par un juriste.
    conservation_client_mois integer NOT NULL DEFAULT 12 CHECK (conservation_client_mois BETWEEN 1 AND 36),
    prefixe_numero_court     text NOT NULL DEFAULT '' CHECK (prefixe_numero_court ~ '^[A-Z0-9]{0,4}$'),
    maj_le                   timestamptz NOT NULL DEFAULT now()
);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['resto_client', 'resto_remise', 'resto_envoi', 'resto_reglage'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_maj_le', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION resto_maj_le()', t || '_maj_le', t);
        PERFORM resto_droits(t, 'ecriture');
    END LOOP;
END $$;

INSERT INTO schema_version (version, description) VALUES
    (27, 'Module Restauration : clients et consignes, remises, envois (éteints par défaut), réglages du module (conservation de la fiche client, préfixe du numéro court)')
ON CONFLICT (version) DO NOTHING;
