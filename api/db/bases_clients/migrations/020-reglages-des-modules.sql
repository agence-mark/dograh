-- =====================================================================
--  020 : les modules de l'agent et leurs réglages terrain (chantier cloture-code-avant-migration,
--  lot F8 ; D120 à D122, M1 à M8, D124). Additive seulement (IF NOT EXISTS, CREATE OR REPLACE,
--  DROP POLICY IF EXISTS) : rien renommé ni retiré.
--
--  - module : le catalogue des modules tel que le registre du fork le déclare
--    (api/services/modules/registre.py), ÉCRIT par Dograh, jamais saisi : code, libellé, ses
--    réglages terrain déclarés (où vit chacun) et les tables qui les portent.
--  - module_agent : sur quels agents le module est allumé, CALCULÉ par Dograh (leur version
--    publiée), comme objet_agent_utilisation (019).
--  - module_reglage : le magasin commun des réglages terrain d'un module qui n'a pas ses propres
--    tables. Un jeu par organisation (site_id vide) avec des valeurs par établissement (vide =
--    hérité), comme le planificateur. Seule une clé DÉCLARÉE par le module s'y écrit (aucun réglage
--    inventé : à la 020, aucun module n'en déclare ; les réglages terrain du planificateur restent
--    dans ses tables 010 et 013, déjà journalisés dans journal_modif et v_portail_historique).
--  - module_reglage_historique : chaque changement de module_reglage (qui, quand, avant, après), par
--    déclencheur, JAMAIS effacé (D111, motif de la 019).
--  - v_portail_modules : ce que le portail affiche (D121) : un module allumé sur au moins un agent
--    rattaché au portail ET porteur de réglages terrain.
--
--  Règle du 22/10 : Dograh (le rôle d'écriture) fait tout ; la seule garde est celle du rôle
--  <base>_portail : catalogue en lecture, valeurs par établissement (motif de la 015).
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  1. Les tables.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS module (
    code              text PRIMARY KEY CHECK (code ~ '^[a-z][a-z0-9_]{1,39}$'),
    libelle           text NOT NULL CHECK (btrim(libelle) <> ''),
    -- [{"cle": ..., "bloc": ..., "lieu": table, "modifiable": bool}, ...] : ce que le registre déclare.
    reglages_terrain  jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(reglages_terrain) = 'array'),
    a_reglages_terrain boolean GENERATED ALWAYS AS (jsonb_array_length(reglages_terrain) > 0) STORED,
    modifie_le        timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS module_agent (
    module_code  text NOT NULL REFERENCES module(code) ON DELETE CASCADE,
    agent_id     bigint NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    PRIMARY KEY (module_code, agent_id)
);

CREATE TABLE IF NOT EXISTS module_reglage (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    module_code  text NOT NULL REFERENCES module(code),
    site_id      bigint REFERENCES site(id) ON DELETE CASCADE,   -- vide = toute l'organisation
    cle          text NOT NULL CHECK (cle ~ '^[a-z][a-z0-9_]{0,62}$'),
    valeur       jsonb NOT NULL,
    modifie_le   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS module_reglage_cle_site_idx
    ON module_reglage (module_code, cle, coalesce(site_id, 0));

-- Sans clé étrangère : l'historique survit au réglage (D111, jamais effacé).
CREATE TABLE IF NOT EXISTS module_reglage_historique (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    module_code  text NOT NULL,
    site_id      bigint,
    ligne_id     bigint NOT NULL,
    operation    text NOT NULL,
    avant        jsonb,
    apres        jsonb,
    auteur       text NOT NULL,
    le           timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS module_reglage_historique_module ON module_reglage_historique (module_code, id);

-- ---------------------------------------------------------------------
--  2. Les déclencheurs : clé déclarée, historique, historique gardé.
-- ---------------------------------------------------------------------

-- Une valeur ne s'écrit que sous une clé que le module DÉCLARE dans module_reglage (aucun réglage
-- inventé, pour Dograh comme pour le portail) ; le module et la clé d'une ligne ne changent pas.
CREATE OR REPLACE FUNCTION module_reglage_avant() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND (NEW.module_code IS DISTINCT FROM OLD.module_code OR NEW.cle IS DISTINCT FROM OLD.cle
                             OR NEW.site_id IS DISTINCT FROM OLD.site_id) THEN
        RAISE EXCEPTION 'module_reglage : le module, la clé et l''établissement d''un réglage ne changent pas'
            USING ERRCODE = 'check_violation';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM module m, jsonb_array_elements(m.reglages_terrain) d
        WHERE m.code = NEW.module_code AND d ->> 'cle' = NEW.cle AND d ->> 'lieu' = 'module_reglage'
    ) THEN
        RAISE EXCEPTION 'module_reglage : « % » n''est pas un réglage terrain déclaré du module %', NEW.cle, NEW.module_code
            USING ERRCODE = 'check_violation';
    END IF;
    NEW.modifie_le := now();
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS module_reglage_avant ON module_reglage;
CREATE TRIGGER module_reglage_avant BEFORE INSERT OR UPDATE ON module_reglage
    FOR EACH ROW EXECUTE FUNCTION module_reglage_avant();

-- L'historique (D111) : qui (mark.auteur posé par l'écrivain, sinon le compte), quand, avant, après.
-- Une écriture qui ne change rien ne s'écrit pas. Puis la notification du référentiel (la copie que
-- lisent les appels se refait), comme pour un objet.
CREATE OR REPLACE FUNCTION journaliser_module_reglage() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = mark AS $$
DECLARE
    ancien  jsonb := CASE WHEN TG_OP IN ('UPDATE', 'DELETE') THEN to_jsonb(OLD) END;
    nouveau jsonb := CASE WHEN TG_OP IN ('INSERT', 'UPDATE') THEN to_jsonb(NEW) END;
    ligne   jsonb;
