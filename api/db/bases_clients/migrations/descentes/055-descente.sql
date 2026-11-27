-- =====================================================================
--  Descente de la 055 (chantier Partie 1, lot 8b-1b). À jouer AVANT la descente de la 054. Idempotente, et rejouable sur une base dont les tables
--  du module sont déjà descendues. L'index du filet redevient celui de la 054, la colonne de l'alerte est retirée (une ligne alertée redevient lue par le filet).
-- =====================================================================
SET search_path = mark;

DO $$
BEGIN
    IF to_regclass('mark.resto_commande') IS NOT NULL THEN
        DROP INDEX IF EXISTS mark.resto_commande_retenue_idx;
        CREATE INDEX IF NOT EXISTS resto_commande_retenue_idx ON mark.resto_commande (site_id, maj_le, numero) WHERE statut = 'retenue' AND appel_id IS NOT NULL;
        ALTER TABLE mark.resto_commande DROP COLUMN IF EXISTS filet_alerte_le;
    END IF;
END $$;

DELETE FROM schema_version WHERE version = 55;
