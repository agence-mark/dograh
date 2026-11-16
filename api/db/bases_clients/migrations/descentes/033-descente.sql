-- =====================================================================
--  Descente de la 033 (module Restauration, lot 26, M13 et M14). À jouer EN PREMIER (avant 032, 031…). Idempotente.
--  ⛔ SUPPRIME les plans du soir, les taux de TVA figés sur les lignes et les frais, et le récapitulatif par taux : sauvegarder la base avant.
--  Les montants (total, frais, remises, lignes) ne sont pas touchés ; seule la ventilation par taux disparaît.
-- =====================================================================
SET search_path = mark;

DROP FUNCTION IF EXISTS resto_tva_par_jour(bigint, date, date);
DROP FUNCTION IF EXISTS resto_ventilation_commandes(bigint, timestamptz);
DROP TABLE IF EXISTS resto_recap_jour_taux;
DROP TABLE IF EXISTS resto_plan_soir;
ALTER TABLE IF EXISTS resto_commande_ligne DROP COLUMN IF EXISTS taux_tva;
ALTER TABLE IF EXISTS resto_commande DROP COLUMN IF EXISTS taux_tva_frais;

DELETE FROM schema_version WHERE version = 33;
