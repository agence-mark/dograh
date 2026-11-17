-- =====================================================================
--  036 : le numéro de carte d'un produit et d'une formule (capacité C2, SA-48).
--  Beaucoup de cartes numérotent leurs plats (« le 46 », « J24 », « 16b ») : le client les dit au téléphone.
--  Additive : une colonne facultative sur deux tables, rien d'existant n'est modifié ; NULL = carte non numérotée (aucun changement).
--  La recherche (``recherche_liste_numero.py``) compare la clé exacte du numéro, jamais une approximation.
--  Les droits et la sécurité par ligne des tables ne changent pas. Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS numero text CHECK (numero IS NULL OR btrim(numero) <> '');
ALTER TABLE resto_formule ADD COLUMN IF NOT EXISTS numero text CHECK (numero IS NULL OR btrim(numero) <> '');

INSERT INTO schema_version (version, description) VALUES
    (36, 'Module Restauration : numéro de carte facultatif d''un produit et d''une formule (C2)')
ON CONFLICT (version) DO NOTHING;
