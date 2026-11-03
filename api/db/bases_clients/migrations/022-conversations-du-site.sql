-- =====================================================================
--  022 : les conversations du site dans la base du client (chantier builder-partie-2, U10.3 / lot S3
--  du plan du portail v4, avec le lot 1 de la v2).
--  Additive seulement (IF NOT EXISTS, CREATE OR REPLACE, DROP ... IF EXISTS) : rien renommé ni retiré.
--  Réflexes de sécurité R1 à R9 : chaque table nouvelle porte sa sécurité par ligne (le portail ne lit que
--  ses lieux), chaque fonction qui écrit pour un autre est SECURITY DEFINER avec un search_path fixé, aucune
--  donnée personnelle dans une notification (table, identifiant, lieu, sorte).
--
--  - evenement_portail + déclencheurs NOTIFY 'portail' (R2) : le portail se réveille et lit depuis le dernier
--    identifiant, rien n'est perdu si l'écoute est coupée ; index manquants (R13) ;
--  - appel.page, appel.mode_site ; la valeur de canal « site » (appel.canal est un texte libre) ;
--  - recevoir_appel : sans numéro, le contact est retrouvé ou créé par son mail (minuscules) ; page et mode ;
--  - avis (un par conversation) et v_portail_avis sous la sécurité par ligne ;
--  - un avis de 1 ou 2 étoiles avec rappel demandé crée une demande « à rappeler » (type « rappel ») ;
--  - v_portail_kpi : colonnes par canal et avis, AJOUTÉES EN DERNIER (les colonnes d'avant inchangées) ;
--  - conservation : les événements du portail se purgent à 30 jours (la purge générique purger()).
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  1. L'appel du site : page et mode. « site » est un canal de plus (comme « navigateur », « clavier »).
-- ---------------------------------------------------------------------
ALTER TABLE appel ADD COLUMN IF NOT EXISTS page text;
ALTER TABLE appel ADD COLUMN IF NOT EXISTS mode_site text;
ALTER TABLE appel DROP CONSTRAINT IF EXISTS appel_mode_site_chk;
ALTER TABLE appel ADD CONSTRAINT appel_mode_site_chk
    CHECK (mode_site IS NULL OR mode_site IN ('voix', 'ecrit', 'voix_puis_ecrit'));
COMMENT ON COLUMN appel.canal IS
    'telephone, navigateur, clavier, simule, site (widget posé sur le site du client, 022)';
COMMENT ON COLUMN appel.page IS 'Chemin de la page du site où la conversation a eu lieu (canal site), sans paramètres.';
COMMENT ON COLUMN appel.mode_site IS 'voix, ecrit ou voix_puis_ecrit (canal site).';

-- Une valeur de liste posée par la migration elle-même : le journal des modifications (écritures de personnes)
-- n'en porte pas la trace, comme pour les valeurs des migrations d'avant.
ALTER TABLE liste_valeur DISABLE TRIGGER liste_valeur_referentiel;
INSERT INTO liste_valeur (liste, code, libelle, ordre) VALUES
    ('type_demande', 'rappel', 'Rappel demandé', 7)
ON CONFLICT (liste, code) DO NOTHING;
ALTER TABLE liste_valeur ENABLE TRIGGER liste_valeur_referentiel;

-- Le contact retrouvé par son mail (sans numéro) : un index sur le mail en minuscules.
CREATE INDEX IF NOT EXISTS contact_mail_minuscules_idx ON contact (lower(btrim(mail))) WHERE mail IS NOT NULL;

-- Les index que le portail demande (R13) et qui manquaient : l'urgence d'une demande, les actions d'un appel.
CREATE INDEX IF NOT EXISTS demande_degre_urgence_idx ON demande (degre_urgence) WHERE degre_urgence IS NOT NULL;
CREATE INDEX IF NOT EXISTS action_appel_statut_idx ON action (appel_id, statut);
CREATE INDEX IF NOT EXISTS appel_canal_debut_idx ON appel (canal, debut DESC);

-- ---------------------------------------------------------------------
--  2. Recevoir un appel (018), plus la page, le mode et le contact par mail.
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
    v_mail       text := nullif(lower(btrim(coalesce(envoi -> 'contact' ->> 'mail', ''))), '');
    v_page       text := nullif(left(coalesce(envoi ->> 'page', ''), 500), '');
    v_mode       text := CASE WHEN envoi ->> 'mode_site' IN ('voix', 'ecrit', 'voix_puis_ecrit') THEN envoi ->> 'mode_site' END;
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

    -- 022 : sans numéro (un visiteur du site), le contact est retrouvé ou créé par son mail, normalisé en
    -- minuscules. Avec les deux, le numéro l'emporte comme avant (le bloc au-dessus).
    IF v_numero IS NULL AND v_mail IS NOT NULL THEN
        SELECT id INTO v_contact FROM contact WHERE lower(btrim(mail)) = v_mail ORDER BY id LIMIT 1;
        IF v_contact IS NULL THEN
            INSERT INTO contact (nom, prenom, mail)
            VALUES (nullif(v_c ->> 'nom', ''), nullif(v_c ->> 'prenom', ''), v_mail)
            RETURNING id INTO v_contact;
        ELSE
            UPDATE contact SET nom = coalesce(nom, nullif(v_c ->> 'nom', '')),
                               prenom = coalesce(prenom, nullif(v_c ->> 'prenom', ''))
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
                       cout_estime, cout_tarif_du, fournisseurs, mesures, parcours, page, mode_site)
    VALUES (v_run, v_version, v_site, v_contact, v_demande,
            (SELECT a.id FROM appel a
             WHERE (v_numero IS NOT NULL AND a.numero_appelant = v_numero)
                OR (v_numero IS NULL AND v_contact IS NOT NULL AND a.contact_id = v_contact)
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
            nullif(envoi ->> 'parcours', ''), v_page, v_mode)
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

    IF jsonb_typeof(envoi -> 'avis') = 'object' THEN
        PERFORM noter_avis(v_run, envoi -> 'avis');
    END IF;

    RETURN jsonb_build_object('appel_id', v_appel, 'demande_id', v_demande, 'contact_id', v_contact,
                              'doublon', false, 'autre_demande_ouverte_id', v_autre);
END $$;

-- ---------------------------------------------------------------------
--  3. L'avis du visiteur : un par conversation, effacé avec elle (ON DELETE CASCADE : la suppression d'une
--     conversation sur demande, comme la purge de l'appel, efface son avis).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS avis (
    id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    appel_id             bigint NOT NULL UNIQUE REFERENCES appel(id) ON DELETE CASCADE,
    etoiles              smallint NOT NULL CHECK (etoiles BETWEEN 1 AND 5),
    obtenu               boolean,
    raisons              text[] NOT NULL DEFAULT '{}',
    commentaire          text CHECK (commentaire IS NULL OR char_length(commentaire) <= 2000),
    rappel_demande       boolean NOT NULL DEFAULT false,
    publication_acceptee boolean NOT NULL DEFAULT false,
    consentement_le      timestamptz,
    donne_le             timestamptz NOT NULL DEFAULT now(),
    CHECK (NOT publication_acceptee OR consentement_le IS NOT NULL)
);
COMMENT ON TABLE avis IS 'Avis laissé par le visiteur du site à la fin de la conversation (022). Un par conversation.';
COMMENT ON COLUMN avis.publication_acceptee IS 'Le visiteur accepte que son avis soit publié ; consentement_le dit quand.';

