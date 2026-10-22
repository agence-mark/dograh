-- =====================================================================
--  021 : un établissement a ses propres règles complètes (chantier
--  cloture-code-avant-migration, F-8, règle d'Evan du 22/10). Additive
--  seulement (CREATE OR REPLACE, INSERT ... ON CONFLICT DO NOTHING, champs
--  vides remplis) : rien renommé, rien retiré, aucune valeur posée remplacée.
--
--  La règle : aucune valeur n'est héritée de l'organisation. La valeur
--  commune (la ligne sans établissement) sert seulement à préremplir un
--  NOUVEL établissement, et aux appels qui ne servent aucun établissement.
--  Ensuite, chaque établissement vit sa vie : un champ vide est vide (le
--  défaut du code pour le planificateur, rien pour une phrase).
--
--  - preremplir_etablissement(site) : recopie dans un établissement les
--    valeurs communes qu'il n'a pas : règles du planificateur et fenêtre du
--    tour de rôle (reglage_planificateur, champ par champ), types de rendez-vous
--    (une copie de chaque type commun dont il n'a pas le code, avec son site_id),
--    réglages terrain des modules (module_reglage, clé par clé, seulement les
--    clés que le module déclare), contenus des phrases placées au niveau de
--    l'établissement (phrase_site). Ne remplace jamais une valeur posée. Rend le
--    nombre de lignes écrites. Appelée par Dograh à la création d'un lieu
--    (api/db/bases_clients/referentiel.py) et ci-dessous.
--  - Pour chaque établissement EXISTANT (site.cle posé, actif ou non) : la même
--    recopie, pour qu'aucun client n'entende autre chose au téléphone (ce qu'il
--    héritait y est écrit). Journalisée comme le reste du référentiel
--    (journal_modif, module_reglage_historique), mark.auteur = cette migration.
--  Rejouable : un second passage ne trouve plus rien à écrire.
--
--  Ce qui vit dans Dograh (horaires, adresse, annonces des établissements
--  quand la base est la source : colonnes de site) n'a pas de valeur commune
--  ici : le script api/scripts/mark/etablissements_complets.py le recopie.
-- =====================================================================
SET search_path = mark;

SELECT set_config('mark.auteur', 'migration 021-etablissements-complets', true);

CREATE OR REPLACE FUNCTION preremplir_etablissement(cible bigint) RETURNS integer
LANGUAGE plpgsql SET search_path = mark AS $$
DECLARE
    ecrites integer := 0;
    n       integer;
BEGIN
    IF cible IS NULL THEN
        RETURN 0;
    END IF;

    -- 1. Les règles du planificateur et la fenêtre du tour de rôle : chaque champ vide de
    --    l'établissement prend la valeur commune (une ligne commune sans aucune valeur : rien).
    INSERT INTO reglage_planificateur (site_id, nombre_creneaux, delai_minimal_h, horizon_jours, pas_min,
        plages, zone_rayon_km, zone_communes, trajets_comptes, coefficient_trajet, vitesse_kmh,
        repartition, repli, personne_visible, jours_feries, fenetre_equite_jours)
    SELECT cible, o.nombre_creneaux, o.delai_minimal_h, o.horizon_jours, o.pas_min,
        o.plages, o.zone_rayon_km, o.zone_communes, o.trajets_comptes, o.coefficient_trajet, o.vitesse_kmh,
        o.repartition, o.repli, o.personne_visible, o.jours_feries, o.fenetre_equite_jours
    FROM reglage_planificateur o
    WHERE o.site_id IS NULL
      AND num_nonnulls(o.nombre_creneaux, o.delai_minimal_h, o.horizon_jours, o.pas_min, o.plages,
                       o.zone_rayon_km, o.zone_communes, o.trajets_comptes, o.coefficient_trajet,
                       o.vitesse_kmh, o.repartition, o.repli, o.personne_visible, o.jours_feries,
                       o.fenetre_equite_jours) > 0
    ON CONFLICT ((coalesce(site_id, 0))) DO UPDATE SET
        nombre_creneaux      = coalesce(reglage_planificateur.nombre_creneaux, EXCLUDED.nombre_creneaux),
        delai_minimal_h      = coalesce(reglage_planificateur.delai_minimal_h, EXCLUDED.delai_minimal_h),
        horizon_jours        = coalesce(reglage_planificateur.horizon_jours, EXCLUDED.horizon_jours),
        pas_min              = coalesce(reglage_planificateur.pas_min, EXCLUDED.pas_min),
        plages               = coalesce(reglage_planificateur.plages, EXCLUDED.plages),
        zone_rayon_km        = coalesce(reglage_planificateur.zone_rayon_km, EXCLUDED.zone_rayon_km),
        zone_communes        = coalesce(reglage_planificateur.zone_communes, EXCLUDED.zone_communes),
        trajets_comptes      = coalesce(reglage_planificateur.trajets_comptes, EXCLUDED.trajets_comptes),
        coefficient_trajet   = coalesce(reglage_planificateur.coefficient_trajet, EXCLUDED.coefficient_trajet),
        vitesse_kmh          = coalesce(reglage_planificateur.vitesse_kmh, EXCLUDED.vitesse_kmh),
        repartition          = coalesce(reglage_planificateur.repartition, EXCLUDED.repartition),
        repli                = coalesce(reglage_planificateur.repli, EXCLUDED.repli),
        personne_visible     = coalesce(reglage_planificateur.personne_visible, EXCLUDED.personne_visible),
        jours_feries         = coalesce(reglage_planificateur.jours_feries, EXCLUDED.jours_feries),
        fenetre_equite_jours = coalesce(reglage_planificateur.fenetre_equite_jours, EXCLUDED.fenetre_equite_jours)
    WHERE (reglage_planificateur.nombre_creneaux IS NULL AND EXCLUDED.nombre_creneaux IS NOT NULL)
       OR (reglage_planificateur.delai_minimal_h IS NULL AND EXCLUDED.delai_minimal_h IS NOT NULL)
       OR (reglage_planificateur.horizon_jours IS NULL AND EXCLUDED.horizon_jours IS NOT NULL)
       OR (reglage_planificateur.pas_min IS NULL AND EXCLUDED.pas_min IS NOT NULL)
       OR (reglage_planificateur.plages IS NULL AND EXCLUDED.plages IS NOT NULL)
       OR (reglage_planificateur.zone_rayon_km IS NULL AND EXCLUDED.zone_rayon_km IS NOT NULL)
       OR (reglage_planificateur.zone_communes IS NULL AND EXCLUDED.zone_communes IS NOT NULL)
       OR (reglage_planificateur.trajets_comptes IS NULL AND EXCLUDED.trajets_comptes IS NOT NULL)
       OR (reglage_planificateur.coefficient_trajet IS NULL AND EXCLUDED.coefficient_trajet IS NOT NULL)
       OR (reglage_planificateur.vitesse_kmh IS NULL AND EXCLUDED.vitesse_kmh IS NOT NULL)
       OR (reglage_planificateur.repartition IS NULL AND EXCLUDED.repartition IS NOT NULL)
       OR (reglage_planificateur.repli IS NULL AND EXCLUDED.repli IS NOT NULL)
       OR (reglage_planificateur.personne_visible IS NULL AND EXCLUDED.personne_visible IS NOT NULL)
       OR (reglage_planificateur.jours_feries IS NULL AND EXCLUDED.jours_feries IS NOT NULL)
       OR (reglage_planificateur.fenetre_equite_jours IS NULL AND EXCLUDED.fenetre_equite_jours IS NOT NULL);
    GET DIAGNOSTICS n = ROW_COUNT;
    ecrites := ecrites + n;

    -- 2. Les types de rendez-vous : une copie de chaque type commun dont l'établissement n'a pas le
    --    code (proposé ou non, comme le commun). Avant la règle, ses types propres remplaçaient les
    --    communs du même code et s'y ajoutaient : il propose désormais exactement le même ensemble.
    INSERT INTO type_rendez_vous (code, site_id, libelle, duree_min, sujet_id,
        marge_avant_min, marge_apres_min, actif, ordre)
    SELECT t.code, cible, t.libelle, t.duree_min, t.sujet_id,
        t.marge_avant_min, t.marge_apres_min, t.actif, t.ordre
    FROM type_rendez_vous t
    WHERE t.site_id IS NULL
    ORDER BY t.ordre, t.id
    ON CONFLICT (code, (coalesce(site_id, 0))) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    ecrites := ecrites + n;

    -- 3. Les réglages terrain des modules : chaque clé commune que l'établissement n'a pas, si le
    --    module la déclare encore (le déclencheur de la 020 refuserait les autres).
    INSERT INTO module_reglage (module_code, site_id, cle, valeur)
    SELECT r.module_code, cible, r.cle, r.valeur
    FROM module_reglage r
    WHERE r.site_id IS NULL
      AND EXISTS (
          SELECT 1 FROM module m, jsonb_array_elements(m.reglages_terrain) d
          WHERE m.code = r.module_code AND d ->> 'cle' = r.cle AND d ->> 'lieu' = 'module_reglage'
      )
    ON CONFLICT (module_code, cle, (coalesce(site_id, 0))) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    ecrites := ecrites + n;

    -- 4. Les contenus des phrases placées au niveau de l'établissement (un contenu commun vide : rien).
    INSERT INTO phrase_site (variable, site_id, contenu)
    SELECT p.variable, cible, btrim(p.contenu)
    FROM phrase p
    WHERE p.niveau = 'etablissement' AND btrim(p.contenu) <> ''
    ON CONFLICT (variable, site_id) DO NOTHING;
    GET DIAGNOSTICS n = ROW_COUNT;
    ecrites := ecrites + n;

    RETURN ecrites;
END $$;

-- Les établissements existants : ce qu'ils héritaient est écrit chez eux (zéro changement au téléphone).
DO $$
DECLARE s record;
BEGIN
    FOR s IN SELECT id FROM site WHERE cle IS NOT NULL ORDER BY id LOOP
        PERFORM preremplir_etablissement(s.id);
    END LOOP;
END $$;

COMMENT ON TABLE reglage_planificateur IS
    'Règles du planificateur. Ligne sans établissement : valeurs de départ d''un nouvel établissement et règles des appels sans établissement. Ligne d''un établissement : ses règles complètes (vide = défaut du code), rien n''est hérité (021).';
COMMENT ON TABLE type_rendez_vous IS
    'Types de rendez-vous. Sans établissement : types de départ d''un nouvel établissement et types des appels sans établissement. D''un établissement : les siens seuls (021).';
COMMENT ON TABLE module_reglage IS
    'Réglages terrain des modules. Sans établissement : valeurs de départ et appels sans établissement. D''un établissement : les siens seuls, rien n''est hérité (021).';
COMMENT ON TABLE phrase_site IS
    'Contenu d''une phrase placée au niveau de l''établissement, pour cet établissement. Absent : rien n''est dit (021) ; le contenu de phrase est la valeur de départ.';

INSERT INTO schema_version (version, description) VALUES
    (21, 'Établissements complets : aucune valeur héritée de l''organisation ; valeurs communes recopiées dans chaque établissement existant et à la création (preremplir_etablissement)')
ON CONFLICT (version) DO NOTHING;
