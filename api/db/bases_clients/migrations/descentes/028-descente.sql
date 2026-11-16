-- =====================================================================
--  Descente de la 028 (module Restauration, lot 1). À jouer EN PREMIER (avant 027, 026, 025).
--  ⛔ SUPPRIME les salles, tables, réservations, le journal des changements, la version de la carte et le
--  récapitulatif chiffré : sauvegarder la base avant. Retire aussi les déclencheurs posés sur les tables des
--  025 à 027. Idempotente.
-- =====================================================================
SET search_path = mark;

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'resto_categorie', 'resto_produit', 'resto_declinaison', 'resto_groupe_choix', 'resto_option', 'resto_formule',
        'resto_surcouche', 'resto_rupture', 'resto_etat_caisse', 'resto_reglage_type', 'resto_zone', 'resto_commande',
        'resto_liaison', 'resto_client', 'resto_remise', 'resto_envoi', 'resto_reglage'] LOOP
        IF to_regclass('mark.' || t) IS NOT NULL THEN
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_journal', t);
            EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_version', t);
        END IF;
    END LOOP;
END $$;

DROP TABLE IF EXISTS resto_version_carte, resto_recap_jour, resto_journal, resto_reservation, resto_regle_reservation,
                     resto_duree_groupe, resto_service, resto_table, resto_salle;
DROP FUNCTION IF EXISTS resto_journaliser();
DROP FUNCTION IF EXISTS resto_monter_version_carte();

DELETE FROM schema_version WHERE version = 28;