GRANT SELECT, INSERT, UPDATE, DELETE ON avis TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    ALTER TABLE avis ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS avis_autres ON avis;
    CREATE POLICY avis_autres ON avis USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS avis_portail ON avis;
    CREATE POLICY avis_portail ON avis FOR SELECT USING (portail_voit_appel(appel_id, current_user));
    EXECUTE format('GRANT SELECT ON avis TO %I', portail);
END $$;

CREATE OR REPLACE VIEW v_portail_avis AS
SELECT v.id, v.appel_id, a.site_id, a.contact_id, a.page, a.mode_site, a.debut AS appel_debut,
       v.etoiles, v.obtenu, v.raisons, v.commentaire, v.rappel_demande,
       v.publication_acceptee, v.consentement_le, v.donne_le
FROM avis v
JOIN appel a ON a.id = v.appel_id
WHERE portail_voit_appel(v.appel_id, current_user);

DO $$ BEGIN
    EXECUTE format('GRANT SELECT ON v_portail_avis TO %I', current_database() || '_portail');
END $$;

-- ---------------------------------------------------------------------
--  4. Les indicateurs : colonnes par canal et avis, EN DERNIER.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW v_portail_kpi AS
WITH x AS (
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
                   WHERE lv.liste = 'degre_urgence'
                     AND lv.code = coalesce(d.degre_urgence, a.degre_urgence) AND lv.urgent) AS urgent,
           (SELECT count(*) FROM rendez_vous r
            WHERE r.demande_id = a.demande_id AND r.origine = 'agent' AND r.statut IN ('pose', 'fait')) AS rendez_vous_pris,
           (a.canal = 'site') AS du_site,
           (a.canal = 'telephone') AS du_telephone,
           (SELECT v.etoiles FROM avis v WHERE v.appel_id = a.id) AS etoiles
    FROM appel a
    LEFT JOIN site s ON s.id = a.site_id
    LEFT JOIN demande d ON d.id = a.demande_id
    WHERE portail_voit_site(a.site_id, current_user)
),
agg AS (
    SELECT x.site_id, x.jour,
           count(*)                                          AS appels,
           count(*) FILTER (WHERE x.hors_horaires)           AS hors_horaires,
           count(*) FILTER (WHERE x.regle_seul)              AS regles_seul,
           count(*) FILTER (WHERE x.transmis)               AS transmis,
           count(*) FILTER (WHERE x.premier_appel)           AS premiers_appels,
           count(*) FILTER (WHERE x.nouveau_projet)          AS nouveaux_projets,
           count(*) FILTER (WHERE x.urgent)                  AS urgents,
           coalesce(sum(x.duree_s), 0)::bigint               AS duree_totale_s,
           coalesce(sum(x.rendez_vous_pris), 0)::bigint      AS rendez_vous_pris,
           count(*) FILTER (WHERE x.du_site)                 AS appels_site,
           count(*) FILTER (WHERE x.du_telephone)            AS appels_telephone,
           count(x.etoiles)                                  AS avis_nombre,
           coalesce(sum(x.etoiles), 0)::bigint               AS avis_etoiles_total
    FROM x
    GROUP BY x.site_id, x.jour
),
perdus AS (
    SELECT sn.site_id,
           (p.debut AT TIME ZONE coalesce(s.fuseau, 'Europe/Paris'))::date AS jour,
           count(*) AS appels_perdus
    FROM appel_perdu p
    JOIN site_numero sn ON sn.numero = p.numero_appele
    LEFT JOIN site s ON s.id = sn.site_id
    WHERE portail_voit_numero(p.numero_appele, current_user)
    GROUP BY sn.site_id, 2
),
cles AS (
    SELECT site_id, jour FROM agg
    UNION
    SELECT site_id, jour FROM perdus
)
SELECT c.site_id, c.jour,
       coalesce(g.appels, 0)              AS appels,
       coalesce(g.hors_horaires, 0)       AS hors_horaires,
       coalesce(g.regles_seul, 0)         AS regles_seul,
       coalesce(g.transmis, 0)            AS transmis,
       coalesce(g.premiers_appels, 0)     AS premiers_appels,
       coalesce(g.nouveaux_projets, 0)    AS nouveaux_projets,
       coalesce(g.urgents, 0)             AS urgents,
       coalesce(g.duree_totale_s, 0)      AS duree_totale_s,
       coalesce(g.rendez_vous_pris, 0)    AS rendez_vous_pris,
       coalesce(p.appels_perdus, 0)       AS appels_perdus,
       coalesce(g.appels_site, 0)         AS appels_site,
       coalesce(g.appels_telephone, 0)    AS appels_telephone,
       coalesce(g.avis_nombre, 0)         AS avis_nombre,
       coalesce(g.avis_etoiles_total, 0)  AS avis_etoiles_total
