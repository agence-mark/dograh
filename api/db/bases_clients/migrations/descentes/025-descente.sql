-- =====================================================================
--  Descente de la 025 (module Restauration, lot 1) : retire la carte au format commun.
--  À jouer APRÈS les descentes de la 028, 027 et 026. ⛔ SUPPRIME toute la carte et ses surcouches :
--  sauvegarder la base avant. Idempotente (IF EXISTS partout).
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS resto_surcouche, resto_formule, resto_option, resto_groupe_choix,
                     resto_declinaison, resto_produit, resto_categorie;
DROP FUNCTION IF EXISTS resto_maj_le();
DROP FUNCTION IF EXISTS resto_droits(text, text, boolean);

DELETE FROM schema_version WHERE version = 25;
