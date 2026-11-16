-- =====================================================================
--  026 : commandes, ruptures, état de la caisse, réglages par type, zones (module Restauration, lot 1).
--  Additive seulement. Voir la 025 pour la règle des droits (``resto_droits``) et le vocabulaire.
--
--  - Les montants sont en centimes (entiers), jamais de flottant.
--  - ``resto_commande.numero`` : UUID unique au monde ; ``numero_court`` : préfixe réglable + compteur du jour.
--  - ``statut`` suit le chemin fermé du contrat (la couche d'accès le vérifie ; un CHECK ferme la liste).
--  - ``cle_doublon`` : même appel + même panier = même commande (verrou anti-doublon), unique par établissement.
--  - Le portail LIT les commandes, les ruptures et l'état de la caisse ; il les change par une route du fork
--    (contrat portail § 1). Il ÉCRIT les réglages par type et les zones (directe).
-- =====================================================================
SET search_path = mark;

-- Ruptures : une ligne par code de caisse (la dernière gagne) ; ``fin`` vide = jusqu'à nouvel ordre.
CREATE TABLE IF NOT EXISTS resto_rupture (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    code_caisse text NOT NULL CHECK (btrim(code_caisse) <> ''),
    disponible  boolean NOT NULL DEFAULT false,
    stock       integer CHECK (stock IS NULL OR stock >= 0),
    debut       timestamptz NOT NULL DEFAULT now(),
    fin         timestamptz,
    source      text NOT NULL DEFAULT 'portail' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_rupture_fin CHECK (fin IS NULL OR fin > debut)
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_rupture_code_idx ON resto_rupture (site_id, code_caisse);

-- L'état que la caisse porte (une ligne par établissement dont la caisse le dit).
CREATE TABLE IF NOT EXISTS resto_etat_caisse (
    site_id           bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    mode              text NOT NULL DEFAULT 'normal' CHECK (mode IN ('normal', 'deborde', 'pause')),
    minutes_en_plus   integer NOT NULL DEFAULT 0 CHECK (minutes_en_plus >= 0),
    reprise           timestamptz,
    motif             text,
    temps_preparation integer CHECK (temps_preparation IS NULL OR temps_preparation >= 0),
    horaires          jsonb,
    fuseau            text NOT NULL DEFAULT 'Europe/Paris',
    source            text NOT NULL DEFAULT 'caisse' CHECK (source IN ('caisse', 'portail', 'mark', 'agent', 'import')),
    maj_le            timestamptz NOT NULL DEFAULT now()
);

-- Réglages de commande par type : planifiée éteinte par défaut, annonce en durée par défaut.
CREATE TABLE IF NOT EXISTS resto_reglage_type (
    site_id            bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    type               text NOT NULL CHECK (type IN ('emporter', 'livraison', 'sur_place', 'reservation')),
    ouvert             boolean NOT NULL DEFAULT true,
    pause_jusqu_a      timestamptz,
    fin_par_jour       jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(fin_par_jour) = 'object'),   -- {"1": "22:00"}
    planifiee_permise  boolean NOT NULL DEFAULT false,
    delai_minimal      integer NOT NULL DEFAULT 0 CHECK (delai_minimal >= 0),
    jours_a_l_avance   integer NOT NULL DEFAULT 0 CHECK (jours_a_l_avance >= 0),
    -- Minutes entières ; la livraison est portée par la zone (E-42), sa valeur ici reste vide.
    delai_annonce      integer CHECK (delai_annonce IS NULL OR delai_annonce >= 0),
    minutes_ajoutees   integer NOT NULL DEFAULT 0 CHECK (minutes_ajoutees >= 0),
    ajout_jusqu_a      timestamptz,
    annonce            text NOT NULL DEFAULT 'duree' CHECK (annonce IN ('heure_fixe', 'tranche', 'duree')),
    capacite_quart_heure integer CHECK (capacite_quart_heure IS NULL OR capacite_quart_heure >= 0),
    maj_le             timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (site_id, type)
);

CREATE TABLE IF NOT EXISTS resto_zone (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id      bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    nom          text NOT NULL CHECK (btrim(nom) <> ''),
    forme        text NOT NULL CHECK (forme IN ('communes', 'rayon')),
    communes     text[] NOT NULL DEFAULT '{}',
    rayon_km     numeric(6, 2) CHECK (rayon_km IS NULL OR rayon_km > 0),
    exclues      text[] NOT NULL DEFAULT '{}',
    frais        integer NOT NULL DEFAULT 0 CHECK (frais >= 0),
    minimum      integer NOT NULL DEFAULT 0 CHECK (minimum >= 0),
    gratuite_des integer CHECK (gratuite_des IS NULL OR gratuite_des >= 0),
    delai        integer NOT NULL DEFAULT 0 CHECK (delai >= 0),    -- minutes entières (E-42)
    couleur      smallint NOT NULL DEFAULT 1 CHECK (couleur BETWEEN 1 AND 5),
    ordre        integer NOT NULL DEFAULT 0,
    maj_le       timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_zone_forme CHECK ((forme = 'rayon') = (rayon_km IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS resto_zone_site_idx ON resto_zone (site_id, ordre);

CREATE TABLE IF NOT EXISTS resto_commande (
    numero          uuid PRIMARY KEY,
    numero_court    text NOT NULL,
    site_id         bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    mode            text NOT NULL CHECK (mode IN ('emporter', 'livraison', 'sur_place')),
    heure_voulue    timestamptz,                  -- NULL = dès que possible
    heure_annoncee  timestamptz,
    telephone       text,                         -- E.164
    prenom          text,
    second_numero   jsonb,                        -- {"numero", "qui", "pourquoi"}
    adresse         jsonb,
    zone_id         bigint REFERENCES resto_zone(id) ON DELETE SET NULL,
    remises         jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(remises) = 'array'),   -- [{"nom","montant","ref_caisse"?}]
    sous_total      integer NOT NULL DEFAULT 0 CHECK (sous_total >= 0),
    frais           integer NOT NULL DEFAULT 0 CHECK (frais >= 0),
    total           integer NOT NULL CHECK (total >= 0),
    paiement        jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(paiement) = 'object'),
    note            text,
    statut          text NOT NULL DEFAULT 'nouvelle' CHECK (statut IN (
                        'nouvelle', 'envoyee', 'recue', 'acceptee', 'en_preparation', 'prete', 'terminee',
                        'refusee', 'annulee', 'echec')),
    ref_fournisseur text,
    tentatives      integer NOT NULL DEFAULT 0 CHECK (tentatives >= 0),
    cree_par        text NOT NULL DEFAULT 'agent' CHECK (cree_par IN ('agent', 'portail', 'caisse')),
    appel_id        text,
    cle_doublon     text,
    cree_le         timestamptz NOT NULL DEFAULT now(),
    maj_le          timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_commande_doublon_idx ON resto_commande (site_id, cle_doublon) WHERE cle_doublon IS NOT NULL;
CREATE INDEX IF NOT EXISTS resto_commande_site_date_idx ON resto_commande (site_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS resto_commande_telephone_idx ON resto_commande (site_id, telephone);
CREATE INDEX IF NOT EXISTS resto_commande_voulue_idx ON resto_commande (site_id, heure_voulue) WHERE heure_voulue IS NOT NULL;
CREATE INDEX IF NOT EXISTS resto_commande_court_idx ON resto_commande (site_id, numero_court);

-- Les lignes : le choix imbriqué est gardé tel que le contrat le décrit ({"option_code","quantite","choix":[...]}).
CREATE TABLE IF NOT EXISTS resto_commande_ligne (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    numero        uuid NOT NULL REFERENCES resto_commande(numero) ON DELETE CASCADE,
    site_id       bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    rang          integer NOT NULL,
    code_caisse   text NOT NULL,
    nom           text NOT NULL,
    prix_unitaire integer NOT NULL CHECK (prix_unitaire >= 0),
    quantite      integer NOT NULL CHECK (quantite > 0),
    note          text,
    choix         jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(choix) = 'array'),
    retires       text[] NOT NULL DEFAULT '{}',
    formule_ref   text,
    UNIQUE (numero, rang)
);
CREATE INDEX IF NOT EXISTS resto_commande_ligne_site_idx ON resto_commande_ligne (site_id, numero);

-- Messages reçus d'un fournisseur : le même identifiant n'est traité qu'une fois (rejeu sans effet double).
CREATE TABLE IF NOT EXISTS resto_message_recu (
    fournisseur text NOT NULL,
    identifiant text NOT NULL,
    site_id     bigint REFERENCES site(id) ON DELETE CASCADE,   -- vide : point de vente inconnu, journalisé quand même
    type        text,
    recu_le     timestamptz NOT NULL DEFAULT now(),
    traite_le   timestamptz,
    PRIMARY KEY (fournisseur, identifiant)
);
CREATE INDEX IF NOT EXISTS resto_message_recu_site_idx ON resto_message_recu (site_id, recu_le);

-- La fiche de liaison : quelle prise, quel point de vente, dans quel état. Jamais de secret ici (lot 9).
CREATE TABLE IF NOT EXISTS resto_liaison (
    site_id          bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    prise            text NOT NULL CHECK (btrim(prise) <> ''),
    point_de_vente   text,
    etat             text NOT NULL DEFAULT 'aucune' CHECK (etat IN ('aucune', 'ok', 'erreur', 'rompue')),
    derniere_erreur  text CHECK (derniere_erreur IS NULL OR char_length(derniere_erreur) <= 80),   -- un code, jamais un texte de fournisseur
    derniere_synchro timestamptz,
    maj_le           timestamptz NOT NULL DEFAULT now()
);

-- Compteur du numéro court : un par établissement et par jour.
CREATE TABLE IF NOT EXISTS resto_compteur_jour (
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    jour    date NOT NULL,
    dernier integer NOT NULL DEFAULT 0 CHECK (dernier >= 0),
    PRIMARY KEY (site_id, jour)
);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['resto_rupture', 'resto_etat_caisse', 'resto_reglage_type', 'resto_zone', 'resto_commande', 'resto_liaison'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_maj_le', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION resto_maj_le()', t || '_maj_le', t);
    END LOOP;
    -- Le portail écrit : les réglages par type et les zones.
    PERFORM resto_droits('resto_reglage_type', 'ecriture');
    PERFORM resto_droits('resto_zone', 'ecriture');
    -- Le portail lit seulement : il change ces objets par une route du fork.
    PERFORM resto_droits('resto_rupture', 'lecture');
    PERFORM resto_droits('resto_etat_caisse', 'lecture');
    PERFORM resto_droits('resto_commande', 'lecture');
    PERFORM resto_droits('resto_commande_ligne', 'lecture');
    PERFORM resto_droits('resto_liaison', 'lecture');
    -- Le portail n'a rien à y voir.
    PERFORM resto_droits('resto_message_recu', 'aucun');
    PERFORM resto_droits('resto_compteur_jour', 'aucun');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (26, 'Module Restauration : ruptures, état de la caisse, réglages par type, zones, commandes et lignes, messages reçus, fiche de liaison, compteur du numéro court')
ON CONFLICT (version) DO NOTHING;
