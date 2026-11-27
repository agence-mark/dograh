-- =====================================================================
--  Descente de la 056 (chantier Partie 1, lot 8b-3, T35). À jouer AVANT la descente de la 055. Idempotente, et rejouable sur une base dont les tables
--  du module sont déjà descendues. La colonne de la marque est retirée.
-- =====================================================================
SET search_path = mark;

DO $$
BEGIN
    IF to_regclass('mark.resto_commande') IS NOT NULL THEN
        ALTER TABLE mark.resto_commande DROP COLUMN IF EXISTS accord_retire_le;
    END IF;
END $$;

DELETE FROM schema_version WHERE version = 56;
