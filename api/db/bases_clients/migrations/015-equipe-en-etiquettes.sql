-- =====================================================================
--  015 : l'équipe en étiquettes (chantier agents-specialises, lot 5 = lot 3 du
--  plan fiche-etablissement, décision M5 : l'équipe est unique, le lieu est une
--  étiquette, jamais un filtre). Additive seulement (IF NOT EXISTS).
--
--  - personne_site : les lieux d'une personne (zéro, un ou plusieurs). Aucune
--    ligne = toute l'entreprise. La colonne personne.site_id reste, et porte le
--    PREMIER lieu (lue par le routage des courriels et par le planificateur, qui
--    n'ont pas changé) ; la lecture fait l'union des deux, une personne d'avant
--    n'a donc rien à rattraper.
--  - personne_site n'a pas de colonne id : sa ligne se nomme « personne_id:site_id »
--    dans le journal (comme personne_sujet).
--  Les lots suivants (8) complètent cette migration (vues, accès par ligne).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS personne_site (
    personne_id bigint NOT NULL REFERENCES personne(id) ON DELETE CASCADE,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    PRIMARY KEY (personne_id, site_id)
);
CREATE INDEX IF NOT EXISTS personne_site_site_idx ON personne_site (site_id);

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
                 WHEN TG_TABLE_NAME = 'personne_site' THEN (ligne ->> 'personne_id') || ':' || (ligne ->> 'site_id')
                 ELSE ligne ->> 'id' END,
            lower(TG_OP), ancien, nouveau, coalesce(current_setting('mark.auteur', true), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS personne_site_referentiel ON personne_site;
CREATE TRIGGER personne_site_referentiel AFTER INSERT OR UPDATE OR DELETE ON personne_site
    FOR EACH ROW EXECUTE FUNCTION journaliser_referentiel();

GRANT SELECT, INSERT, UPDATE, DELETE ON personne_site TO mark_ecriture;
GRANT SELECT ON personne_site TO mark_interface;

INSERT INTO schema_version (version, description) VALUES
    (15, 'Équipe en étiquettes : une personne a zéro, un ou plusieurs lieux (personne_site), jamais un filtre');
