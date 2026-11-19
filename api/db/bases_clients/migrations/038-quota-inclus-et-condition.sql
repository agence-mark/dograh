-- =====================================================================
--  038 : le quota inclus d'un groupe de choix et la condition d'un groupe (chantier Partie 1, lot 9 : briques groupes d'options ; E29, D9, D31).
--  Additive : trois colonnes facultatives sur ``resto_groupe_choix``, rien d'existant n'est modifié ; NULL = non dit (aucun changement de comportement).
--
--  * ``inclus`` : le nombre d'éléments compris dans le prix (OPT3), les suivants se paient. Le nombre vit SUR LE GROUPE ; une table déclinaison x groupe
--    (``resto_declinaison.quotas``, 037) le surcharge pour une taille ; une formule ne le change jamais (D31).
--  * ``prix_au_dela`` : en centimes, le prix de chaque élément au-delà de ``inclus`` ; NULL : le prix de l'option.
--  * ``si_option`` : le code de caisse d'une option qui fait apparaître ce groupe (OPT6, « une vinaigrette si une salade ») ; NULL : le groupe est toujours là.
--  Les droits et la sécurité par ligne de la table ne changent pas. Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_groupe_choix ADD COLUMN IF NOT EXISTS inclus integer CHECK (inclus IS NULL OR inclus >= 0);
ALTER TABLE resto_groupe_choix ADD COLUMN IF NOT EXISTS prix_au_dela integer CHECK (prix_au_dela IS NULL OR prix_au_dela >= 0);
ALTER TABLE resto_groupe_choix ADD COLUMN IF NOT EXISTS si_option text CHECK (si_option IS NULL OR btrim(si_option) <> '');

INSERT INTO schema_version (version, description) VALUES
    (38, 'Module Restauration : quota inclus, prix au-delà et condition d''un groupe de choix (briques groupes d''options)')
ON CONFLICT (version) DO NOTHING;
