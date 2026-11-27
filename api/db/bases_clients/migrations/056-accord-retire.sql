-- =====================================================================
--  056 (chantier Partie 1, lot 8b-3, T35 ; Pierre 27/11) : la marque « accord retiré » d'une commande ``retenue``.
--  Une allergie dite après le « oui » retire l'accord ; la marque est posée sur la ligne AVANT la tentative de l'annuler. Si l'annulation échoue (la ligne reste ``retenue``)
--  puis que l'appel plante, le filet du rattrapage lit la marque : il n'envoie pas la ligne, la passe à « annulée » et alerte le restaurant une fois. Un nouveau « oui »
--  (réécriture, ``rouvrir``) l'efface. En ajout seulement. Idempotente.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS accord_retire_le timestamptz;

INSERT INTO schema_version (version, description) VALUES
    (56, 'Module Restauration : marque « accord retiré » sur une commande retenue (le filet ne l''envoie pas)')
ON CONFLICT (version) DO NOTHING;
