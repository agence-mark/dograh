-- =====================================================================
--  030 : le signal « module Restauration allumé », le cercle d'une zone, le paiement et le numéro de commande, les soirs toujours chargés
--  (chantier module-restauration, lot 12).
--  Additive : deux colonnes. ``module_actif`` : vrai par défaut (une base qui a déjà des lignes de réglage reste allumée).
--  Allumer = une ligne de ``resto_reglage`` par établissement avec ``module_actif`` vrai ; retirer = ``module_actif`` faux
--  partout. AUCUNE donnée n'est supprimée (carte, salles, commandes, zones restent, le remettre les retrouve).
--  Le portail et le fork lisent le même signal : ``EXISTS (SELECT 1 FROM resto_reglage WHERE module_actif)``.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS module_actif boolean NOT NULL DEFAULT true;

-- Le cercle d'une zone sur le schéma de l'écran : son rayon en km, quelle que soit sa forme. Une zone « par communes » n'a pas de ``rayon_km`` (la
-- contrainte ``resto_zone_forme`` le veut vide) : ``cercle_km`` ne sert qu'à l'affichage et au rangement des communes par la distance, jamais à
-- décider si une adresse est livrée.
ALTER TABLE resto_zone ADD COLUMN IF NOT EXISTS cercle_km numeric(6, 2) CHECK (cercle_km IS NULL OR cercle_km > 0);

-- Paiement et numéro de commande (décision de la fenêtre principale : ce que l'onglet « Paiements et numéro » du portail et celui du fork enregistrent).
-- ``numero_mode`` : comment le numéro court est préfixé (liste fermée) ; ``prefixe_mixte`` : le préfixe d'un paiement en deux moyens.
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS numero_mode text NOT NULL DEFAULT 'aucun' CHECK (numero_mode IN ('aucun', 'moyen', 'type'));
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS prefixe_mixte text NOT NULL DEFAULT 'MIX' CHECK (prefixe_mixte ~ '^[A-Z0-9]{0,4}$');
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS notes_libres boolean NOT NULL DEFAULT true;
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS titre_alcool_exclu boolean NOT NULL DEFAULT true;
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS titre_sans_rendu boolean NOT NULL DEFAULT true;

-- Pause du téléphone avec la caisse (T-05) : quand la caisse passe en pause, l'agent du téléphone se met en pause aussi (oui par défaut ; décoché,
-- la pause de la caisse ne ferme plus le téléphone). Sources par objet (F4, E-49 « la caisse prime ») : ``{"carte": "ici"}`` = tenu ici et plus lu
-- chez la caisse ; un objet absent suit la caisse quand elle le porte. Objets réglables : carte, ruptures, etat, horaires.
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS pause_caisse_pause_telephone boolean NOT NULL DEFAULT true;
ALTER TABLE resto_reglage ADD COLUMN IF NOT EXISTS sources jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(sources) = 'object');

-- Ingrédients et allergènes écrits depuis l'onglet Carte quand la caisse est maître de la carte (W31) : en surcouche, jamais écrasés par un réimport.
-- ``ingredients`` vide = pas de surcouche ; ``allergenes_ecrits`` dit si ``allergenes`` compte (NULL = inconnu et '{}' = aucun restent distincts).
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS ingredients jsonb CHECK (ingredients IS NULL OR jsonb_typeof(ingredients) = 'array');
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS allergenes_ecrits boolean NOT NULL DEFAULT false;
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS allergenes text[] CHECK (allergenes IS NULL OR allergenes <@ ARRAY[
    'gluten', 'crustaces', 'oeufs', 'poissons', 'arachides', 'soja', 'lait', 'fruits_a_coque',
    'celeri', 'moutarde', 'sesame', 'sulfites', 'lupin', 'mollusques']::text[]);
-- ``alcool`` : le produit contient de l'alcool (un titre-restaurant ne le paie pas, réglage « alcool exclu du titre »). Posé à l'écran, toujours en surcouche.
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS alcool boolean NOT NULL DEFAULT false;
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS produit_source text CHECK (produit_source IS NULL OR produit_source IN ('caisse', 'portail', 'mark', 'agent', 'import'));
ALTER TABLE resto_surcouche ADD COLUMN IF NOT EXISTS produit_maj_le timestamptz;

-- Les soirs toujours chargés : des minutes ajoutées par-dessus le délai d'un type, certains jours, dans une plage (heure locale de l'établissement,
-- ``jours`` : 1 = lundi à 7 = dimanche). Elles s'ajoutent à celles que la puce pose pour un moment ; deux plages qui se recouvrent : la plus grande compte.
CREATE TABLE IF NOT EXISTS resto_temps_recurrent (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id         bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    type            text NOT NULL CHECK (type IN ('emporter', 'livraison', 'sur_place')),
    jours           smallint[] NOT NULL CHECK (cardinality(jours) BETWEEN 1 AND 7 AND jours <@ ARRAY[1, 2, 3, 4, 5, 6, 7]::smallint[]),
    debut           time NOT NULL,
    fin             time NOT NULL,
    minutes_ajoutees integer NOT NULL CHECK (minutes_ajoutees BETWEEN 1 AND 240),
    maj_le          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT resto_temps_recurrent_plage CHECK (fin > debut)
);
CREATE INDEX IF NOT EXISTS resto_temps_recurrent_site_idx ON resto_temps_recurrent (site_id, type);

DO $$
BEGIN
    DROP TRIGGER IF EXISTS resto_temps_recurrent_maj_le ON resto_temps_recurrent;
    CREATE TRIGGER resto_temps_recurrent_maj_le BEFORE UPDATE ON resto_temps_recurrent FOR EACH ROW EXECUTE FUNCTION resto_maj_le();
    DROP TRIGGER IF EXISTS resto_temps_recurrent_journal ON resto_temps_recurrent;
    CREATE TRIGGER resto_temps_recurrent_journal AFTER INSERT OR UPDATE OR DELETE ON resto_temps_recurrent FOR EACH ROW EXECUTE FUNCTION resto_journaliser();
    -- Le portail les règle lui-même (contrat § 1 : zones et délais en direct), établissement par établissement.
    PERFORM resto_droits('resto_temps_recurrent', 'ecriture');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (30, 'Module Restauration : signal « module allumé » (resto_reglage.module_actif, le retirer ne supprime aucune donnée) cercle d''une zone (resto_zone.cercle_km), paiement et numéro de commande, soirs toujours chargés (resto_temps_recurrent)')
ON CONFLICT (version) DO NOTHING;