BEGIN
    IF TG_OP = 'UPDATE' AND (ancien - 'modifie_le') = (nouveau - 'modifie_le') THEN
        RETURN NULL;
    END IF;
    ligne := coalesce(nouveau, ancien);
    INSERT INTO module_reglage_historique (module_code, site_id, ligne_id, operation, avant, apres, auteur)
    VALUES (ligne ->> 'module_code', (ligne ->> 'site_id')::bigint, (ligne ->> 'id')::bigint, lower(TG_OP),
            ancien, nouveau, coalesce(nullif(current_setting('mark.auteur', true), ''), session_user));
    PERFORM pg_notify('mark_referentiel', TG_TABLE_NAME);
    RETURN NULL;
END $$;
DROP TRIGGER IF EXISTS module_reglage_historique ON module_reglage;
CREATE TRIGGER module_reglage_historique AFTER INSERT OR UPDATE OR DELETE ON module_reglage
    FOR EACH ROW EXECUTE FUNCTION journaliser_module_reglage();

CREATE OR REPLACE FUNCTION module_reglage_historique_garde() RETURNS trigger
LANGUAGE plpgsql SET search_path = mark AS $$
BEGIN
    RAISE EXCEPTION 'module_reglage_historique : l''historique des réglages des modules ne s''efface jamais'
        USING ERRCODE = 'insufficient_privilege';
END $$;
DROP TRIGGER IF EXISTS module_reglage_historique_garde ON module_reglage_historique;
CREATE TRIGGER module_reglage_historique_garde BEFORE UPDATE OR DELETE ON module_reglage_historique
    FOR EACH ROW EXECUTE FUNCTION module_reglage_historique_garde();
DROP TRIGGER IF EXISTS module_reglage_historique_garde_vidage ON module_reglage_historique;
CREATE TRIGGER module_reglage_historique_garde_vidage BEFORE TRUNCATE ON module_reglage_historique
    FOR EACH STATEMENT EXECUTE FUNCTION module_reglage_historique_garde();

-- ---------------------------------------------------------------------
--  3. Droits et sécurité par ligne. Dograh (mark_ecriture) : tout. Le portail : le catalogue en
--     lecture, les valeurs de ses établissements (et de toute l'entreprise s'il voit un lieu).
-- ---------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON module, module_agent, module_reglage TO mark_ecriture;
GRANT SELECT, INSERT ON module_reglage_historique TO mark_ecriture;
GRANT USAGE ON SEQUENCE module_reglage_id_seq, module_reglage_historique_id_seq TO mark_ecriture;

DO $$
DECLARE
    portail text := current_database() || '_portail';
