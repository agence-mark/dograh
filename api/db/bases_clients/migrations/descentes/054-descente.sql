-- =====================================================================
--  Descente de la 054 (chantier Partie 1, lot 8b-1a). À jouer AVANT la descente de la 053. Idempotente.
--  Une ligne ``retenue`` redevient ``nouvelle`` (rien n'est perdu : c'est ce que l'ancien code écrivait au « oui », le rattrapage l'envoie),
--  puis la contrainte d'avant la 054 est remise.
-- =====================================================================
SET search_path = mark;

UPDATE resto_commande SET statut = 'nouvelle' WHERE statut = 'retenue';
ALTER TABLE resto_commande DROP CONSTRAINT IF EXISTS resto_commande_statut_check;
ALTER TABLE resto_commande ADD CONSTRAINT resto_commande_statut_check CHECK (statut IN (
    'nouvelle', 'envoyee', 'recue', 'acceptee', 'en_preparation', 'prete', 'terminee',
    'refusee', 'annulee', 'echec'));

DELETE FROM schema_version WHERE version = 54;
