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

-- E11 : le filet du rattrapage (chaque minute). Une ligne « retenue » part quand son appel est terminé en base (sa fin n'a pas été jouée : serveur redémarré
-- pendant l'appel) et qu'elle n'a plus bougé depuis ``filet_retenue_min`` minutes, comptées depuis sa dernière écriture (``maj_le`` : le dernier « oui »), pas
-- depuis la fin de l'appel, que le filet ne connaît pas. Un réglage du module de l'établissement, 2 par défaut.
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS filet_retenue_min integer NOT NULL DEFAULT 2 CHECK (filet_retenue_min BETWEEN 1 AND 120);

-- Les lectures des lignes « retenue » : le filet, par établissement et dans l'ordre (``maj_le``, ``numero``), seulement celles d'un appel ; la fin de l'appel, par
-- ``appel_id`` (toute la table sinon, à chaque fin d'appel).
CREATE INDEX IF NOT EXISTS resto_commande_retenue_idx ON resto_commande (site_id, maj_le, numero) WHERE statut = 'retenue' AND appel_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS resto_commande_appel_idx ON resto_commande (appel_id) WHERE appel_id IS NOT NULL;

INSERT INTO schema_version (version, description) VALUES
    (54, 'Module Restauration : statut retenue (commande écrite au oui, envoyée à la fin de l''appel) et délai du filet du rattrapage')
ON CONFLICT (version) DO NOTHING;
