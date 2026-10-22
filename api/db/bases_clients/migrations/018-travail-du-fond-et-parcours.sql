-- =====================================================================
--  018 : le travail du cerveau de fond et le parcours de l'appel (chantier
--  cloture-code-avant-migration, lot F2).
--  Additive seulement (IF NOT EXISTS, CREATE OR REPLACE, DROP POLICY IF EXISTS) : rien renommé ni
--  retiré. Un envoi sans « travaux », sans « parcours » et sans « agent_id » par tour (tout appel
--  d'avant) s'écrit exactement comme avant.
--
--  - travail_fond : une ligne par travail confié au cerveau de fond pendant l'appel, avec les outils
--    qu'il a appelés, son statut et sa durée. ⛔ Jamais le texte de la demande ni celui du résultat
--    (IX.3 : la base du client ne garde pas le texte d'un échange hors verbatim).
--  - tour.agent_id : l'agent qui portait le tour (le parcours se relit agent par agent).
--  - appel.parcours : « Agent › étape › étape », rendu par le code, pour la lecture du portail.
--  - recevoir_appel : la 016, plus ces trois écritures.
--  Sécurité par ligne de travail_fond : motif de la 015 (tout autre rôle passe comme avant, le
--  portail ne lit que les lignes des appels qu'il voit).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS travail_fond (
    appel_id  bigint   NOT NULL REFERENCES appel(id) ON DELETE CASCADE,
    ordre     smallint NOT NULL,
    statut    text,
    duree_ms  integer,
    outils    text[]   NOT NULL DEFAULT '{}',
    PRIMARY KEY (appel_id, ordre)
);

ALTER TABLE tour  ADD COLUMN IF NOT EXISTS agent_id bigint REFERENCES agent(id) ON DELETE SET NULL;
ALTER TABLE appel ADD COLUMN IF NOT EXISTS parcours text;

GRANT SELECT, INSERT, UPDATE, DELETE ON travail_fond TO mark_ecriture;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    ALTER TABLE travail_fond ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS travail_fond_autres ON travail_fond;
    CREATE POLICY travail_fond_autres ON travail_fond USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS travail_fond_portail ON travail_fond;
    CREATE POLICY travail_fond_portail ON travail_fond FOR SELECT
        USING (portail_voit_appel(appel_id, current_user));
    EXECUTE format('GRANT SELECT ON travail_fond TO %I', portail);
END $$;

-- ---------------------------------------------------------------------
--  Recevoir un appel (016), plus le travail de fond, l'agent de chaque tour et le parcours.
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
    v_b          jsonb;
    v_bd         bigint;
    v_bt         text;
    v_bs         bigint;
    v_bag        bigint;
    v_bo         integer;
    v_t          jsonb;
    v_tour_agent bigint;
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
                       cout_estime, cout_tarif_du, fournisseurs, mesures, parcours)
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
            coalesce(envoi -> 'fournisseurs', '{}'::jsonb), coalesce(envoi -> 'mesures', '{}'::jsonb),
            nullif(envoi ->> 'parcours', ''))
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

    -- Les demandes d'un appel à plusieurs demandes (lot 17 d'agents-specialises) : une demande par
    -- bloc. Le bloc « courant » est la demande de l'appel (v_demande, ses champs sont dans champ_appel,
    -- comme avant) ; chaque demande close a sa propre ligne de demande et ses champs propres
    -- (champ_demande). Sans « demandes » dans l'envoi (tout appel d'avant, tout appel à une seule
    -- demande) : rien n'est écrit ici, la fonction fait exactement ce qu'elle faisait.
    IF jsonb_typeof(envoi -> 'demandes') = 'array' THEN
        FOR v_b IN SELECT * FROM jsonb_array_elements(envoi -> 'demandes') LOOP
            CONTINUE WHEN jsonb_typeof(v_b) <> 'object';
            v_bo := coalesce((v_b ->> 'ordre')::integer, 1);
            v_bag := NULL;
            IF (v_b ->> 'agent_id') IS NOT NULL THEN
                SELECT id INTO v_bag FROM agent WHERE dograh_workflow_id = (v_b ->> 'agent_id')::integer;
            END IF;
            IF coalesce((v_b ->> 'courante')::boolean, false) THEN
                v_bd := v_demande;
            ELSE
                SELECT code INTO v_bt FROM liste_valeur
                WHERE liste = 'type_demande' AND actif AND code = nullif(v_b -> 'demande' ->> 'type', '');
                SELECT id INTO v_bs FROM sujet WHERE actif AND code = nullif(v_b -> 'demande' ->> 'sujet', '');
                INSERT INTO demande (contact_id, sujet_id, site_id, type, priorite, degre_urgence, creee_le)
                VALUES (v_contact, v_bs, v_site, coalesce(v_bt, 'autre'),
                        least(3, greatest(1, coalesce((v_b -> 'demande' ->> 'priorite')::smallint, 2))),
                        nullif(v_b -> 'demande' ->> 'degre_urgence', ''), v_debut)
                RETURNING id INTO v_bd;
                FOR v_champ IN SELECT * FROM jsonb_array_elements(coalesce(v_b -> 'champs', '[]'::jsonb)) LOOP
                    CONTINUE WHEN nullif(v_champ ->> 'nom', '') IS NULL
                               OR coalesce(v_champ ->> 'portee', 'demande') = 'appel';
                    INSERT INTO champ_demande (demande_id, nom, valeur, origine, sure, source)
                    VALUES (v_bd, v_champ ->> 'nom', v_champ ->> 'valeur',
                            CASE WHEN v_champ ->> 'origine' IN ('dicte', 'deduit') THEN v_champ ->> 'origine' END,
                            (v_champ ->> 'sure')::boolean, nullif(v_champ ->> 'source', ''))
                    ON CONFLICT (demande_id, nom) DO NOTHING;
                END LOOP;
            END IF;
            INSERT INTO appel_demande (appel_id, ordre, demande_id, agent_id, motif)
            VALUES (v_appel, least(v_bo, 32000), v_bd, v_bag, nullif(v_b ->> 'motif', ''))
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;

    -- Les tours, sans leur texte (IX.3).
    FOR v_tour IN SELECT * FROM jsonb_array_elements(coalesce(envoi -> 'tours', '[]'::jsonb)) LOOP
        CONTINUE WHEN (v_tour ->> 'numero') IS NULL;
        -- L'agent du tour : son identifiant Dograh, retrouvé parmi les agents connus de la base
        -- (aucun agent créé ici : un agent inconnu laisse le tour sans agent).
        v_tour_agent := NULL;
        IF (v_tour ->> 'agent_id') IS NOT NULL THEN
            SELECT id INTO v_tour_agent FROM agent WHERE dograh_workflow_id = (v_tour ->> 'agent_id')::integer;
        END IF;
        INSERT INTO tour (appel_id, numero, etape, locuteur, debut_s, silence_s, latence_s, interrompu, agent_id)
        VALUES (v_appel, (v_tour ->> 'numero')::integer, nullif(v_tour ->> 'etape', ''),
                CASE WHEN v_tour ->> 'locuteur' IN ('agent', 'appelant') THEN v_tour ->> 'locuteur' END,
                (v_tour ->> 'debut_s')::numeric, (v_tour ->> 'silence_s')::numeric,
                (v_tour ->> 'latence_s')::numeric, (v_tour ->> 'interrompu')::boolean, v_tour_agent)
        ON CONFLICT (appel_id, numero) DO NOTHING;
    END LOOP;

    -- Le travail du cerveau de fond : outils, statut, durée. ⛔ Ni la demande ni le résultat (leur
    -- texte n'est lu nulle part ici). Sans « travaux » dans l'envoi (tout appel d'avant) : rien.
    IF jsonb_typeof(envoi -> 'travaux') = 'array' THEN
        v_n := 0;
        FOR v_t IN SELECT * FROM jsonb_array_elements(envoi -> 'travaux') LOOP
            CONTINUE WHEN jsonb_typeof(v_t) <> 'object';
            v_n := v_n + 1;
            INSERT INTO travail_fond (appel_id, ordre, statut, duree_ms, outils)
            VALUES (v_appel, least(v_n, 32000), nullif(v_t ->> 'statut', ''),
                    round((v_t ->> 'duree_ms')::numeric)::integer,
                    CASE WHEN jsonb_typeof(v_t -> 'outils') = 'array'
                         THEN ARRAY(SELECT jsonb_array_elements_text(v_t -> 'outils'))
                         ELSE '{}'::text[] END)
            ON CONFLICT (appel_id, ordre) DO NOTHING;
        END LOOP;
    END IF;

    -- Le verbatim, avec sa date d'expiration (politique_conservation, 6 mois par défaut).
    IF jsonb_typeof(envoi -> 'verbatim') = 'array' AND jsonb_array_length(envoi -> 'verbatim') > 0 THEN
        SELECT duree INTO v_duree_verb FROM politique_conservation WHERE table_nom = 'verbatim';
        INSERT INTO verbatim (appel_id, contenu, expire_le)
        VALUES (v_appel, envoi -> 'verbatim', v_debut + coalesce(v_duree_verb, interval '6 months'));
    END IF;

    RETURN jsonb_build_object('appel_id', v_appel, 'demande_id', v_demande, 'contact_id', v_contact,
                              'doublon', false, 'autre_demande_ouverte_id', v_autre);
END $$;

INSERT INTO schema_version (version, description) VALUES
    (18, 'Travail du cerveau de fond (travail_fond : outils, statut, durée, jamais le texte) ; agent de chaque tour (tour.agent_id) et parcours de l''appel (appel.parcours) ; recevoir_appel les écrit');
