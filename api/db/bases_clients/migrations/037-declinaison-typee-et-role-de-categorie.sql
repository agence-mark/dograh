-- =====================================================================
--  037 : la déclinaison typée, le rôle d'une catégorie, le lexique et le produit du moment, les signalements de carte
--  (chantier Partie 1, lot 8 : briques article et déclinaison ; E17, E29, D9). Additive : des colonnes facultatives et une table,
--  rien d'existant n'est modifié ; NULL = donnée absente (aucun changement de comportement, une donnée absente ne bloque jamais l'agent).
--
--  * ``resto_declinaison.type`` : ce que la déclinaison distingue (taille, variante, nombre de pièces, contenance, base, grammage, autre) ;
--    ``libelle_question`` : le mot de la question (« version », « pièces ») quand le restaurateur le dit ; ``quotas`` : par groupe de choix,
--    le minimum et le maximum que CETTE déclinaison fixe (``{"<ref du groupe>": {"min": 1, "max": 3}}``, DEC2).
--  * ``resto_categorie.role`` : ce qu'une catégorie est pour la vente en plus (principal, boisson, dessert, accompagnement, jamais proposé, autre).
--  * ``resto_surcouche`` (écrite par une personne, jamais écrasée par un import de caisse) : ``genre`` et ``nom_commun`` d'un produit (accorder
--    « une Napoli », « deux tiramisus »), ``du_moment`` et ``texte_du_jour`` (le plat du jour, ART3).
--  * ``resto_signalement_carte`` : ce que la carte exprime d'une règle que l'agent ne sait pas appliquer (E29), à préciser au portail ; un
--    signalement par couple (établissement, produit, texte), rejouable sans effet double. Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_declinaison ADD COLUMN IF NOT EXISTS type text
    CHECK (type IS NULL OR type IN ('taille', 'variante', 'pieces', 'contenance', 'base', 'grammage', 'autre'));
ALTER TABLE resto_declinaison ADD COLUMN IF NOT EXISTS libelle_question text CHECK (libelle_question IS NULL OR btrim(libelle_question) <> '');
ALTER TABLE resto_declinaison ADD COLUMN IF NOT EXISTS quotas jsonb;

ALTER TABLE resto_categorie ADD COLUMN IF NOT EXISTS role text
    CHECK (role IS NULL OR role IN ('principal', 'boisson', 'dessert', 'accompagnement', 'jamais_propose', 'autre'));

ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS genre text CHECK (genre IS NULL OR genre IN ('m', 'f'));
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS nom_commun boolean;
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS du_moment boolean NOT NULL DEFAULT false;
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS texte_du_jour text CHECK (texte_du_jour IS NULL OR btrim(texte_du_jour) <> '');

CREATE TABLE IF NOT EXISTS resto_signalement_carte (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id     bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    produit_ref text NOT NULL CHECK (btrim(produit_ref) <> ''),
    texte       text NOT NULL CHECK (btrim(texte) <> '' AND length(texte) <= 300),
    cree_le     timestamptz NOT NULL
);
-- Un signalement par couple (établissement, produit, texte) : rejouable sans effet double ; la lecture de l'écran est paginée par id décroissant.
CREATE UNIQUE INDEX IF NOT EXISTS resto_signalement_carte_unique_idx ON resto_signalement_carte (site_id, produit_ref, texte);
CREATE INDEX IF NOT EXISTS resto_signalement_carte_site_idx ON resto_signalement_carte (site_id, id DESC);

DO $$
BEGIN
    -- Le fork l'écrit (l'agent signale), le portail le lit seulement (RLS par établissement, comme les commandes).
    PERFORM resto_droits('resto_signalement_carte', 'lecture');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (37, 'Module Restauration : déclinaison typée (type, libellé de question, quotas), rôle de catégorie, genre, nom commun et produit du moment en surcouche, signalements de carte (briques article et déclinaison)')
ON CONFLICT (version) DO NOTHING;
