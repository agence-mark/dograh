-- =====================================================================
--  039 : le supplément selon la taille, le prix d'un retrait, la règle des moitiés (chantier Partie 1, lot 10 : briques retrait et ajout ; E29, D9).
--  Additive : trois colonnes facultatives, rien d'existant n'est modifié ; NULL = non dit (aucun changement de comportement).
--
--  * ``resto_option.prix_par_declinaison`` (RET2) : le prix de l'option par déclinaison de la ligne (``{"<ref de la déclinaison>": centimes}``) ; une déclinaison absente
--    garde le prix de l'option. Sur le modèle de ``prix_par_mode`` : une colonne jsonb de la ligne, fusion et portée déjà là.
--  * ``resto_option.prix_retrait`` (RET5) : le prix d'un retrait, signé (HubRise ``removed`` avec prix) ; NULL : un retrait ne change pas le prix.
--  * ``resto_reglage.moities_prix`` (RET6) : la règle de prix des moitiés de l'ÉTABLISSEMENT (la plus chère, la moyenne, la somme) ; NULL : la plus chère. Elle était un réglage
--    de l'agent (``commande_moities_prix``) : la carte et son prix sont ceux de l'établissement, une seule source.
--  Les droits et la sécurité par ligne des tables ne changent pas. Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS prix_par_declinaison jsonb;
ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS prix_retrait integer;  -- signé : un retrait qui rend de l'argent est négatif
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS moities_prix text CHECK (moities_prix IS NULL OR moities_prix IN ('plus_chere', 'moyenne', 'somme'));

INSERT INTO schema_version (version, description) VALUES
    (39, 'Module Restauration : supplément par déclinaison, prix d''un retrait, règle des moitiés de l''établissement (briques retrait et ajout)')
ON CONFLICT (version) DO NOTHING;
