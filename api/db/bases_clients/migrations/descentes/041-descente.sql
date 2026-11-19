-- =====================================================================
--  Descente de la 041 (chantier Partie 1, lot 7 complément). À jouer EN PREMIER (avant 040…). Idempotente.
--  Retire la capacité du formulaire : seul ce réglage est perdu, les réservations restent entières.
-- =====================================================================
SET search_path = mark;

ALTER TABLE IF EXISTS resto_regle_reservation DROP COLUMN IF EXISTS couverts_simultanes;

DELETE FROM schema_version WHERE version = 41;
