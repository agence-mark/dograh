-- =====================================================================
--  011 : la vérification de l'appelant (chantier l-agent-collegue, L6,
--  V6). Additive seulement.
--
--  - verification : chaque tentative de vérification pendant un appel :
--    le dossier visé (le contact du hub, ou l'identifiant du dossier dans
--    le logiciel du client), les facteurs essayés, ceux qui ont réussi, le
--    résultat. ⛔ Jamais la réponse donnée par l'appelant ni le code envoyé
--    (RGPD) : la table n'a aucune colonne pour eux.
--  - Conservée 12 mois, comme l'appel.
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS verification (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id         bigint NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    contact_id       bigint REFERENCES contact(id) ON DELETE SET NULL,
    source           text NOT NULL DEFAULT 'hub' CHECK (source ~ '^[a-z][a-z0-9_]{1,39}$'),
    dossier_externe  text CHECK (dossier_externe IS NULL OR char_length(dossier_externe) <= 200),
    facteurs_essayes text[] NOT NULL DEFAULT '{}'
        CHECK (facteurs_essayes <@ ARRAY['numero', 'question', 'code_sms']::text[]),
    facteurs_reussis text[] NOT NULL DEFAULT '{}'
        CHECK (facteurs_reussis <@ ARRAY['numero', 'question', 'code_sms']::text[]),
    resultat         text NOT NULL CHECK (resultat IN ('verifie', 'insuffisant', 'echec', 'bloque')),
    le               timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS verification_appel_idx ON verification (appel_id);

GRANT SELECT, INSERT, DELETE ON verification TO mark_ecriture;  -- DELETE : la purge
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;
GRANT SELECT ON verification TO mark_interface;

INSERT INTO politique_conservation (table_nom, duree, colonne_date, decidee_le, source) VALUES
    ('verification', interval '12 months', 'le', '2026-10-07', 'l-agent-collegue V6 : comme l''appel')
ON CONFLICT (table_nom) DO NOTHING;

INSERT INTO schema_version (version, description) VALUES
    (11, 'Vérification de l''appelant : chaque tentative tracée, jamais la réponse');
