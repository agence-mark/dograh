-- =====================================================================
--  044 : le code de remise (chantier Partie 1, lot 14 : brique OFF3 ; E29, D9, D23).
--  EN AJOUT SEULEMENT : une colonne facultative, rien d'existant n'est modifié.
--
--  ``resto_remise.code`` (OFF3) : le code que l'appelant dit pour avoir la remise (« BIENVENUE », « PIZZA5 »), en majuscules et chiffres, sans séparateur
--  (la forme que lit ``barriere_des_chiffres.code_lu``). Une remise À CODE n'est JAMAIS annoncée par l'agent (ni « qu'est-ce que vous avez », ni offre
--  proposée) et ne s'applique qu'à une commande dont l'appelant a dit le code. Un code est unique dans un établissement (index partiel).
--  Les droits et la sécurité par ligne de la table ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_remise ADD COLUMN IF NOT EXISTS code text CHECK (code IS NULL OR code ~ '^[A-Z0-9]{2,32}$');
CREATE UNIQUE INDEX IF NOT EXISTS resto_remise_code_idx ON resto_remise (site_id, code) WHERE code IS NOT NULL;

INSERT INTO schema_version (version, description) VALUES
    (44, 'Module Restauration : code de remise (resto_remise.code), jamais annoncé, unique par établissement')
ON CONFLICT (version) DO NOTHING;
