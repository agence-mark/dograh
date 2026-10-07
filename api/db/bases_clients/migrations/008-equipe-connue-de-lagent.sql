-- =====================================================================
--  008 : l'équipe connue de l'agent (chantier l-agent-collegue, L1, C1 à C3).
--  Additive seulement.
--
--  - Trois réglages de plus par personne (C1) : ce dont elle s'occupe
--    (description, 300 caractères au plus), ce que l'agent peut en dire
--    (divulguer_telephone, divulguer_mail : faux par défaut) et si l'agent
--    peut lui transférer un appel (joignable_par_transfert : faux par défaut).
--  - Les sujets et le routage entrent dans la copie en mémoire (C3) : leurs
--    écritures sont journalisées et notifiées comme le reste du référentiel.
--    personne_sujet n'a pas de colonne id : sa ligne se nomme
--    « personne_id:sujet_id » dans le journal.
-- =====================================================================
SET search_path = mark;

ALTER TABLE personne ADD COLUMN IF NOT EXISTS description text
    CONSTRAINT personne_description_courte CHECK (description IS NULL OR char_length(description) <= 300);
ALTER TABLE personne ADD COLUMN IF NOT EXISTS divulguer_telephone    boolean NOT NULL DEFAULT false;
ALTER TABLE personne ADD COLUMN IF NOT EXISTS divulguer_mail         boolean NOT NULL DEFAULT false;
ALTER TABLE personne ADD COLUMN IF NOT EXISTS joignable_par_transfert boolean NOT NULL DEFAULT false;

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
                 ELSE ligne ->> 'id' END,
            lower(TG_OP), ancien, nouveau, coalesce(current_setting('mark.auteur', true), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['sujet', 'personne_sujet'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_referentiel', t);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT OR UPDATE OR DELETE ON %I FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel()', t || '_referentiel', t);
    END LOOP;
END $$;

INSERT INTO schema_version (version, description) VALUES
    (8, 'Équipe connue de l''agent : description, divulgations et transfert possible par personne ; sujets et routage notifiés');
