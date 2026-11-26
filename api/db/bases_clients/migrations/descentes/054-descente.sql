-- =====================================================================
--  Descente de la 054 (chantier Partie 1, lot 8b-1a). À jouer AVANT la descente de la 053. Idempotente, et rejouable sur une base dont les tables
--  du module sont déjà descendues.
--  Une ligne ``retenue`` redevient ``nouvelle`` (rien n'est perdu : c'est ce que l'ancien code écrivait au « oui », le rattrapage l'envoie),
--  puis la contrainte d'avant la 054 est remise, ses deux index et le délai du filet retirés.
-- =====================================================================
SET search_path = mark;

DO $$
BEGIN
    IF to_regclass('mark.resto_commande') IS NOT NULL THEN
        UPDATE mark.resto_commande SET statut = 'nouvelle' WHERE statut = 'retenue';
        ALTER TABLE mark.resto_commande DROP CONSTRAINT IF EXISTS resto_commande_statut_check;
        ALTER TABLE mark.resto_commande ADD CONSTRAINT resto_commande_statut_check CHECK (statut IN (
            'nouvelle', 'envoyee', 'recue', 'acceptee', 'en_preparation', 'prete', 'terminee',
            'refusee', 'annulee', 'echec'));
    END IF;
END $$;
DROP INDEX IF EXISTS resto_commande_retenue_idx;
DROP INDEX IF EXISTS resto_commande_appel_idx;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS filet_retenue_min;

DELETE FROM schema_version WHERE version = 54;
