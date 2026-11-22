-- =====================================================================
--  051 : la clé anti-doublon n'est unique que parmi les commandes NON annulées (clôture de la Partie 1, lot B4, M2).
--
--  Avant : l'index unique ``resto_commande_doublon_idx`` portait sur toutes les commandes. Une commande enregistrée puis changée (l'heure, le même
--  panier) est annulée puis réenregistrée : même appel, même panier, même clé ; l'anti-doublon rendait l'ANCIENNE (annulée) comme « déjà faite »,
--  et la commande de la personne était perdue (test des combinaisons, E16 et E18). Une commande annulée n'est plus jamais « déjà faite ».
--  En place : l'index est recréé partiel, sans toucher aux données.
-- =====================================================================
SET search_path = mark;

DROP INDEX IF EXISTS resto_commande_doublon_idx;
CREATE UNIQUE INDEX IF NOT EXISTS resto_commande_doublon_idx ON resto_commande (site_id, cle_doublon)
    WHERE cle_doublon IS NOT NULL AND statut <> 'annulee';

INSERT INTO schema_version (version, description) VALUES
    (51, 'Module Restauration : la clé anti-doublon ne compte pas les commandes annulées')
ON CONFLICT (version) DO NOTHING;