BEGIN
    -- Le catalogue et les agents où il est allumé : en lecture (rien n'y est propre à un lieu).
    EXECUTE format('GRANT SELECT ON module, module_agent TO %I', portail);

    ALTER TABLE module_reglage ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS module_reglage_autres ON module_reglage;
    CREATE POLICY module_reglage_autres ON module_reglage USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS module_reglage_portail ON module_reglage;
    CREATE POLICY module_reglage_portail ON module_reglage
        USING (portail_voit_lieu_ou_entreprise(site_id, current_user))
        WITH CHECK (portail_voit_lieu_ou_entreprise(site_id, current_user));
    -- Le client règle la valeur d'une clé déclarée (le déclencheur l'impose) ; il pose ou retire la
    -- valeur d'un établissement qu'il voit (retirer = revenir à l'hérité).
    EXECUTE format('GRANT SELECT, DELETE ON module_reglage TO %I', portail);
    EXECUTE format('GRANT INSERT (module_code, site_id, cle, valeur) ON module_reglage TO %I', portail);
    EXECUTE format('GRANT UPDATE (valeur) ON module_reglage TO %I', portail);
    EXECUTE format('GRANT USAGE ON SEQUENCE module_reglage_id_seq TO %I', portail);

    ALTER TABLE module_reglage_historique ENABLE ROW LEVEL SECURITY;
    DROP POLICY IF EXISTS module_reglage_historique_autres ON module_reglage_historique;
    CREATE POLICY module_reglage_historique_autres ON module_reglage_historique
        USING ((SELECT NOT est_du_portail(current_user)));
    DROP POLICY IF EXISTS module_reglage_historique_portail ON module_reglage_historique;
    CREATE POLICY module_reglage_historique_portail ON module_reglage_historique FOR SELECT
        USING (est_du_portail(current_user) AND portail_voit_lieu_ou_entreprise(site_id, current_user));
    EXECUTE format('GRANT SELECT ON module_reglage_historique TO %I', portail);
END $$;

-- ---------------------------------------------------------------------
--  4. Ce que le portail affiche (D121, M6) : un module allumé sur au moins un agent rattaché au
--     portail (une copie de test n'allume rien, D90) ET porteur de réglages terrain (M5). Il apparaît
--     dès que les deux tiennent et disparaît sinon. « dernier_changement » : le plus récent des
--     changements de ses réglages terrain que ce compte voit, dans module_reglage_historique ou, pour
--     un module qui a ses propres tables, dans journal_modif (motif de v_portail_historique, 017).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION module_tables_terrain(cible text) RETURNS text[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT coalesce(array_agg(DISTINCT d ->> 'lieu'), '{}')
    FROM module m, jsonb_array_elements(m.reglages_terrain) d
    WHERE m.code = cible AND d ->> 'lieu' <> 'module_reglage';
$$;

CREATE OR REPLACE VIEW v_portail_modules AS
SELECT m.code, m.libelle, m.reglages_terrain,
       ARRAY(SELECT a.nom FROM module_agent ma JOIN agent a ON a.id = ma.agent_id
             WHERE ma.module_code = m.code AND a.rattache_le IS NOT NULL ORDER BY a.nom) AS utilise_par,
       greatest(
           (SELECT max(h.le) FROM module_reglage_historique h
            WHERE h.module_code = m.code AND portail_voit_lieu_ou_entreprise(h.site_id, current_user)),
           (SELECT max(j.le) FROM journal_modif j
            WHERE j.table_nom = ANY (module_tables_terrain(m.code))
              AND portail_voit_lieu_ou_entreprise(
                      nullif(coalesce(j.apres ->> 'site_id', j.avant ->> 'site_id'), '')::bigint, current_user))
       ) AS dernier_changement
FROM module m
WHERE est_du_portail(current_user)
  AND m.a_reglages_terrain
  AND EXISTS (SELECT 1 FROM module_agent ma JOIN agent a ON a.id = ma.agent_id
              WHERE ma.module_code = m.code AND a.rattache_le IS NOT NULL);

DO $$
BEGIN
    EXECUTE format('GRANT SELECT ON v_portail_modules TO %I', current_database() || '_portail');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (20, 'Modules de l''agent : catalogue écrit par Dograh, agents où chacun est allumé (calculé), magasin commun des réglages terrain (organisation puis établissement, clé déclarée seulement), historique jamais effacé ; sécurité par ligne du portail par établissement ; v_portail_modules');
