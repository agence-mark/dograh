-- =====================================================================
--  041 : les conditions de vente (chantier Partie 1, lot 12 : briques prix et conditions ; E29, D9).
--  Additive : colonnes facultatives, rien d'existant n'est modifié ; NULL ou vide = non dit (aucun changement de comportement).
--
--  ``disponibilite`` (PRX1) : la plage de jours, d'heures et de dates (``plages.py``), posée sur le produit, la catégorie et l'option (la déclinaison et la
--  formule l'avaient déjà). La clé ``hors_feries`` (PRX2) y vit aussi : ``plages.py`` ignore les clés inconnues, elle ne restreint rien.
--  ``modes`` (PRX3) : les modes où le produit ou l'option se vend ; NULL : tous. ``resto_formule.modes`` est posé par la 040 (lot 11), pas ici.
--  ``resto_option.prix_par_mode`` (PRX4) : comme celui de la déclinaison, ``{"<mode>": centimes}``.
--  ``alcool`` et ``degre`` (PRX6) : dans le format commun (importés) ; l'alcool d'une surcouche (migration 030, posé à l'écran) reste et s'y ajoute.
--  ``frais`` (PRX7) : ``[{"nom", "prix", "code_caisse"?}]`` (consigne, emballage, couverts) ajoutés à la commande avec l'article.
--  ``max_par_commande`` (PRX8), ``delai_minimal_heures`` et ``personnes_min`` (PRX9).
--  Les droits et la sécurité par ligne des tables ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS disponibilite jsonb CHECK (disponibilite IS NULL OR jsonb_typeof(disponibilite) = 'object');
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS modes text[] CHECK (modes IS NULL OR modes <@ ARRAY['emporter', 'livraison', 'sur_place']::text[]);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS alcool boolean NOT NULL DEFAULT false;
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS degre numeric(4, 1) CHECK (degre IS NULL OR (degre >= 0 AND degre <= 100));
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS frais jsonb CHECK (frais IS NULL OR jsonb_typeof(frais) = 'array');
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS max_par_commande integer CHECK (max_par_commande IS NULL OR max_par_commande > 0);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS delai_minimal_heures integer CHECK (delai_minimal_heures IS NULL OR delai_minimal_heures >= 0);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS personnes_min integer CHECK (personnes_min IS NULL OR personnes_min > 0);

ALTER TABLE resto_categorie ADD COLUMN IF NOT EXISTS disponibilite jsonb CHECK (disponibilite IS NULL OR jsonb_typeof(disponibilite) = 'object');

ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS disponibilite jsonb CHECK (disponibilite IS NULL OR jsonb_typeof(disponibilite) = 'object');
ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS modes text[] CHECK (modes IS NULL OR modes <@ ARRAY['emporter', 'livraison', 'sur_place']::text[]);
ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS prix_par_mode jsonb CHECK (prix_par_mode IS NULL OR jsonb_typeof(prix_par_mode) = 'object');

INSERT INTO schema_version (version, description) VALUES
    (41, 'Module Restauration : conditions de vente (disponibilité, modes, alcool, frais, maximum, délai, personnes minimales, prix par mode d''une option)')
ON CONFLICT (version) DO NOTHING;
