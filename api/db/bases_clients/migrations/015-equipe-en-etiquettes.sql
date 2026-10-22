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
--  Le lot 8 la complète (fermeture par fiche, motifs multiples, agents de l'appel,
--  rôle et sécurité par ligne du portail, vues d'indicateurs, incidents) : voir plus bas.
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


-- =====================================================================
--  Lot 8 (chantier agents-specialises) : la base du client prête pour le portail
--  (lot 5 du plan fiche-etablissement = lot 1 du plan du portail) et pour les
--  motifs multiples et les agents d'un appel. Additive : IF NOT EXISTS,
--  colonnes facultatives ou à défaut, rien renommé ni retiré.
-- =====================================================================

-- ---------------------------------------------------------------------
--  1. Fermeture par fiche (C5) : la fiche d'un lieu porte son état forcé.
--     L'heure de fin est une heure de Paris sans décalage, comme dans le schéma
--     de Dograh (Etablissement.etat_force_jusqu_a).
-- ---------------------------------------------------------------------
ALTER TABLE site ADD COLUMN IF NOT EXISTS etat_force          text;
ALTER TABLE site ADD COLUMN IF NOT EXISTS etat_force_jusqu_a  timestamp;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                   WHERE conname = 'site_etat_force_valide' AND conrelid = 'mark.site'::regclass) THEN
        ALTER TABLE site ADD CONSTRAINT site_etat_force_valide
            CHECK (etat_force IS NULL OR etat_force IN ('OUVERT', 'PAUSE', 'FERME', 'SUR_RENDEZ_VOUS'));
    END IF;
END $$;

-- ---------------------------------------------------------------------
--  2. Cases des listes de valeurs : « compte comme réglé seul » (issues),
--     « opportunité » (motifs), « urgent » (degrés d'urgence). Cochées par .mark
--     ou par le dirigeant, jamais par le code ; aucune valeur n'est cochée ici.
-- ---------------------------------------------------------------------
ALTER TABLE liste_valeur ADD COLUMN IF NOT EXISTS regle_seul  boolean NOT NULL DEFAULT false;
ALTER TABLE liste_valeur ADD COLUMN IF NOT EXISTS opportunite boolean NOT NULL DEFAULT false;
ALTER TABLE liste_valeur ADD COLUMN IF NOT EXISTS urgent      boolean NOT NULL DEFAULT false;

-- Les transferts vers un humain s'écrivent dans `action` (D82) : un canal de plus.
INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES
    ('canal_action', 'transfert', 'Transfert vers un humain', 6)
ON CONFLICT (liste, code) DO NOTHING;

-- ---------------------------------------------------------------------
--  3. La demande : qui l'a prise, qui l'a close, quand l'urgence a été corrigée.
--     D76 : un compte du portail n'est pas forcément une personne de l'équipe ;
--     les colonnes *_par_id restent remplies quand le compte est lié à une personne.
-- ---------------------------------------------------------------------
ALTER TABLE demande ADD COLUMN IF NOT EXISTS prise_le                    timestamptz;
ALTER TABLE demande ADD COLUMN IF NOT EXISTS prise_par_id                bigint REFERENCES personne(id);
ALTER TABLE demande ADD COLUMN IF NOT EXISTS close_par_id                bigint REFERENCES personne(id);
ALTER TABLE demande ADD COLUMN IF NOT EXISTS urgence_modifiee_le         timestamptz;
ALTER TABLE demande ADD COLUMN IF NOT EXISTS urgence_modifiee_par_id     bigint REFERENCES personne(id);
ALTER TABLE demande ADD COLUMN IF NOT EXISTS prise_par_compte            text;
ALTER TABLE demande ADD COLUMN IF NOT EXISTS close_par_compte            text;
ALTER TABLE demande ADD COLUMN IF NOT EXISTS rappelee_par_compte         text;
ALTER TABLE demande ADD COLUMN IF NOT EXISTS urgence_modifiee_par_compte text;

-- ---------------------------------------------------------------------
--  4. L'agent rattaché au portail par .mark (D90, M9) : une date, jamais une saisie du client.
-- ---------------------------------------------------------------------
ALTER TABLE agent ADD COLUMN IF NOT EXISTS rattache_le timestamptz;

-- ---------------------------------------------------------------------
--  5. Les motifs d'un appel (A8, D48) et les agents qui l'ont pris (D83).
--     appel.motif garde le PREMIER motif ; appel_motif porte tous les motifs de la liste
--     fermée motif_appel, dans l'ordre. appel_agent : un agent par ligne, dans l'ordre
--     de l'appel (le principal, ses spécialisés, de nouveau le principal...).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS appel_motif (
    appel_id    bigint   NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    motif       text     NOT NULL,
    ordre       smallint NOT NULL DEFAULT 1,
    motif_liste text GENERATED ALWAYS AS ('motif_appel') STORED,
    PRIMARY KEY (appel_id, motif),
    FOREIGN KEY (motif_liste, motif) REFERENCES liste_valeur(liste, code)
);

CREATE TABLE IF NOT EXISTS appel_agent (
    appel_id bigint   NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    agent_id bigint   NOT NULL REFERENCES agent(id),
    ordre    smallint NOT NULL,
    heure    timestamptz,
    PRIMARY KEY (appel_id, ordre)
);

