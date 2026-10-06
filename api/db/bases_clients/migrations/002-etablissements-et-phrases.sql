-- =====================================================================
--  002 : établissements tels que Dograh les règle, phrases, notification
--  (chantier l-agent-travaille, L3, B1 à B3). Additive seulement.
-- =====================================================================
SET search_path = mark;

-- L'identifiant stable de l'établissement côté Dograh, et ce qu'il surcharge
-- (vide = hérité de l'organisation, E2).
ALTER TABLE site ADD COLUMN IF NOT EXISTS cle               text UNIQUE;
ALTER TABLE site ADD COLUMN IF NOT EXISTS second_numero     text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS numero_transfert  text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS adresse_cp        char(5);
ALTER TABLE site ADD COLUMN IF NOT EXISTS adresse_insee     char(5);
ALTER TABLE site ADD COLUMN IF NOT EXISTS adresse_commune   text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS adresse_voie      text;
-- Décision d'Evan (06/10, option A) : les horaires au format lisible que lit l'agent ;
-- horaire et fermeture restent vides jusqu'au portail.
ALTER TABLE site ADD COLUMN IF NOT EXISTS horaires_texte    text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS annonce_fermeture text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS annonce_pause     text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS termes_lexique    jsonb NOT NULL DEFAULT '[]';
ALTER TABLE site ADD COLUMN IF NOT EXISTS ordre             integer NOT NULL DEFAULT 0;

-- L'identifiant stable d'une personne de l'équipe côté Dograh (le routage la désigne).
ALTER TABLE personne ADD COLUMN IF NOT EXISTS cle text UNIQUE;

-- Plusieurs numéros appelés par établissement (site.numero_appele n'en porte qu'un).
CREATE TABLE IF NOT EXISTS site_numero (
    numero  text PRIMARY KEY,                        -- E.164 ; un numéro, un établissement
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE
);

-- Le catalogue de phrases (E5) et leurs surcharges par établissement.
CREATE TABLE IF NOT EXISTS phrase (
    variable    text PRIMARY KEY CHECK (variable ~ '^[a-z][a-z0-9_]{1,39}$'),
    description text NOT NULL DEFAULT '',
    contenu     text NOT NULL DEFAULT '',
    niveau      text NOT NULL DEFAULT 'organisation' CHECK (niveau IN ('organisation', 'etablissement')),
    ordre       integer NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS phrase_site (
    variable text   NOT NULL REFERENCES phrase(variable) ON DELETE CASCADE,
    site_id  bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    contenu  text   NOT NULL,
    PRIMARY KEY (variable, site_id)
);

-- Toute écriture du référentiel lu par l'agent est journalisée (B2) et prévient
-- Dograh (B3), qui remet sa copie en mémoire à jour.
CREATE OR REPLACE FUNCTION journaliser_referentiel() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    ancien jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    nouveau jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
BEGIN
    -- Une écriture qui ne change rien (« Enregistrer » sans modification) ne journalise rien.
    IF TG_OP = 'UPDATE' AND ancien = nouveau THEN
        RETURN NULL;
    END IF;
    INSERT INTO journal_modif (table_nom, ligne_id, champ, avant, apres, auteur)
    VALUES (TG_TABLE_NAME,
            coalesce(nouveau, ancien) ->> (CASE WHEN TG_TABLE_NAME IN ('site_numero') THEN 'numero'
                                                WHEN TG_TABLE_NAME IN ('phrase', 'phrase_site') THEN 'variable'
                                                WHEN TG_TABLE_NAME = 'reglage_metier' THEN 'cle'
                                                ELSE 'id' END),
            lower(TG_OP), ancien, nouveau, coalesce(current_setting('mark.auteur', true), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['site', 'site_numero', 'horaire', 'fermeture', 'phrase', 'phrase_site', 'personne', 'reglage_metier'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_referentiel', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel()', t || '_referentiel', t);
    END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON site_numero, phrase, phrase_site TO mark_ecriture;
GRANT SELECT ON phrase, phrase_site, site_numero TO mark_interface;   -- le client voit les phrases (E5)

INSERT INTO schema_version (version, description) VALUES
    (2, 'Établissements réglés par Dograh (numéros, surcharges), phrases, journal et notification du référentiel');
