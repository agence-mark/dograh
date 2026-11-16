-- =====================================================================
--  032 : « carte à la livraison » entre dans la liste fermée des moyens de paiement du classeur (chantier module-restauration, lot 26, M19).
--  La caisse de démo le permettait déjà (``carte_livraison``) mais la base le refusait. Additive : la contrainte de ``resto_reglage.moyens_paiement`` est
--  remplacée par la même liste plus ce moyen ; aucune ligne n'est touchée.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage DROP CONSTRAINT IF EXISTS resto_reglage_moyens_paiement_check;
ALTER TABLE resto_reglage ADD CONSTRAINT resto_reglage_moyens_paiement_check
    CHECK (moyens_paiement <@ ARRAY['carte', 'especes', 'titre_restaurant', 'cheque', 'en_ligne', 'carte_livraison']::text[]);

INSERT INTO schema_version (version, description) VALUES
    (32, 'Module Restauration : « carte à la livraison » (carte_livraison) dans la liste fermée des moyens de paiement de resto_reglage')
ON CONFLICT (version) DO NOTHING;
