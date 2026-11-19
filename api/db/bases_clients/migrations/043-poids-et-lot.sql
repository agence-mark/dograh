-- =====================================================================
--  043 : le poids et le lot de vente (chantier Partie 1, lot 13 : briques quantité et unité ; E29, D9, D55).
--  EN AJOUT SEULEMENT : colonnes facultatives, rien d'existant n'est modifié. ``resto_commande_ligne.quantite`` reste un entier (CHECK > 0) : une ligne au poids a ``quantite``
--  1 (ou le nombre de portions du même poids) et son ``poids_g``.
--
--  ``resto_commande_ligne.poids_g`` (QTE1) : le poids d'UNE portion de la ligne, en grammes ; vide pour toute ligne entière.
--  ``resto_produit`` :
--  * ``unite`` (QTE1) : ``piece`` (défaut), ``g`` ou ``kg`` : comment on vend le produit ;
--  * ``prix_par_unite`` (QTE1) : en centimes par KILOGRAMME pour ``g`` et ``kg`` (un entier ne porte pas le prix d'un gramme) ;
--  * ``arrondi`` (QTE1) : le pas du poids en grammes ; le poids dit est arrondi au pas supérieur, et dit ; vide : au gramme ;
--  * ``lot_de_vente`` (QTE2) : le nombre de pièces d'un lot ; le prix du produit est celui d'un lot.
--  Les droits et la sécurité par ligne des tables ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande_ligne ADD COLUMN IF NOT EXISTS poids_g integer CHECK (poids_g IS NULL OR poids_g > 0);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS unite text NOT NULL DEFAULT 'piece' CHECK (unite IN ('piece', 'g', 'kg'));
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS prix_par_unite integer CHECK (prix_par_unite IS NULL OR prix_par_unite > 0);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS arrondi integer CHECK (arrondi IS NULL OR arrondi > 0);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS lot_de_vente integer CHECK (lot_de_vente IS NULL OR lot_de_vente > 0);

INSERT INTO schema_version (version, description) VALUES
    (43, 'Module Restauration : poids d''une ligne (poids_g), unité, prix par unité, arrondi et lot de vente d''un produit')
ON CONFLICT (version) DO NOTHING;
