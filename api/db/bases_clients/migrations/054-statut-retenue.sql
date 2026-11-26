-- =====================================================================
--  054 (chantier Partie 1, lot 8b-1a, E1 ; décision d'Evan du 24/11, plan § 17) : le statut ``retenue``.
--  Au « oui » de la relecture, l'agent écrit la commande en base (son numéro court est dit pendant l'appel) au statut ``retenue`` : elle ne part
--  en caisse qu'à la fin de l'appel (``retenue -> nouvelle`` puis l'envoi) ; jamais réaccordée, elle passe ``annulee``. Le rattrapage ne lit que
--  ``nouvelle`` et ``envoyee`` : il n'y touche pas. En ajout seulement : la contrainte accepte une valeur de plus. Idempotente.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande DROP CONSTRAINT IF EXISTS resto_commande_statut_check;
ALTER TABLE resto_commande ADD CONSTRAINT resto_commande_statut_check CHECK (statut IN (
    'retenue', 'nouvelle', 'envoyee', 'recue', 'acceptee', 'en_preparation', 'prete', 'terminee',
    'refusee', 'annulee', 'echec'));

INSERT INTO schema_version (version, description) VALUES
    (54, 'Module Restauration : statut retenue (commande écrite au oui, envoyée à la fin de l''appel)')
ON CONFLICT (version) DO NOTHING;
