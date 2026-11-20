-- =====================================================================
--  Descente de la 048 (chantier Partie 1, lot 19 bis, K5). À jouer EN PREMIER (avant 047…). Idempotente.
--  Retire l'index et les colonnes ajoutés : les commandes gardent tout le reste (une annulation encore à dire n'est plus rejouée).
-- =====================================================================
SET search_path = mark;

DROP INDEX IF EXISTS resto_commande_annulation_idx;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS annulation_alertee_le;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS annulation_essai_le;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS annulation_essais;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS annulation_a_dire_le;

DELETE FROM schema_version WHERE version = 48;