-- Les fils de commentaires (D9) : sur un appel OU sur un contact, jamais les deux.
-- Suppression douce : la trace reste en base, masquée à l'écran par le portail.
CREATE TABLE IF NOT EXISTS commentaire (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id      bigint REFERENCES appel(id)   ON DELETE CASCADE,
    contact_id    bigint REFERENCES contact(id) ON DELETE CASCADE,
    auteur_id     bigint REFERENCES personne(id),
    auteur_compte text   NOT NULL,
    texte         text   NOT NULL CHECK (char_length(btrim(texte)) > 0),
    le            timestamptz NOT NULL DEFAULT now(),
    modifie_le    timestamptz,
    supprime_le   timestamptz,
    CHECK ((appel_id IS NOT NULL) <> (contact_id IS NOT NULL))
);

-- Les appels d'avant la 015 : leur motif et leur agent sont rangés, une fois (rejouable).
INSERT INTO liste_valeur (liste, code, libelle, ordre)
SELECT DISTINCT 'motif_appel', btrim(motif), btrim(motif), 50 FROM appel
WHERE btrim(coalesce(motif, '')) <> '' AND char_length(btrim(motif)) <= 100
ON CONFLICT (liste, code) DO NOTHING;
INSERT INTO appel_motif (appel_id, motif, ordre)
SELECT id, btrim(motif), 1 FROM appel
WHERE btrim(coalesce(motif, '')) <> '' AND char_length(btrim(motif)) <= 100
ON CONFLICT DO NOTHING;
INSERT INTO appel_agent (appel_id, agent_id, ordre, heure)
SELECT a.id, v.agent_id, 1, a.debut FROM appel a JOIN version_agent v ON v.id = a.version_agent_id
ON CONFLICT DO NOTHING;

