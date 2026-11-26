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

-- E11 : le filet du rattrapage. Une ligne « retenue » dont l'appel est terminé en base sans que sa fin ait été jouée (serveur redémarré pendant l'appel) part
-- quand elle n'a plus bougé depuis ``filet_retenue_min`` minutes : un réglage du module de l'établissement, 2 par défaut (deux passages du rattrapage, qui tourne
-- chaque minute : la fin normale de l'appel, jouée dans la seconde, a toujours fini avant ; la cuisine l'a vite quand même).
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS filet_retenue_min integer NOT NULL DEFAULT 2 CHECK (filet_retenue_min BETWEEN 1 AND 120);

INSERT INTO schema_version (version, description) VALUES
    (54, 'Module Restauration : statut retenue (commande écrite au oui, envoyée à la fin de l''appel) et délai du filet du rattrapage')
ON CONFLICT (version) DO NOTHING;
