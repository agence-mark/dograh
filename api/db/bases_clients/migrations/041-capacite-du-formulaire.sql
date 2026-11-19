-- =====================================================================
--  041 : la capacité du formulaire (chantier Partie 1, lot 7 complément : la réservation sans plan ni tables ; E1, E2).
--  Additive : une colonne facultative sur les règles de réservation ; NULL = non dite (aucun changement de comportement avec des tables).
--
--  ``resto_regle_reservation.couverts_simultanes`` : le nombre de couverts présents en même temps dans la salle, sur la durée d'un repas. Sans table
--  active, c'est elle qui dit si un créneau tient ; vide et sans table, la réservation est INCOMPLETE (``capacite``), jamais « complet ».
--  ``couverts_max_creneau`` (arrivées par créneau) reste en plus, inchangé.
--  Numéro pris par SA-4 (le lot 12 annonçait 041) : à renuméroter côté lots 12 à 15 (voir a-trancher.md).
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_regle_reservation
    ADD COLUMN IF NOT EXISTS couverts_simultanes integer CHECK (couverts_simultanes IS NULL OR couverts_simultanes >= 1);

INSERT INTO schema_version (version, description) VALUES
    (41, 'Module Restauration : capacité du formulaire en couverts présents en même temps (réservation sans tables)')
ON CONFLICT (version) DO NOTHING;
