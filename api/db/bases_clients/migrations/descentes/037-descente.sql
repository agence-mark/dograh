-- =====================================================================
--  Descente de la 037 (chantier Partie 1, lot 8). À jouer EN PREMIER (avant 036, 035…). Idempotente.
--  Retire les colonnes ajoutées et la table des signalements : seules ces données sont perdues, la carte reste entière.
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_signalement_carte;

ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS texte_du_jour;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS du_moment;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS nom_commun;
ALTER TABLE IF EXISTS resto_surcouche DROP COLUMN IF EXISTS genre;
ALTER TABLE IF EXISTS resto_categorie DROP COLUMN IF EXISTS role;
ALTER TABLE IF EXISTS resto_declinaison DROP COLUMN IF EXISTS quotas;
ALTER TABLE IF EXISTS resto_declinaison DROP COLUMN IF EXISTS libelle_question;
ALTER TABLE IF EXISTS resto_declinaison DROP COLUMN IF EXISTS type;

DELETE FROM schema_version WHERE version = 37;
