-- =====================================================================
--  055 (chantier Partie 1, lot 8b-1b ; Pierre 27/11, registre T24 (1)) : l'alerte du filet pour une commande ``retenue`` qui ne peut pas partir.
--  Le filet du rattrapage envoie une ligne ``retenue`` quand son appel est terminé ou ne peut plus être en cours. Une ligne dont l'appel reste inconnu ou
--  jamais fini au-delà de la limite du filet alerte le restaurant UNE fois (``filet_alerte_le``, posée par la seule requête qui la pose) ; le filet ne la relit
--  plus ensuite (la fin de l'appel, si elle arrive, l'envoie encore). En ajout seulement. Idempotente.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS filet_alerte_le timestamptz;

-- La lecture du filet ne garde que les lignes pas encore alertées : l'index partiel de la 054 suit ce filtre.
DROP INDEX IF EXISTS resto_commande_retenue_idx;
CREATE INDEX IF NOT EXISTS resto_commande_retenue_idx ON resto_commande (site_id, maj_le, numero)
    WHERE statut = 'retenue' AND appel_id IS NOT NULL AND filet_alerte_le IS NULL;

INSERT INTO schema_version (version, description) VALUES
    (55, 'Module Restauration : alerte du filet pour une commande retenue qui ne peut pas partir')
ON CONFLICT (version) DO NOTHING;