FROM cles c
LEFT JOIN agg g ON g.site_id IS NOT DISTINCT FROM c.site_id AND g.jour = c.jour
LEFT JOIN perdus p ON p.site_id IS NOT DISTINCT FROM c.site_id AND p.jour = c.jour;

-- ---------------------------------------------------------------------
--  5. Les événements du portail (R2) : id, table, ligne, lieu, sorte, horodatage. Aucune donnée personnelle.
--     Le NOTIFY 'portail' est un réveil (JSON court) ; la vérité est la table, lue depuis le dernier id.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS evenement_portail (
    id      bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tbl     text NOT NULL,
    ligne   text NOT NULL,
    site_id bigint,
    sorte   text NOT NULL,
    le      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS evenement_portail_le_idx ON evenement_portail (le);
GRANT SELECT, INSERT, UPDATE, DELETE ON evenement_portail TO mark_ecriture;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mark TO mark_ecriture;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    ALTER TABLE evenement_portail ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS evenement_portail_autres ON evenement_portail;
    CREATE POLICY evenement_portail_autres ON evenement_portail USING ((SELECT NOT est_du_portail(current_user)));
    -- Le portail ne lit que les événements de ses lieux (un événement sans lieu n'est vu que de qui voit tout).
    DROP POLICY IF EXISTS evenement_portail_portail ON evenement_portail;
    CREATE POLICY evenement_portail_portail ON evenement_portail FOR SELECT
        USING (portail_voit_site(site_id, current_user));
    EXECUTE format('GRANT SELECT ON evenement_portail TO %I', portail);
END $$;

INSERT INTO politique_conservation (table_nom, duree, colonne_date, decidee_le, source) VALUES
    ('evenement_portail', interval '30 days', 'le', '2026-11-03', 'plan portail v4 / lot S3 : simple réveil du portail, jamais une archive')
ON CONFLICT (table_nom) DO NOTHING;

CREATE OR REPLACE FUNCTION emettre_evenement_portail() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    v_sorte text := TG_ARGV[0];
    v_site  bigint;
    v_ligne text;
    v_evt   bigint;
BEGIN
    IF TG_TABLE_NAME = 'demande' THEN
        v_site := NEW.site_id;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'appel' THEN
        -- Seul un appel urgent réveille le portail (l'urgence est celle de la liste fermée).
        IF NOT EXISTS (SELECT 1 FROM liste_valeur lv
                       WHERE lv.liste = 'degre_urgence' AND lv.code = NEW.degre_urgence AND lv.urgent) THEN
            RETURN NULL;
        END IF;
        v_site := NEW.site_id;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'commentaire' THEN
        IF NEW.appel_id IS NOT NULL THEN
            SELECT site_id INTO v_site FROM appel WHERE id = NEW.appel_id;
        ELSE
            SELECT site_id INTO v_site FROM appel WHERE contact_id = NEW.contact_id ORDER BY debut DESC LIMIT 1;
        END IF;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'incident' THEN
        -- Le lien incident_appel s'écrit après l'incident : sans lieu à cet instant (vu de qui voit tout).
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'action' THEN
        SELECT coalesce((SELECT a.site_id FROM appel a WHERE a.id = NEW.appel_id),
                        (SELECT d.site_id FROM demande d WHERE d.id = NEW.demande_id)) INTO v_site;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'rendez_vous' THEN
        IF NEW.origine <> 'agent' THEN
            RETURN NULL;
        END IF;
        SELECT site_id INTO v_site FROM demande WHERE id = NEW.demande_id;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'journal_modif' THEN
        BEGIN
            v_site := coalesce(NEW.apres ->> 'site_id', NEW.avant ->> 'site_id')::bigint;
        EXCEPTION WHEN others THEN
            v_site := NULL;
        END;
        v_ligne := NEW.id::text;
    ELSIF TG_TABLE_NAME = 'avis' THEN
        SELECT site_id INTO v_site FROM appel WHERE id = NEW.appel_id;
        v_ligne := NEW.id::text;
    ELSE
        RETURN NULL;
    END IF;

    INSERT INTO evenement_portail (tbl, ligne, site_id, sorte)
    VALUES (TG_TABLE_NAME, v_ligne, v_site, v_sorte)
    RETURNING id INTO v_evt;
    PERFORM pg_notify('portail', json_build_object(
        'evt', v_evt, 'table', TG_TABLE_NAME, 'id', v_ligne, 'site_id', v_site, 'sorte', v_sorte)::text);
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS demande_evt_nouvelle ON demande;
CREATE TRIGGER demande_evt_nouvelle AFTER INSERT ON demande
    FOR EACH ROW EXECUTE FUNCTION emettre_evenement_portail('nouvelle');
DROP TRIGGER IF EXISTS demande_evt_assignee ON demande;
CREATE TRIGGER demande_evt_assignee AFTER UPDATE OF assignee_id ON demande
    FOR EACH ROW WHEN (OLD.assignee_id IS DISTINCT FROM NEW.assignee_id)
    EXECUTE FUNCTION emettre_evenement_portail('assignee');
DROP TRIGGER IF EXISTS demande_evt_urgence ON demande;
CREATE TRIGGER demande_evt_urgence AFTER UPDATE OF degre_urgence ON demande
    FOR EACH ROW WHEN (OLD.degre_urgence IS DISTINCT FROM NEW.degre_urgence)
    EXECUTE FUNCTION emettre_evenement_portail('urgence');
DROP TRIGGER IF EXISTS appel_evt_urgent ON appel;
CREATE TRIGGER appel_evt_urgent AFTER INSERT ON appel
    FOR EACH ROW WHEN (NEW.degre_urgence IS NOT NULL)
    EXECUTE FUNCTION emettre_evenement_portail('urgent');
DROP TRIGGER IF EXISTS commentaire_evt ON commentaire;
CREATE TRIGGER commentaire_evt AFTER INSERT ON commentaire
    FOR EACH ROW EXECUTE FUNCTION emettre_evenement_portail('commentaire');
DROP TRIGGER IF EXISTS incident_evt ON incident;
CREATE TRIGGER incident_evt AFTER INSERT ON incident
    FOR EACH ROW EXECUTE FUNCTION emettre_evenement_portail('incident');
DROP TRIGGER IF EXISTS action_evt_echec_insert ON action;
CREATE TRIGGER action_evt_echec_insert AFTER INSERT ON action
    FOR EACH ROW WHEN (NEW.statut = 'echec')
    EXECUTE FUNCTION emettre_evenement_portail('echec');
DROP TRIGGER IF EXISTS action_evt_echec ON action;
CREATE TRIGGER action_evt_echec AFTER UPDATE OF statut ON action
    FOR EACH ROW WHEN (NEW.statut = 'echec' AND OLD.statut IS DISTINCT FROM NEW.statut)
    EXECUTE FUNCTION emettre_evenement_portail('echec');
DROP TRIGGER IF EXISTS rendez_vous_evt ON rendez_vous;
CREATE TRIGGER rendez_vous_evt AFTER INSERT ON rendez_vous
    FOR EACH ROW WHEN (NEW.origine = 'agent')
    EXECUTE FUNCTION emettre_evenement_portail('pose');
DROP TRIGGER IF EXISTS journal_modif_evt ON journal_modif;
CREATE TRIGGER journal_modif_evt AFTER INSERT ON journal_modif
    FOR EACH ROW EXECUTE FUNCTION emettre_evenement_portail('reglage');
DROP TRIGGER IF EXISTS avis_evt ON avis;
CREATE TRIGGER avis_evt AFTER INSERT ON avis
    FOR EACH ROW EXECUTE FUNCTION emettre_evenement_portail('avis');

-- ---------------------------------------------------------------------
--  6. Un avis de 1 ou 2 étoiles avec rappel demandé crée une demande « à rappeler » (type « rappel »),
--     liée à la conversation (si elle n'avait pas de demande). Elle réveille le portail comme toute demande.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION demande_apres_avis() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    v_appel   appel%ROWTYPE;
    v_demande bigint;
BEGIN
    IF NOT (NEW.rappel_demande AND NEW.etoiles <= 2) THEN
        RETURN NULL;
    END IF;
    SELECT * INTO v_appel FROM appel WHERE id = NEW.appel_id;
    INSERT INTO demande (contact_id, site_id, type, priorite, resume, creee_le)
    VALUES (v_appel.contact_id, v_appel.site_id, 'rappel', 1,
            'Rappel demandé après un avis de ' || NEW.etoiles || ' étoile' || CASE WHEN NEW.etoiles > 1 THEN 's' ELSE '' END
            || ' sur la conversation du site.', now())
    RETURNING id INTO v_demande;
    UPDATE appel SET demande_id = v_demande WHERE id = NEW.appel_id AND demande_id IS NULL;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS avis_demande_de_rappel ON avis;
CREATE TRIGGER avis_demande_de_rappel AFTER INSERT ON avis
    FOR EACH ROW EXECUTE FUNCTION demande_apres_avis();

-- ---------------------------------------------------------------------
--  7. Le visiteur du site : son contact (retrouvé par son téléphone puis son mail, créé sinon), son avis,
--     sa demande de rappel quand le plafond du mois est atteint. Rien n'est écrit pour une conversation qui
--     n'existe pas : l'avis arrivé avant la conversation attend dans le run et entre avec elle (recevoir_appel).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION contact_du_visiteur(p jsonb) RETURNS bigint
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_mail text := nullif(lower(btrim(coalesce(p ->> 'mail', ''))), '');
    v_tel  text := nullif(btrim(coalesce(p ->> 'telephone', '')), '');
    v_nom  text := nullif(left(btrim(coalesce(p ->> 'nom', '')), 200), '');
    v_id   bigint;
BEGIN
    IF v_tel IS NOT NULL THEN
        SELECT contact_id INTO v_id FROM telephone WHERE numero = v_tel;
    END IF;
    IF v_id IS NULL AND v_mail IS NOT NULL THEN
        SELECT id INTO v_id FROM contact WHERE lower(btrim(mail)) = v_mail ORDER BY id LIMIT 1;
    END IF;
    IF v_id IS NULL THEN
        IF v_tel IS NULL AND v_mail IS NULL THEN
            RETURN NULL;
        END IF;
        INSERT INTO contact (nom, mail) VALUES (v_nom, v_mail) RETURNING id INTO v_id;
    ELSE
        UPDATE contact SET nom = coalesce(nom, v_nom), mail = coalesce(mail, v_mail), derniere_activite = now()
        WHERE id = v_id;
    END IF;
    IF v_tel IS NOT NULL THEN
        INSERT INTO telephone (numero, contact_id) VALUES (v_tel, v_id)
        ON CONFLICT (numero) DO UPDATE SET contact_id = coalesce(telephone.contact_id, EXCLUDED.contact_id);
    END IF;
    RETURN v_id;
END $$;

CREATE OR REPLACE FUNCTION noter_avis(p_run integer, p jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_appel   bigint;
    v_contact bigint;
    v_nouveau bigint;
    v_publie  boolean := coalesce((p ->> 'publication_acceptee')::boolean, false);
BEGIN
    SELECT id, contact_id INTO v_appel, v_contact FROM appel WHERE dograh_run_id = p_run;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('ecrit', false);
    END IF;
    -- Les coordonnées laissées avec l'avis : celles du contact de la conversation, ou un contact nouveau.
    IF jsonb_typeof(p -> 'contact') = 'object' THEN
        IF v_contact IS NULL THEN
            v_contact := contact_du_visiteur(p -> 'contact');
            UPDATE appel SET contact_id = v_contact WHERE id = v_appel AND contact_id IS NULL;
        ELSE
            UPDATE contact SET mail = coalesce(mail, nullif(lower(btrim(coalesce(p -> 'contact' ->> 'mail', ''))), '')),
                               nom = coalesce(nom, nullif(left(btrim(coalesce(p -> 'contact' ->> 'nom', '')), 200), ''))
            WHERE id = v_contact;
            IF nullif(btrim(coalesce(p -> 'contact' ->> 'telephone', '')), '') IS NOT NULL THEN
                INSERT INTO telephone (numero, contact_id) VALUES (btrim(p -> 'contact' ->> 'telephone'), v_contact)
                ON CONFLICT (numero) DO NOTHING;
            END IF;
        END IF;
    END IF;
    INSERT INTO avis (appel_id, etoiles, obtenu, raisons, commentaire, rappel_demande,
                      publication_acceptee, consentement_le)
    VALUES (v_appel, (p ->> 'etoiles')::smallint, (p ->> 'obtenu')::boolean,
            CASE WHEN jsonb_typeof(p -> 'raisons') = 'array'
                 THEN ARRAY(SELECT left(x, 120) FROM jsonb_array_elements_text(p -> 'raisons') AS t(x) LIMIT 10)
                 ELSE '{}'::text[] END,
            nullif(left(btrim(coalesce(p ->> 'commentaire', '')), 2000), ''),
            coalesce((p ->> 'rappel_demande')::boolean, false),
            v_publie, CASE WHEN v_publie THEN now() END)
    ON CONFLICT (appel_id) DO NOTHING
    RETURNING id INTO v_nouveau;
    RETURN jsonb_build_object('ecrit', true, 'nouveau', v_nouveau IS NOT NULL);
END $$;

-- Plafond du mois atteint : le visiteur laisse ses coordonnées, une demande « à rappeler » entre dans la base
-- (sans conversation). Un établissement inconnu laisse la demande sans lieu.
CREATE OR REPLACE FUNCTION demander_rappel_site(p jsonb) RETURNS jsonb
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    v_contact bigint := contact_du_visiteur(coalesce(p -> 'contact', '{}'::jsonb));
    v_site    bigint;
    v_demande bigint;
BEGIN
    IF v_contact IS NULL THEN
        RAISE EXCEPTION 'demander_rappel_site : ni téléphone ni mail';
    END IF;
    SELECT id INTO v_site FROM site WHERE cle = nullif(p ->> 'etablissement', '');
    INSERT INTO demande (contact_id, site_id, type, priorite, resume, creee_le)
    VALUES (v_contact, v_site, 'rappel', 1,
            left('Rappel demandé depuis le site (l''agent n''était plus disponible ce mois-ci).'
                 || coalesce(' Page : ' || nullif(left(p ->> 'chemin', 300), ''), '')
                 || coalesce(' Message : ' || nullif(left(btrim(coalesce(p ->> 'message', '')), 1000), ''), ''), 2000),
            now())
    RETURNING id INTO v_demande;
    RETURN jsonb_build_object('demande_id', v_demande, 'contact_id', v_contact);
END $$;

INSERT INTO schema_version (version, description) VALUES
    (22, 'Conversations du site : appel.page et mode_site, canal site, contact par mail, avis et v_portail_avis, événements du portail (NOTIFY portail), rappel après un mauvais avis, indicateurs par canal')
ON CONFLICT (version) DO NOTHING;
