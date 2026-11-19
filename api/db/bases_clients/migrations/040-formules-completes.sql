-- =====================================================================
--  040 : les formules lues en entier (chantier Partie 1, lot 11 : briques formules et menus ; E29, D9, D34).
--  Additive : colonnes facultatives, rien d'existant n'est modifié ; NULL ou vide = non dit (aucun changement de comportement).
--
--  ``resto_formule`` :
--  * ``modes`` (FOR7) : les modes où la formule se vend (``emporter``, ``livraison``, ``sur_place``) ; NULL : tous. Le lot 12 (041) pose ``modes`` sur
--    le produit et l'option, jamais sur la formule (vu avec SA-7, 19/11).
--  * ``age_max`` (FOR7) : l'âge maximum dit à la personne, jamais vérifié ; ``public`` (FOR9) : le texte du justificatif, jamais contrôlé.
--  * ``personnes`` (FOR10) : le prix par nombre de personnes (``{"<n>": centimes}``).
--  * ``tailles`` (FOR6) : les tailles de la formule (``[{"nom", "ecart", "declinaisons": {"<nom de ligne>": "<nom de déclinaison>"}}]``), la taille de base comprise.
--  * ``par_lot`` (FOR11) : un lot de N produits à prix fixe, compté sur le panier (N = la quantité de sa ligne).
--  Les clés des lignes (``lignes jsonb``, existant) ne demandent aucune colonne : ``quantite``, ``obligatoire``, ``inclus``, ``exclus``, ``prix_max``, ``supplements``,
--  ``alternatives``, ``a_volonte`` (validées à l'import, ``restauration_carte._lignes_de_la_carte``).
--  ``resto_categorie.inclus`` (FOR13) : ce qui est servi avec chaque produit de la rubrique.
--  Les droits et la sécurité par ligne des tables ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS modes text[]
    CHECK (modes IS NULL OR modes <@ ARRAY['emporter', 'livraison', 'sur_place']::text[]);
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS age_max integer CHECK (age_max IS NULL OR age_max > 0);
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS public text CHECK (public IS NULL OR btrim(public) <> '');
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS personnes jsonb CHECK (personnes IS NULL OR jsonb_typeof(personnes) = 'object');
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS tailles jsonb CHECK (tailles IS NULL OR jsonb_typeof(tailles) = 'array');
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS par_lot boolean NOT NULL DEFAULT false;
ALTER TABLE resto_categorie ADD COLUMN IF NOT EXISTS inclus text[] NOT NULL DEFAULT '{}';

INSERT INTO schema_version (version, description) VALUES
    (40, 'Module Restauration : formules complètes (modes, âge, public, personnes, tailles, lot) et inclus de rubrique (briques formules et menus)')
ON CONFLICT (version) DO NOTHING;
