-- =====================================================================
--  046 : les allergènes validés, les régimes, l'épice, la nutrition, les réglages d'information (chantier Partie 1, lot 15 : briques INF1 à INF7 ; D22, D9, E29).
--  EN AJOUT SEULEMENT : des colonnes facultatives, rien d'existant n'est modifié (sauf l'étiquette des allergènes déjà écrits, ci-dessous).
--  (La fiche du lot disait 044 ; 044 est le code de remise (lot 14) et 045 le lot des manques : ce lot prend 046.)
--
--  ``resto_option.allergenes`` : les 14 codes de l'option, ``NULL`` = inconnu, ``{}`` = aucun (même règle que le produit, 025).
--  ``allergenes_etat`` (``propose`` | ``valide``) et ``allergenes_source`` (``caisse`` | ``restaurateur`` | ``suggestion``), sur le produit et l'option : seuls les
--  allergènes ``valide`` sont lus par l'agent ; une suggestion tirée des ingrédients est ``propose`` jusqu'à ce qu'une personne la valide.
--  Les allergènes déjà en base passent en ``valide`` : source ``caisse`` pour une ligne venue d'une caisse ou d'un fichier, ``restaurateur`` sinon (une personne
--  les a écrits, jamais proposés). Une surcouche (030) dont ``allergenes_ecrits`` est vrai est, par construction, validée par une personne.
--  ``resto_produit.regimes`` (liste fermée), ``epice`` (texte), ``nutrition`` (jsonb : valeurs pour 100 g, degré).
--  ``resto_reglage.consigne_allergie`` (texte), ``halal_restaurant`` (faux), ``allergies_renvoyees_au_restaurant`` (faux : réglage restrictif éteint par défaut).
--  Les droits et la sécurité par ligne des tables ne changent pas (aucune table neuve). Aucune donnée personnelle.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS allergenes text[] CHECK (allergenes IS NULL OR allergenes <@ ARRAY[
    'gluten', 'crustaces', 'oeufs', 'poissons', 'arachides', 'soja', 'lait', 'fruits_a_coque',
    'celeri', 'moutarde', 'sesame', 'sulfites', 'lupin', 'mollusques']::text[]);

ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS allergenes_etat text NOT NULL DEFAULT 'valide' CHECK (allergenes_etat IN ('propose', 'valide'));
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS allergenes_source text CHECK (allergenes_source IS NULL OR allergenes_source IN ('caisse', 'restaurateur', 'suggestion'));
ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS allergenes_etat text NOT NULL DEFAULT 'valide' CHECK (allergenes_etat IN ('propose', 'valide'));
ALTER TABLE resto_option ADD COLUMN IF NOT EXISTS allergenes_source text CHECK (allergenes_source IS NULL OR allergenes_source IN ('caisse', 'restaurateur', 'suggestion'));

ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS regimes text[] CHECK (regimes IS NULL OR regimes <@ ARRAY['vegetarien', 'vegetalien', 'sans_gluten', 'halal', 'autre']::text[]);
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS epice text CHECK (epice IS NULL OR btrim(epice) <> '');
ALTER TABLE resto_produit ADD COLUMN IF NOT EXISTS nutrition jsonb CHECK (nutrition IS NULL OR jsonb_typeof(nutrition) = 'object');

ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS consigne_allergie text CHECK (consigne_allergie IS NULL OR btrim(consigne_allergie) <> '');
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS halal_restaurant boolean NOT NULL DEFAULT false;
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS allergies_renvoyees_au_restaurant boolean NOT NULL DEFAULT false;

-- L'étiquette des allergènes déjà écrits : une seule fois (une colonne encore sans source), hors du journal des changements (ce n'est pas un geste d'une personne).
SELECT set_config('mark.purge', 'on', true);
UPDATE resto_produit SET allergenes_source = CASE WHEN source IN ('caisse', 'import') THEN 'caisse' ELSE 'restaurateur' END
    WHERE allergenes IS NOT NULL AND allergenes_source IS NULL;
SELECT set_config('mark.purge', 'off', true);

INSERT INTO schema_version (version, description) VALUES
    (46, 'Module Restauration : allergènes validés ou proposés (produit, option), régimes, épice, nutrition, consigne d''allergie, halal du restaurant, allergies renvoyées au restaurant')
ON CONFLICT (version) DO NOTHING;
