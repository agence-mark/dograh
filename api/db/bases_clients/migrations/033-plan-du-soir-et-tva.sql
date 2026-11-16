-- =====================================================================
--  033 : plan de salle du soir et taux de TVA figés (chantier module-restauration, lot 26, M13 et M14).
--  Additive : une table pour le plan du soir, une pour le récapitulatif par taux, des colonnes de taux, deux fonctions de ventilation.
--
--  M13, ``resto_plan_soir`` : ce que le plan de salle enregistré ne garde pas, les tables RASSEMBLÉES pour un jour (et un service) et les
--  positions du soir. Une ligne par (établissement, jour, service) ; ``service_id`` vide = toute la journée. ``assemblages`` : liste de listes
--  d'identifiants de table (``[[3, 4], [7, 8, 9]]``), chaque liste est UNE table pour le calcul de capacité (couverts min = le plus petit,
--  couverts max = la somme) ; ``positions`` : ``{"<id de table>": {"x": 12.5, "y": 40}}``. Le plan de salle (``resto_table``) n'est jamais touché :
--  « Revenir au plan » = supprimer la ligne. Le portail l'écrit (directe), le fork le lit pour la capacité.
--
--  M14, taux de TVA FIGÉS à la création de la commande, en millièmes de pour cent (10 % = 10000, 5,5 % = 5500, comme ``tva_par_mode`` de la carte) :
--    - ``resto_commande_ligne.taux_tva`` : le taux du produit pour le mode de la commande (vide = la carte ne le disait pas) ;
--    - ``resto_commande.taux_tva_frais`` : le taux des frais de livraison ;
--    - chaque remise de ``resto_commande.remises`` porte ``taux_tva`` (clé de l'objet JSON, pas de colonne).
--  Les prix de la carte sont TTC (contrat comptoir-classeur : le total TTC est calculé chez nous depuis la carte).
--  ``resto_recap_jour_taux`` : le récapitulatif par jour, par mode ET par taux (TTC net des remises, frais compris), sans donnée personnelle,
--  qui survit à la purge comme ``resto_recap_jour``. ``taux`` = -1 : taux inconnu (commandes d'avant cette migration, ou carte muette).
--  ``resto_ventilation_commandes`` : la ventilation des commandes encore là, une ligne par taux ;
--  ``resto_tva_par_jour`` : commandes présentes + récapitulatif des purgées, avec HT et TVA calculés au centime (HT + TVA = TTC).
-- =====================================================================
SET search_path = mark;

-- ---------------------------------------------------------------------
--  M13 : le plan du soir.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS resto_plan_soir (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    jour        date NOT NULL,
    service_id  bigint REFERENCES resto_service(id) ON DELETE CASCADE,
    assemblages jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(assemblages) = 'array'),
    positions   jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(positions) = 'object'),
    maj_le      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS resto_plan_soir_jour_idx ON resto_plan_soir (site_id, jour, coalesce(service_id, 0));

-- ---------------------------------------------------------------------
--  M14 : les taux figés.
-- ---------------------------------------------------------------------
ALTER TABLE resto_commande_ligne ADD COLUMN IF NOT EXISTS taux_tva integer CHECK (taux_tva IS NULL OR taux_tva BETWEEN 0 AND 100000);
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS taux_tva_frais integer CHECK (taux_tva_frais IS NULL OR taux_tva_frais BETWEEN 0 AND 100000);

CREATE TABLE IF NOT EXISTS resto_recap_jour_taux (
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    jour    date NOT NULL,
    mode    text NOT NULL,
    taux    integer NOT NULL CHECK (taux = -1 OR taux BETWEEN 0 AND 100000),
    ttc     integer NOT NULL DEFAULT 0,
    PRIMARY KEY (site_id, jour, mode, taux)
);

-- Les lignes, les frais et les remises des commandes qui ont fait une vente, regroupés par taux. ``p_avant`` : seulement celles créées avant.
-- Invoker : le portail ne voit que ses établissements (RLS), le fork tout.
CREATE OR REPLACE FUNCTION resto_ventilation_commandes(p_site bigint DEFAULT NULL, p_avant timestamptz DEFAULT NULL)
RETURNS TABLE (site_id bigint, jour date, mode text, taux integer, ttc integer)
LANGUAGE sql STABLE AS $$
    WITH c AS (
        SELECT k.numero, k.site_id, k.mode, k.frais, k.taux_tva_frais, k.remises, (k.cree_le AT TIME ZONE s.fuseau)::date AS jour
        FROM resto_commande k JOIN site s ON s.id = k.site_id
        WHERE (p_site IS NULL OR k.site_id = p_site) AND (p_avant IS NULL OR k.cree_le < p_avant)
          AND k.statut NOT IN ('annulee', 'refusee', 'echec')
    ), parts AS (
        SELECT c.site_id, c.jour, c.mode, coalesce(l.taux_tva, -1) AS taux, sum(l.prix_unitaire * l.quantite)::bigint AS ttc
        FROM c JOIN resto_commande_ligne l ON l.numero = c.numero GROUP BY c.site_id, c.jour, c.mode, coalesce(l.taux_tva, -1)
        UNION ALL
        SELECT c.site_id, c.jour, c.mode, coalesce(c.taux_tva_frais, -1), c.frais::bigint FROM c WHERE c.frais <> 0
        UNION ALL
        SELECT c.site_id, c.jour, c.mode, coalesce((r ->> 'taux_tva')::int, -1), -(r ->> 'montant')::bigint
        FROM c CROSS JOIN LATERAL jsonb_array_elements(c.remises) r
    )
    SELECT p.site_id, p.jour, p.mode, p.taux, sum(p.ttc)::int FROM parts p GROUP BY p.site_id, p.jour, p.mode, p.taux HAVING sum(p.ttc) <> 0
$$;

-- Le récapitulatif par jour, mode et taux d'un établissement entre deux jours (inclus) : les commandes encore là + celles que la purge a résumées.
-- HT = TTC / (1 + taux), arrondi au centime sur le TOTAL du taux ; TVA = TTC - HT : HT + TVA = TTC, toujours. Taux inconnu : ni HT ni TVA.
CREATE OR REPLACE FUNCTION resto_tva_par_jour(p_site bigint, p_du date, p_au date)
RETURNS TABLE (jour date, mode text, taux integer, ttc integer, ht integer, tva integer)
LANGUAGE sql STABLE AS $$
    WITH toutes AS (
        SELECT v.jour, v.mode, v.taux, v.ttc FROM resto_ventilation_commandes(p_site) v WHERE v.jour BETWEEN p_du AND p_au
        UNION ALL
        SELECT r.jour, r.mode, r.taux, r.ttc FROM resto_recap_jour_taux r WHERE r.site_id = p_site AND r.jour BETWEEN p_du AND p_au
    ), somme AS (
        SELECT t.jour, t.mode, t.taux, sum(t.ttc)::int AS ttc FROM toutes t GROUP BY t.jour, t.mode, t.taux
    )
    SELECT s.jour, s.mode, s.taux, s.ttc,
           CASE WHEN s.taux < 0 THEN NULL ELSE round(s.ttc * 100000.0 / (100000 + s.taux))::int END,
           CASE WHEN s.taux < 0 THEN NULL ELSE s.ttc - round(s.ttc * 100000.0 / (100000 + s.taux))::int END
    FROM somme s ORDER BY s.jour, s.mode, s.taux
$$;

DO $$
DECLARE portail text := current_database() || '_portail';
BEGIN
    DROP TRIGGER IF EXISTS resto_plan_soir_maj_le ON resto_plan_soir;
    CREATE TRIGGER resto_plan_soir_maj_le BEFORE UPDATE ON resto_plan_soir FOR EACH ROW EXECUTE FUNCTION resto_maj_le();
    DROP TRIGGER IF EXISTS resto_plan_soir_journal ON resto_plan_soir;
    CREATE TRIGGER resto_plan_soir_journal AFTER INSERT OR UPDATE OR DELETE ON resto_plan_soir FOR EACH ROW EXECUTE FUNCTION resto_journaliser();
    PERFORM resto_droits('resto_plan_soir', 'ecriture');   -- le portail l'écrit lui-même (contrat § 1 : salles, tables, plan du soir)
    PERFORM resto_droits('resto_recap_jour_taux', 'lecture');
    REVOKE ALL ON FUNCTION resto_ventilation_commandes(bigint, timestamptz) FROM PUBLIC;
    REVOKE ALL ON FUNCTION resto_tva_par_jour(bigint, date, date) FROM PUBLIC;
    GRANT EXECUTE ON FUNCTION resto_ventilation_commandes(bigint, timestamptz) TO mark_ecriture;
    GRANT EXECUTE ON FUNCTION resto_tva_par_jour(bigint, date, date) TO mark_ecriture;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = portail) THEN
        EXECUTE format('GRANT EXECUTE ON FUNCTION resto_ventilation_commandes(bigint, timestamptz) TO %I', portail);
        EXECUTE format('GRANT EXECUTE ON FUNCTION resto_tva_par_jour(bigint, date, date) TO %I', portail);
    END IF;
END $$;

INSERT INTO schema_version (version, description) VALUES
    (33, 'Module Restauration : plan du soir (tables rassemblées, positions), taux de TVA figés sur lignes, frais et remises, récapitulatif par taux, ventilation HT/TVA')
ON CONFLICT (version) DO NOTHING;
