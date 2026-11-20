-- =====================================================================
--  Descente de la 046 (chantier Partie 1, lot 15). À jouer EN PREMIER (avant 045…). Idempotente.
--  Retire les colonnes ajoutées : les allergènes VALIDÉS du produit gardent leur liste (la colonne d'origine, 025), les seulement proposés redeviennent inconnus ; ceux d'une option, son état et sa source disparaissent.
-- =====================================================================
SET search_path = mark;

-- Lot 19 bis (K-046) : l'ancien code lit la colonne ``allergenes`` du produit comme VALIDÉE (il ne connaît pas l'état) : un allergène seulement PROPOSÉ (suggestion tirée des
-- ingrédients) redevient « inconnu » (NULL) avant que l'état disparaisse ; les allergènes validés restent. Rejouable : sans la colonne d'état, rien à faire.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = 'resto_produit' AND column_name = 'allergenes_etat') THEN
        UPDATE resto_produit SET allergenes = NULL WHERE allergenes_etat = 'propose';
    END IF;
END $$;

ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS allergies_renvoyees_au_restaurant;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS halal_restaurant;
ALTER TABLE IF EXISTS resto_reglage DROP COLUMN IF EXISTS consigne_allergie;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS nutrition;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS epice;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS regimes;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes_source;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes_etat;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS allergenes_source;
ALTER TABLE IF EXISTS resto_produit DROP COLUMN IF EXISTS allergenes_etat;
ALTER TABLE IF EXISTS resto_option DROP COLUMN IF EXISTS allergenes;

DELETE FROM schema_version WHERE version = 46;
