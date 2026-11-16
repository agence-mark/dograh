-- =====================================================================
--  Descente de la 032 (module Restauration, lot 26, M19). À jouer EN PREMIER (avant 031, 030…). Idempotente.
--  Retire « carte à la livraison » de la liste fermée. Les réglages qui l'acceptaient le perdent (seule donnée touchée : ce moyen, retiré du tableau) :
--  sans cela la contrainte d'avant refuserait leur ligne.
-- =====================================================================
SET search_path = mark;

-- Rejouable : la table peut déjà avoir disparu (descente de la 027 jouée avant).
DO $$
BEGIN
    IF to_regclass('mark.resto_reglage') IS NOT NULL THEN
        UPDATE resto_reglage SET moyens_paiement = array_remove(moyens_paiement, 'carte_livraison') WHERE 'carte_livraison' = ANY(moyens_paiement);
        ALTER TABLE resto_reglage DROP CONSTRAINT IF EXISTS resto_reglage_moyens_paiement_check;
        ALTER TABLE resto_reglage ADD CONSTRAINT resto_reglage_moyens_paiement_check
            CHECK (moyens_paiement <@ ARRAY['carte', 'especes', 'titre_restaurant', 'cheque', 'en_ligne']::text[]);
    END IF;
END $$;

DELETE FROM schema_version WHERE version = 32;