-- Index des lectures du portail.
CREATE INDEX IF NOT EXISTS appel_site_debut_idx     ON appel (site_id, debut DESC);
CREATE INDEX IF NOT EXISTS demande_site_creee_idx   ON demande (site_id, creee_le DESC);
CREATE INDEX IF NOT EXISTS commentaire_appel_idx    ON commentaire (appel_id) WHERE appel_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS commentaire_contact_idx  ON commentaire (contact_id) WHERE contact_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS appel_motif_motif_idx    ON appel_motif (motif);
CREATE INDEX IF NOT EXISTS appel_agent_agent_idx    ON appel_agent (agent_id);
CREATE INDEX IF NOT EXISTS action_appel_idx         ON action (appel_id);
CREATE INDEX IF NOT EXISTS action_demande_idx       ON action (demande_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON appel_motif, appel_agent, commentaire TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;

-- ---------------------------------------------------------------------
--  6. Les motifs reçus avec un appel : une liste, ou une chaîne dont les valeurs sont
--     séparées par « ; ». Une chaîne sans « ; » = un seul motif (comportement d'avant).
--     Le premier est le motif de l'appel ; les doublons et les vides tombent.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION motifs_de(envoi jsonb) RETURNS text[]
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    v_brut    jsonb := CASE WHEN jsonb_typeof(envoi -> 'motifs') = 'array' THEN envoi -> 'motifs' ELSE envoi -> 'motif' END;
    v_valeurs text[] := '{}';
    v_m       text;
    v_sortie  text[] := '{}';
BEGIN
    IF v_brut IS NULL OR jsonb_typeof(v_brut) = 'null' THEN
        RETURN v_sortie;
    END IF;
    IF jsonb_typeof(v_brut) = 'array' THEN
        SELECT coalesce(array_agg(x.v ORDER BY x.o), '{}') INTO v_valeurs
        FROM jsonb_array_elements_text(v_brut) WITH ORDINALITY AS x(v, o);
    ELSIF jsonb_typeof(v_brut) = 'string' THEN
        v_valeurs := string_to_array(v_brut #>> '{}', ';');
    ELSE
        v_valeurs := ARRAY[v_brut #>> '{}'];
    END IF;
    FOREACH v_m IN ARRAY v_valeurs LOOP
        v_m := btrim(coalesce(v_m, ''));
        IF v_m <> '' AND NOT (v_m = ANY (v_sortie)) THEN
            v_sortie := v_sortie || v_m;
        END IF;
    END LOOP;
    RETURN v_sortie;
END $$;

-- ---------------------------------------------------------------------
--  7. Recevoir un appel (004), avec les motifs (appel_motif, motif_appel), les agents de
--     l'appel (appel_agent). Tout le reste est identique à la 004.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION recevoir_appel(envoi jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_run        integer := (envoi ->> 'dograh_run_id')::integer;
    v_appel      bigint;
    v_demande    bigint;
    v_contact    bigint;
    v_agent      bigint;
    v_version    bigint;
    v_site       bigint;
    v_numero     text := nullif(envoi ->> 'numero_appelant', '');
    v_issue      text := nullif(envoi ->> 'issue', '');
    v_debut      timestamptz := coalesce((envoi ->> 'debut')::timestamptz, now());
    v_duree_verb interval;
    v_autre      bigint;
    v_d          jsonb := envoi -> 'demande';
    v_type       text;
    v_sujet      bigint;
    v_c          jsonb := coalesce(envoi -> 'contact', '{}'::jsonb);
    v_champ      jsonb;
    v_tour       jsonb;
    v_motifs     text[] := motifs_de(envoi);
    v_i          integer;
    v_m          text;
    v_ag         jsonb;
    v_ag_id      bigint;
    v_n          integer;
BEGIN
    IF v_run IS NULL THEN
        RAISE EXCEPTION 'recevoir_appel : dograh_run_id manquant';
    END IF;

    -- Un envoi rejoué ne crée rien (appel.dograh_run_id est unique).
    SELECT id, demande_id, contact_id INTO v_appel, v_demande, v_contact
    FROM appel WHERE dograh_run_id = v_run;
    IF FOUND THEN
        RETURN jsonb_build_object('appel_id', v_appel, 'demande_id', v_demande,
                                  'contact_id', v_contact, 'doublon', true);
    END IF;

    -- L'agent et sa version, tels que Dograh les numérote.
    INSERT INTO agent (dograh_workflow_id, nom)
    VALUES ((envoi ->> 'dograh_workflow_id')::integer, coalesce(nullif(envoi ->> 'agent_nom', ''), 'Agent'))
    ON CONFLICT (dograh_workflow_id) DO UPDATE SET nom = EXCLUDED.nom
    RETURNING id INTO v_agent;
    INSERT INTO version_agent (agent_id, dograh_definition_id, numero_version)
    VALUES (v_agent, (envoi ->> 'dograh_definition_id')::integer, (envoi ->> 'numero_version')::integer)
    ON CONFLICT (dograh_definition_id) DO UPDATE SET numero_version = coalesce(EXCLUDED.numero_version, version_agent.numero_version)
    RETURNING id INTO v_version;

    -- L'établissement servi : son identifiant Dograh, sinon le numéro appelé.
    SELECT id INTO v_site FROM site WHERE cle = nullif(envoi ->> 'etablissement', '');
    IF v_site IS NULL AND nullif(envoi ->> 'numero_appele', '') IS NOT NULL THEN
        SELECT site_id INTO v_site FROM site_numero WHERE numero = envoi ->> 'numero_appele';
    END IF;

    -- Le contact, retrouvé par son numéro exact (E.164) ; créé sinon.
    IF v_numero IS NOT NULL THEN
        SELECT contact_id INTO v_contact FROM telephone WHERE numero = v_numero;
        IF v_contact IS NULL THEN
            INSERT INTO contact (nom, prenom, mail)
            VALUES (nullif(v_c ->> 'nom', ''), nullif(v_c ->> 'prenom', ''), nullif(v_c ->> 'mail', ''))
            RETURNING id INTO v_contact;
            INSERT INTO telephone (numero, contact_id) VALUES (v_numero, v_contact)
            ON CONFLICT (numero) DO UPDATE SET contact_id = coalesce(telephone.contact_id, EXCLUDED.contact_id);
        ELSE
            -- Ce qui manquait à la fiche se complète ; ce qui était su ne s'écrase pas.
            UPDATE contact SET nom = coalesce(nom, nullif(v_c ->> 'nom', '')),
                               prenom = coalesce(prenom, nullif(v_c ->> 'prenom', '')),
                               mail = coalesce(mail, nullif(v_c ->> 'mail', ''))
            WHERE id = v_contact;
        END IF;
    END IF;

    -- Une issue que la liste ne connaît pas encore y entre (un besoin propre = une ligne).
    IF v_issue IS NOT NULL THEN
        INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES ('issue_appel', v_issue, v_issue, 50)
        ON CONFLICT (liste, code) DO NOTHING;
    END IF;

    -- Une demande par appel (A2), quand l'appel en porte une.
    IF v_d IS NOT NULL AND jsonb_typeof(v_d) = 'object' THEN
        SELECT code INTO v_type FROM liste_valeur
        WHERE liste = 'type_demande' AND actif AND code = nullif(v_d ->> 'type', '');
        SELECT id INTO v_sujet FROM sujet WHERE actif AND code = nullif(v_d ->> 'sujet', '');
        INSERT INTO demande (contact_id, sujet_id, site_id, type, priorite, degre_urgence, resume, creee_le)
        VALUES (v_contact, v_sujet, v_site, coalesce(v_type, 'autre'),
                least(3, greatest(1, coalesce((v_d ->> 'priorite')::smallint, 2))),
                nullif(v_d ->> 'degre_urgence', ''), nullif(v_d ->> 'resume', ''), v_debut)
        RETURNING id INTO v_demande;
        -- L'indice : une autre demande ouverte venue du même numéro (la machine signale, l'humain tranche).
        IF v_numero IS NOT NULL THEN
            SELECT d2.id INTO v_autre
            FROM appel a2 JOIN demande d2 ON d2.id = a2.demande_id
            WHERE a2.numero_appelant = v_numero AND d2.id <> v_demande
              AND d2.close_le IS NULL AND d2.rattachee_a_id IS NULL
            ORDER BY d2.creee_le DESC LIMIT 1;
        END IF;
    END IF;

    -- Le motif de l'appel est le PREMIER des motifs reçus (A8).
    INSERT INTO appel (dograh_run_id, version_agent_id, site_id, contact_id, demande_id, appel_precedent_id,
                       canal, sens, numero_appelant, numero_appele, debut, duree_s, issue, motif,
                       degre_urgence, hors_horaires, nb_tours, latence_mediane_s, pire_silence_s,
                       jetons_entree, jetons_cache, jetons_sortie, secondes_transcrites, caracteres_dits,
                       cout_estime, cout_tarif_du, fournisseurs, mesures)
    VALUES (v_run, v_version, v_site, v_contact, v_demande,
            (SELECT a.id FROM appel a WHERE v_numero IS NOT NULL AND a.numero_appelant = v_numero
             ORDER BY a.debut DESC LIMIT 1),
            coalesce(nullif(envoi ->> 'canal', ''), 'telephone'),
            CASE WHEN envoi ->> 'sens' = 'sortant' THEN 'sortant' ELSE 'entrant' END,
            v_numero, nullif(envoi ->> 'numero_appele', ''), v_debut, (envoi ->> 'duree_s')::integer,
            v_issue, v_motifs[1], nullif(envoi ->> 'degre_urgence', ''),
            (envoi ->> 'hors_horaires')::boolean, (envoi ->> 'nb_tours')::integer,
            (envoi ->> 'latence_mediane_s')::numeric, (envoi ->> 'pire_silence_s')::numeric,
            (envoi ->> 'jetons_entree')::integer, (envoi ->> 'jetons_cache')::integer,
            (envoi ->> 'jetons_sortie')::integer, (envoi ->> 'secondes_transcrites')::numeric,
            (envoi ->> 'caracteres_dits')::integer, (envoi ->> 'cout_estime')::numeric,
            (envoi ->> 'cout_tarif_du')::date,
            coalesce(envoi -> 'fournisseurs', '{}'::jsonb), coalesce(envoi -> 'mesures', '{}'::jsonb))
    RETURNING id INTO v_appel;

    -- Chaque motif reçu entre dans la liste fermée motif_appel et dans appel_motif (A8, D48).
    -- Une phrase de plus de 100 caractères n'est pas une valeur de liste : elle reste dans
    -- appel.motif seulement (les agents d'avant écrivaient une phrase libre).
    FOR v_i IN 1 .. coalesce(array_length(v_motifs, 1), 0) LOOP
        v_m := v_motifs[v_i];
        CONTINUE WHEN char_length(v_m) > 100;
        INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES ('motif_appel', v_m, v_m, 50)
        ON CONFLICT (liste, code) DO NOTHING;
        INSERT INTO appel_motif (appel_id, motif, ordre) VALUES (v_appel, v_m, least(v_i, 32000))
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Les agents de l'appel, dans l'ordre (D83). Sans liste : l'agent qui a décroché.
    v_n := 0;
    IF jsonb_typeof(envoi -> 'agents') = 'array' THEN
        FOR v_ag IN SELECT * FROM jsonb_array_elements(envoi -> 'agents') LOOP
            CONTINUE WHEN jsonb_typeof(v_ag) <> 'object' OR (v_ag ->> 'dograh_workflow_id') IS NULL;
            INSERT INTO agent (dograh_workflow_id, nom)
            VALUES ((v_ag ->> 'dograh_workflow_id')::integer, coalesce(nullif(v_ag ->> 'nom', ''), 'Agent'))
            ON CONFLICT (dograh_workflow_id) DO UPDATE
                SET nom = CASE WHEN nullif(v_ag ->> 'nom', '') IS NOT NULL THEN EXCLUDED.nom ELSE agent.nom END
            RETURNING id INTO v_ag_id;
            v_n := v_n + 1;
            INSERT INTO appel_agent (appel_id, agent_id, ordre, heure)
            VALUES (v_appel, v_ag_id, v_n,
                    CASE WHEN v_n = 1 THEN v_debut ELSE nullif(v_ag ->> 'heure', '')::timestamptz END)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    IF v_n = 0 THEN
        INSERT INTO appel_agent (appel_id, agent_id, ordre, heure) VALUES (v_appel, v_agent, 1, v_debut)
        ON CONFLICT DO NOTHING;
    END IF;

    -- La fiche : un champ par ligne, sa provenance quand elle est connue.
    FOR v_champ IN SELECT * FROM jsonb_array_elements(coalesce(envoi -> 'champs', '[]'::jsonb)) LOOP
        CONTINUE WHEN nullif(v_champ ->> 'nom', '') IS NULL;
        INSERT INTO champ_appel (appel_id, nom, valeur, origine, sure, source)
        VALUES (v_appel, v_champ ->> 'nom', v_champ ->> 'valeur',
                CASE WHEN v_champ ->> 'origine' IN ('dicte', 'deduit') THEN v_champ ->> 'origine' END,
                (v_champ ->> 'sure')::boolean, nullif(v_champ ->> 'source', ''))
        ON CONFLICT (appel_id, nom) DO NOTHING;
    END LOOP;

    -- Les tours, sans leur texte (IX.3).
    FOR v_tour IN SELECT * FROM jsonb_array_elements(coalesce(envoi -> 'tours', '[]'::jsonb)) LOOP
        CONTINUE WHEN (v_tour ->> 'numero') IS NULL;
        INSERT INTO tour (appel_id, numero, etape, locuteur, debut_s, silence_s, latence_s, interrompu)
        VALUES (v_appel, (v_tour ->> 'numero')::integer, nullif(v_tour ->> 'etape', ''),
                CASE WHEN v_tour ->> 'locuteur' IN ('agent', 'appelant') THEN v_tour ->> 'locuteur' END,
                (v_tour ->> 'debut_s')::numeric, (v_tour ->> 'silence_s')::numeric,
                (v_tour ->> 'latence_s')::numeric, (v_tour ->> 'interrompu')::boolean)
        ON CONFLICT (appel_id, numero) DO NOTHING;
    END LOOP;

    -- Le verbatim, avec sa date d'expiration (politique_conservation, 6 mois par défaut).
    IF jsonb_typeof(envoi -> 'verbatim') = 'array' AND jsonb_array_length(envoi -> 'verbatim') > 0 THEN
        SELECT duree INTO v_duree_verb FROM politique_conservation WHERE table_nom = 'verbatim';
        INSERT INTO verbatim (appel_id, contenu, expire_le)
        VALUES (v_appel, envoi -> 'verbatim', v_debut + coalesce(v_duree_verb, interval '6 months'));
    END IF;

    RETURN jsonb_build_object('appel_id', v_appel, 'demande_id', v_demande, 'contact_id', v_contact,
                              'doublon', false, 'autre_demande_ouverte_id', v_autre);
END $$;

-- ---------------------------------------------------------------------
--  8. Les incidents (lot 9) : un incident = une brique et une cause ; un même incident
--     touche plusieurs appels. Un incident de même brique et de même cause, vu dans les
--     30 minutes, est le MÊME (sa fin est la dernière fois qu'on l'a vu). Rejouable :
--     le lien appel-incident est unique.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION noter_incident(
    p_appel bigint, p_brique text, p_cause text, p_debut timestamptz,
    p_fin timestamptz DEFAULT NULL, p_correctif text DEFAULT NULL
) RETURNS bigint LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_id    bigint;
    v_debut timestamptz := coalesce(p_debut, now());
    v_fin   timestamptz := coalesce(p_fin, coalesce(p_debut, now()));
BEGIN
    SELECT i.id INTO v_id FROM incident i
    WHERE i.brique IS NOT DISTINCT FROM p_brique AND i.cause IS NOT DISTINCT FROM p_cause
      AND i.debut <= v_debut + interval '30 minutes'
      AND coalesce(i.fin, i.debut) >= v_debut - interval '30 minutes'
    ORDER BY i.debut DESC LIMIT 1;
    IF v_id IS NULL THEN
        INSERT INTO incident (debut, fin, brique, cause, correctif)
        VALUES (v_debut, v_fin, p_brique, p_cause, p_correctif) RETURNING id INTO v_id;
    ELSE
        UPDATE incident SET fin = greatest(coalesce(fin, debut), v_fin),
                            correctif = coalesce(correctif, p_correctif)
        WHERE id = v_id;
    END IF;
    IF p_appel IS NOT NULL THEN
        INSERT INTO incident_appel (incident_id, appel_id) VALUES (v_id, p_appel) ON CONFLICT DO NOTHING;
    END IF;
    RETURN v_id;
END $$;

-- ---------------------------------------------------------------------
--  9. Le portail : un rôle de lecture et d'écriture limité, la sécurité par ligne
--     par variable de session. La variable `mark.sites_portail` porte la liste des
--     identifiants d'établissements du compte (« 3,7 »), ou « * » pour tous (D76).
--     Variable absente ou vide = rien de lisible. Le portail la pose à chaque
--     transaction (SET LOCAL / set_config(..., true)) d'après le compte connecté.
--     ⚠️ Le portail est de confiance : un compte de connexion de ce rôle pourrait poser
--     lui-même la variable. La protection est dans le portail (jamais de SQL libre).
-- ---------------------------------------------------------------------
DO $$
DECLARE
    base text := current_database();
    portail text := base || '_portail';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = portail) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', portail);
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I', base, portail);
    EXECUTE format('GRANT USAGE ON SCHEMA mark TO %I', portail);
END $$;

-- Membre DIRECT du groupe du portail, ou le groupe lui-même (un membre peut faire SET ROLE
-- sur le groupe : il reste alors dans la règle). Comme est_un_salarie, sans pg_has_role
-- (vrai pour tout superutilisateur).
CREATE OR REPLACE FUNCTION est_du_portail(qui name) RETURNS boolean
LANGUAGE sql STABLE SET search_path = pg_catalog AS $$
    SELECT qui = (current_database() || '_portail')::name OR EXISTS (
        SELECT 1 FROM pg_auth_members m
        JOIN pg_roles g ON g.oid = m.roleid AND g.rolname = current_database() || '_portail'
        JOIN pg_roles u ON u.oid = m.member AND u.rolname = qui
    );
$$;

CREATE OR REPLACE FUNCTION portail_voit_site(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND CASE
        WHEN btrim(coalesce(current_setting('mark.sites_portail', true), '')) = '' THEN false
        WHEN btrim(current_setting('mark.sites_portail', true)) = '*' THEN true
        ELSE cible IS NOT NULL
             AND cible::text = ANY (string_to_array(replace(current_setting('mark.sites_portail', true), ' ', ''), ','))
    END;
$$;

CREATE OR REPLACE FUNCTION portail_voit_appel(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui)
       AND EXISTS (SELECT 1 FROM appel a WHERE a.id = cible AND portail_voit_site(a.site_id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_demande(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui)
       AND EXISTS (SELECT 1 FROM demande d WHERE d.id = cible AND portail_voit_site(d.site_id, qui));
$$;

CREATE OR REPLACE FUNCTION portail_voit_contact(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui) AND (
        EXISTS (SELECT 1 FROM appel a WHERE a.contact_id = cible AND portail_voit_site(a.site_id, qui))
        OR EXISTS (SELECT 1 FROM demande d WHERE d.contact_id = cible AND portail_voit_site(d.site_id, qui)));
$$;

CREATE OR REPLACE FUNCTION portail_voit_rdv(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT est_du_portail(qui)
       AND EXISTS (SELECT 1 FROM rendez_vous r JOIN demande d ON d.id = r.demande_id
                   WHERE r.id = cible AND portail_voit_site(d.site_id, qui));
$$;

-- Les règles d'avant ne laissent jamais passer le portail : une règle « pas un lecteur interne »
-- (voit_le_site, voit_la_mention) lui aurait ouvert toutes les lignes.
CREATE OR REPLACE FUNCTION voit_le_site(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT NOT est_un_salarie(qui)
       AND NOT est_du_portail(qui)
       AND (cible IS NULL
            OR pg_has_role(qui, current_database() || '_direction', 'MEMBER')
            OR NOT pg_has_role(qui, 'mark_interface', 'MEMBER')
            OR EXISTS (SELECT 1 FROM role_site r WHERE r.role = qui AND r.site_id = cible));
$$;

CREATE OR REPLACE FUNCTION voit_la_mention(cible bigint, qui name) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT NOT est_du_portail(qui)
       AND (NOT pg_has_role(qui, current_database() || '_salarie', 'MEMBER')
            OR cible = personne_du_role(qui));
$$;

-- Un salarié sur plusieurs lieux voit les appels de chacun (M5) : le lieu de sa fiche, ceux de
-- personne_site, et ceux qu'on lui ouvre en plus.
CREATE OR REPLACE FUNCTION sites_du_salarie(qui name) RETURNS SETOF bigint
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT p.site_id FROM role_personne rp JOIN personne p ON p.id = rp.personne_id
    WHERE rp.role = qui AND p.actif AND p.site_id IS NOT NULL
      AND (qui = session_user OR NOT est_un_salarie(session_user))
    UNION
    SELECT ps.site_id FROM role_personne rp
    JOIN personne p ON p.id = rp.personne_id
    JOIN personne_site ps ON ps.personne_id = p.id
    WHERE rp.role = qui AND p.actif
      AND (qui = session_user OR NOT est_un_salarie(session_user))
    UNION
    SELECT r.site_id FROM role_site r
    WHERE r.role = qui AND personne_du_role(qui) IS NOT NULL;
$$;

-- La sécurité par ligne du portail. Les tables qui avaient déjà une règle (appel, demande,
-- mention) gardent la leur et en reçoivent une pour le portail ; les autres en reçoivent deux :
-- « tout autre rôle passe comme avant » et « le portail ne lit que ses lignes ».
DROP POLICY IF EXISTS appel_portail ON appel;
CREATE POLICY appel_portail ON appel FOR SELECT USING (portail_voit_site(site_id, current_user));
DROP POLICY IF EXISTS demande_portail ON demande;
CREATE POLICY demande_portail ON demande USING (portail_voit_site(site_id, current_user));
DROP POLICY IF EXISTS mention_portail ON mention;
CREATE POLICY mention_portail ON mention FOR SELECT USING (portail_voit_appel(appel_id, current_user));

DO $$
DECLARE
    t text;
    portail text := current_database() || '_portail';
BEGIN
    -- Les tables d'un appel.
    FOREACH t IN ARRAY ARRAY['verbatim', 'champ_appel', 'tour', 'transfert', 'appel_agent', 'appel_motif'] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_autres', t);
        EXECUTE format('CREATE POLICY %I ON %I USING ((SELECT NOT est_du_portail(current_user)))', t || '_autres', t);
        EXECUTE format('DROP POLICY IF EXISTS %I ON %I', t || '_portail', t);
        EXECUTE format('CREATE POLICY %I ON %I FOR SELECT USING (portail_voit_appel(appel_id, current_user))', t || '_portail', t);
        EXECUTE format('GRANT SELECT ON %I TO %I', t, portail);
    END LOOP;

    -- L'action : liée à un appel ou à une demande.
    ALTER TABLE action ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS action_autres ON action;
    CREATE POLICY action_autres ON action USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS action_portail ON action;
    CREATE POLICY action_portail ON action FOR SELECT
        USING (portail_voit_appel(appel_id, current_user) OR portail_voit_demande(demande_id, current_user));
    EXECUTE format('GRANT SELECT ON action TO %I', portail);

    -- Les rendez-vous, par leur demande ; l'attribution, par son rendez-vous.
    ALTER TABLE rendez_vous ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS rendez_vous_autres ON rendez_vous;
    CREATE POLICY rendez_vous_autres ON rendez_vous USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS rendez_vous_portail ON rendez_vous;
    CREATE POLICY rendez_vous_portail ON rendez_vous FOR SELECT USING (portail_voit_demande(demande_id, current_user));
    EXECUTE format('GRANT SELECT ON rendez_vous TO %I', portail);
    ALTER TABLE attribution ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS attribution_autres ON attribution;
    CREATE POLICY attribution_autres ON attribution USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS attribution_portail ON attribution;
    CREATE POLICY attribution_portail ON attribution FOR SELECT USING (portail_voit_rdv(rendez_vous_id, current_user));
    EXECUTE format('GRANT SELECT ON attribution TO %I', portail);

    -- Le contact et ses numéros : visibles par un appel ou une demande visible.
    ALTER TABLE contact ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS contact_autres ON contact;
    CREATE POLICY contact_autres ON contact USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS contact_portail ON contact;
    CREATE POLICY contact_portail ON contact FOR SELECT USING (portail_voit_contact(id, current_user));
    ALTER TABLE telephone ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS telephone_autres ON telephone;
    CREATE POLICY telephone_autres ON telephone USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS telephone_portail ON telephone;
    CREATE POLICY telephone_portail ON telephone FOR SELECT USING (portail_voit_contact(contact_id, current_user));
    EXECUTE format('GRANT SELECT ON contact, telephone TO %I', portail);

    -- Les commentaires : sur un appel ou un contact visible. Le portail lit et écrit.
    ALTER TABLE commentaire ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS commentaire_autres ON commentaire;
    CREATE POLICY commentaire_autres ON commentaire USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS commentaire_portail ON commentaire;
    CREATE POLICY commentaire_portail ON commentaire USING (
        CASE WHEN appel_id IS NOT NULL THEN portail_voit_appel(appel_id, current_user)
             ELSE portail_voit_contact(contact_id, current_user) END);
    EXECUTE format('GRANT SELECT, INSERT ON commentaire TO %I', portail);
    EXECUTE format('GRANT UPDATE (texte, modifie_le, supprime_le) ON commentaire TO %I', portail);
    EXECUTE format('GRANT USAGE ON SEQUENCE commentaire_id_seq TO %I', portail);

    -- Les établissements : chaque compte ne voit que les siens.
    ALTER TABLE site ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS site_autres ON site;
    CREATE POLICY site_autres ON site USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS site_portail ON site;
    CREATE POLICY site_portail ON site FOR SELECT USING (portail_voit_site(id, current_user));
    EXECUTE format('GRANT SELECT ON site TO %I', portail);

    -- Les appels, les demandes et les mentions (règles ci-dessus). Les demandes : le portail
    -- agit (prise en charge, rappel, clôture, urgence), pas ailleurs, et ne change jamais
    -- d'établissement ni ne fusionne des demandes.
    EXECUTE format('GRANT SELECT ON appel, mention TO %I', portail);
    EXECUTE format('GRANT SELECT ON demande TO %I', portail);
    EXECUTE format($g$GRANT UPDATE (statut, priorite, degre_urgence, assignee_id, rappelee_le, rappelee_par_id,
        rappelee_par_compte, prise_le, prise_par_id, prise_par_compte, close_le, close_par_id, close_par_compte,
        urgence_modifiee_le, urgence_modifiee_par_id, urgence_modifiee_par_compte) ON demande TO %I$g$, portail);

    -- Ce qui n'est pas propre à un établissement : les listes de valeurs, les sujets, les
    -- agents, les noms de l'équipe (ni mail ni téléphone).
    EXECUTE format('GRANT SELECT ON liste_valeur, sujet, agent, version_agent, agent_site, personne_site TO %I', portail);
    EXECUTE format('GRANT SELECT (id, cle, prenom, nom, role, site_id, actif) ON personne TO %I', portail);
END $$;

-- ---------------------------------------------------------------------
--  10. Les indicateurs du portail, calculés en direct (kpi_jour ne se rafraîchit que la nuit).
--      Aucune donnée personnelle : des comptes, par jour (heure du lieu) et par établissement ;
--      le portail additionne les jours d'une période. Chaque vue applique la même règle que
--      les tables (portail_voit_site) : un autre rôle n'y lit rien.
-- ---------------------------------------------------------------------
-- [.mark] cloture-code (CI comparée, constat 24) : la 017 ajoute des colonnes à cette vue ; une base
-- remise en arrière puis remontée rejoue la 015 après la 017, et CREATE OR REPLACE ne retire pas de
-- colonne. La vue est donc refaite à neuf ici (aucune vue ni règle n'en dépend ; ses droits suivent).
DROP VIEW IF EXISTS v_portail_kpi;
CREATE OR REPLACE VIEW v_portail_kpi AS
SELECT x.site_id, x.jour,
       count(*)                                          AS appels,
       count(*) FILTER (WHERE x.hors_horaires)           AS hors_horaires,
       count(*) FILTER (WHERE x.regle_seul)              AS regles_seul,
       count(*) FILTER (WHERE x.transmis)                AS transmis,
       count(*) FILTER (WHERE x.premier_appel)           AS premiers_appels,
       count(*) FILTER (WHERE x.nouveau_projet)          AS nouveaux_projets,
       count(*) FILTER (WHERE x.urgent)                  AS urgents,
       coalesce(sum(x.duree_s), 0)::bigint               AS duree_totale_s,
       coalesce(sum(x.rendez_vous_pris), 0)::bigint      AS rendez_vous_pris
FROM (
    SELECT a.site_id,
           (a.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
           a.hors_horaires, a.duree_s,
           (a.appel_precedent_id IS NULL) AS premier_appel,
           EXISTS (SELECT 1 FROM liste_valeur lv
                   WHERE lv.liste = a.issue_liste AND lv.code = a.issue AND lv.regle_seul) AS regle_seul,
           (a.demande_id IS NOT NULL
            OR EXISTS (SELECT 1 FROM transfert tr WHERE tr.appel_id = a.id)) AS transmis,
           EXISTS (SELECT 1 FROM appel_motif am
                   JOIN liste_valeur lv ON lv.liste = am.motif_liste AND lv.code = am.motif
                   WHERE am.appel_id = a.id AND lv.opportunite) AS nouveau_projet,
           EXISTS (SELECT 1 FROM liste_valeur lv
                   WHERE lv.liste = 'degre_urgence' AND lv.code = a.degre_urgence AND lv.urgent) AS urgent,
           (SELECT count(*) FROM rendez_vous r
            WHERE r.demande_id = a.demande_id AND r.origine = 'agent' AND r.statut IN ('pose', 'fait')) AS rendez_vous_pris
    FROM appel a
    LEFT JOIN site s ON s.id = a.site_id
    WHERE portail_voit_site(a.site_id, current_user)
) x
GROUP BY x.site_id, x.jour;

CREATE OR REPLACE VIEW v_portail_motifs AS
SELECT a.site_id,
       (a.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
       m.motif,
       coalesce(lv.libelle, m.motif)       AS libelle,
       coalesce(lv.opportunite, false)     AS opportunite,
       count(*)                            AS appels
FROM appel a
LEFT JOIN site s ON s.id = a.site_id
CROSS JOIN LATERAL (
    SELECT am.motif FROM appel_motif am WHERE am.appel_id = a.id
    UNION ALL
    SELECT a.motif WHERE a.motif IS NOT NULL AND NOT EXISTS (SELECT 1 FROM appel_motif am WHERE am.appel_id = a.id)
) m
LEFT JOIN liste_valeur lv ON lv.liste = 'motif_appel' AND lv.code = m.motif
WHERE portail_voit_site(a.site_id, current_user)
GROUP BY a.site_id, 2, m.motif, 4, 5;

CREATE OR REPLACE VIEW v_portail_charge AS
SELECT a.site_id,
       (a.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
       extract(hour FROM a.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::integer AS heure,
       count(*) AS appels
FROM appel a
LEFT JOIN site s ON s.id = a.site_id
WHERE portail_voit_site(a.site_id, current_user)
GROUP BY a.site_id, 2, 3;

CREATE OR REPLACE VIEW v_portail_rappels AS
SELECT d.site_id,
       (d.creee_le AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
       count(*)                                                           AS demandes,
       count(*) FILTER (WHERE d.rappelee_le IS NOT NULL)                  AS rappelees,
       coalesce(sum(extract(epoch FROM d.rappelee_le - d.creee_le))
                FILTER (WHERE d.rappelee_le IS NOT NULL), 0)::bigint      AS delai_rappel_total_s,
       count(*) FILTER (WHERE d.rappelee_le IS NULL AND d.close_le IS NULL
                          AND d.rattachee_a_id IS NULL)                   AS ouvertes
FROM demande d
LEFT JOIN site s ON s.id = d.site_id
WHERE portail_voit_site(d.site_id, current_user)
GROUP BY d.site_id, 2;

DO $$
BEGIN
    EXECUTE format('GRANT SELECT ON v_portail_kpi, v_portail_motifs, v_portail_charge, v_portail_rappels TO %I',
                   current_database() || '_portail');
END $$;

-- La connexion que le portail utilise (propriétaire seulement, comme donner_acces) : un compte de
-- connexion, membre du groupe du portail, sans aucun autre droit. Le mot de passe est un argument,
-- jamais stocké ici.
CREATE OR REPLACE FUNCTION donner_connexion_portail(p_mot_de_passe text) RETURNS text
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_role text := current_database() || '_portail_c';
BEGIN
    IF coalesce(length(p_mot_de_passe), 0) < 12 THEN
        RAISE EXCEPTION 'Mot de passe trop court (12 caractères au moins)';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = v_role) THEN
        EXECUTE format('ALTER ROLE %I LOGIN PASSWORD %L', v_role, p_mot_de_passe);
    ELSE
        EXECUTE format('CREATE ROLE %I LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 20 PASSWORD %L',
                       v_role, p_mot_de_passe);
    END IF;
    EXECUTE format('GRANT %I TO %I', current_database() || '_portail', v_role);
    RETURN v_role;
END $$;
REVOKE EXECUTE ON FUNCTION donner_connexion_portail(text) FROM PUBLIC;

INSERT INTO schema_version (version, description) VALUES
    (15, 'Équipe en étiquettes (personne_site) ; fermeture par fiche ; motifs multiples (appel_motif) et agents de l''appel (appel_agent) ; commentaires, cases des listes, rôle et sécurité par ligne du portail, vues d''indicateurs, incidents');
