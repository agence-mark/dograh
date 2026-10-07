-- =====================================================================
--  004 : l'après-appel écrit par Dograh (chantier l-agent-travaille, L4,
--  A2, A8). Additive seulement.
--
--  - mark.recevoir_appel(envoi) : l'appel, son contact, sa demande, sa fiche,
--    ses tours, son verbatim, en une transaction ; un envoi rejoué (même
--    dograh_run_id) ne crée rien et rend ce qui existe déjà.
--  - mark.ecrire_synthese(appel, texte) : la synthèse sur l'appel (et le
--    résumé de sa demande s'il est vide).
--  - mark.nuit() : la purge table par table, les compteurs du jour, et la
--    preuve gardée dans execution_tache.
--  - le verbatim reçoit sa durée de conservation : 6 mois par défaut (A8),
--    réglable plus court depuis « Données du client ».
-- =====================================================================
SET search_path = mark;

-- La preuve des tâches de nuit (purge faite, lignes supprimées), gardée.
CREATE TABLE IF NOT EXISTS execution_tache (
    id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tache    text NOT NULL,
    debut    timestamptz NOT NULL DEFAULT now(),
    fin      timestamptz,
    statut   text NOT NULL DEFAULT 'en_cours' CHECK (statut IN ('en_cours', 'faite', 'echec')),
    resultat jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS execution_tache_debut_idx ON execution_tache (tache, debut DESC);

-- Les canaux d'action que Dograh écrit lui-même.
INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES
    ('canal_action', 'webhook', 'Workflow sur mesure', 5)
ON CONFLICT (liste, code) DO NOTHING;

-- Le verbatim : 6 mois par défaut (A8, décision du 06/10). La colonne de date
-- est celle de l'appel ; expire_le est posé à l'écriture depuis cette durée.
INSERT INTO politique_conservation (table_nom, duree, colonne_date, decidee_le, source) VALUES
    ('verbatim', interval '6 months', 'expire_le', '2026-10-06',
     'chantier l-agent-travaille A8 : 6 mois par défaut, réglable plus court ; défaut à faire valider par le client')
ON CONFLICT (table_nom) DO NOTHING;

-- ---------------------------------------------------------------------
--  Recevoir un appel (A2)
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
            v_issue, nullif(envoi ->> 'motif', ''), nullif(envoi ->> 'degre_urgence', ''),
            (envoi ->> 'hors_horaires')::boolean, (envoi ->> 'nb_tours')::integer,
            (envoi ->> 'latence_mediane_s')::numeric, (envoi ->> 'pire_silence_s')::numeric,
            (envoi ->> 'jetons_entree')::integer, (envoi ->> 'jetons_cache')::integer,
            (envoi ->> 'jetons_sortie')::integer, (envoi ->> 'secondes_transcrites')::numeric,
            (envoi ->> 'caracteres_dits')::integer, (envoi ->> 'cout_estime')::numeric,
            (envoi ->> 'cout_tarif_du')::date,
            coalesce(envoi -> 'fournisseurs', '{}'::jsonb), coalesce(envoi -> 'mesures', '{}'::jsonb))
    RETURNING id INTO v_appel;

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

-- La synthèse sur l'appel ; le résumé de la demande la reprend s'il est vide.
CREATE OR REPLACE FUNCTION ecrire_synthese(p_appel bigint, p_texte text) RETURNS void
LANGUAGE plpgsql SET search_path = mark AS $$
BEGIN
    UPDATE appel SET synthese = p_texte WHERE id = p_appel;
    UPDATE demande SET resume = p_texte
    WHERE id = (SELECT demande_id FROM appel WHERE id = p_appel) AND (resume IS NULL OR resume = '');
END $$;

-- ---------------------------------------------------------------------
--  La tâche de nuit (A8) : purge, compteurs, preuve
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION nuit() RETURNS jsonb
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_id     bigint;
    v_purge  jsonb;
BEGIN
    INSERT INTO execution_tache (tache) VALUES ('nuit') RETURNING id INTO v_id;
    SELECT coalesce(jsonb_object_agg(p.table_nom, p.lignes), '{}'::jsonb) INTO v_purge FROM purger() p;
    REFRESH MATERIALIZED VIEW kpi_jour;
    UPDATE execution_tache SET fin = now(), statut = 'faite',
           resultat = jsonb_build_object('purge', v_purge, 'kpi_jour', 'rafraichie')
    WHERE id = v_id;
    RETURN jsonb_build_object('execution_id', v_id, 'purge', v_purge);
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON execution_tache TO mark_ecriture;

INSERT INTO schema_version (version, description) VALUES
    (4, 'Après-appel écrit par Dograh : recevoir_appel, ecrire_synthese, nuit, execution_tache, verbatim 6 mois');
