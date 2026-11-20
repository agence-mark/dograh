-- =====================================================================
--  049 : le motif que la caisse écrit en refusant une commande (chantier Partie 1, lot 19 bis, N6 ; prouvé en 208 et 210).
--  EN AJOUT SEULEMENT : une colonne facultative, rien d'existant n'est modifié.
--
--  ``resto_commande.motif_refus_caisse`` : le message du restaurant (``seller_notes`` de la commande lue chez HubRise, « Plus de pâte ce soir »), gardé tel quel (500 signes au plus) pour
--  être joint à l'alerte de refus et lu par le portail. Ce que l'agent DIT au client n'est pas décidé ici. Aucune donnée personnelle du client ; droits et sécurité par ligne inchangés.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS motif_refus_caisse text CHECK (motif_refus_caisse IS NULL OR (btrim(motif_refus_caisse) <> '' AND length(motif_refus_caisse) <= 500));

INSERT INTO schema_version (version, description) VALUES
    (49, 'Module Restauration : motif du refus écrit par la caisse')
ON CONFLICT (version) DO NOTHING;
