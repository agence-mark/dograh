-- =====================================================================
--  Descente de la 049 (chantier Partie 1, lot 19 bis, N6). À jouer EN PREMIER (avant 048…). Idempotente.
--  Retire la colonne ajoutée : les commandes gardent tout le reste (le motif du refus n'est plus gardé).
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS motif_refus_caisse;

DELETE FROM schema_version WHERE version = 49;
