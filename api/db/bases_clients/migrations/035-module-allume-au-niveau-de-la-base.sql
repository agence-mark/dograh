-- =====================================================================
--  035 : l'état « module Restauration allumé » tenu AU NIVEAU DE LA BASE (chantier module-restauration, lot 26, M50).
--  Avant : l'état n'existait qu'en lignes de ``resto_reglage`` (une par établissement) ; une base sans établissement ne pouvait pas porter
--  l'état, « Ajouter un module » ne retenait rien. Maintenant : une table d'une seule ligne, ``resto_module``, dit si le module est allumé pour
--  la base. Un établissement créé ensuite reçoit sa ligne de réglage (``module_actif`` selon l'état de la base) d'office, par déclencheur.
--  Additive : une table, une fonction, un déclencheur. Les bases déjà allumées (ou éteintes) par leurs lignes de réglage gardent leur état.
--  Aucune donnée personnelle. Le retirer ne supprime AUCUNE donnée (comme la 030).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS resto_module (
    seule   boolean PRIMARY KEY DEFAULT true CHECK (seule),   -- une seule ligne par base
    actif   boolean NOT NULL,
    maj_le  timestamptz NOT NULL DEFAULT now()
);

-- Une base qui porte déjà des lignes de réglage garde l'état qu'elles disaient (allumée si l'une l'est).
INSERT INTO resto_module (actif)
SELECT bool_or(module_actif) FROM resto_reglage HAVING count(*) > 0
ON CONFLICT (seule) DO NOTHING;

DO $$
BEGIN
    DROP TRIGGER IF EXISTS resto_module_maj_le ON resto_module;
    CREATE TRIGGER resto_module_maj_le BEFORE UPDATE ON resto_module FOR EACH ROW EXECUTE FUNCTION resto_maj_le();
    -- Le fork seul l'écrit ; le portail lit l'état par les lignes de réglage de ses lieux (aucun accès direct).
    PERFORM resto_droits('resto_module', 'aucun');
END $$;

-- Un établissement créé après l'allumage reçoit sa ligne de réglage allumée ; module éteint ou jamais ajouté : rien n'est créé.
CREATE OR REPLACE FUNCTION resto_regler_le_nouvel_etablissement() RETURNS trigger LANGUAGE plpgsql
SECURITY DEFINER SET search_path = mark AS $$
BEGIN
    IF (SELECT actif FROM resto_module) IS TRUE THEN
        INSERT INTO resto_reglage (site_id, module_actif) VALUES (NEW.id, true) ON CONFLICT (site_id) DO NOTHING;
    END IF;
    RETURN NULL;
END $$;

DROP TRIGGER IF EXISTS site_module_restauration ON site;
CREATE TRIGGER site_module_restauration AFTER INSERT ON site FOR EACH ROW EXECUTE FUNCTION resto_regler_le_nouvel_etablissement();

INSERT INTO schema_version (version, description) VALUES
    (35, 'Module Restauration : état « module allumé » tenu au niveau de la base (resto_module), un établissement créé ensuite reçoit sa ligne de réglage allumée d''office')
ON CONFLICT (version) DO NOTHING;
