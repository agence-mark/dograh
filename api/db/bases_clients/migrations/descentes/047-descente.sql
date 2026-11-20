-- =====================================================================
--  Descente de la 047 (chantier Partie 1, lot 16). À jouer EN PREMIER (avant 046…). Idempotente.
--  Retire l'index et les colonnes ajoutés : les commandes gardent tout le reste (le statut ``echec`` ne dit plus sa cause).
-- =====================================================================
SET search_path = mark;

DROP INDEX IF EXISTS resto_commande_envoyee_idx;
ALTER TABLE IF EXISTS resto_liaison ALTER COLUMN alerte_sans_reponse_min SET DEFAULT 3;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS alerte_nouvelle_le;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS acceptee_le;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS envoyee_le;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS consigne_livreur;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS cause_echec;

DELETE FROM schema_version WHERE version = 47;
