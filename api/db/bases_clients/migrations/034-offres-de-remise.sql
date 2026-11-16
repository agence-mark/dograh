-- =====================================================================
--  034 : les offres de remise DITES par l'agent et leur ACCEPTATION (chantier module-restauration, lot 26, M38).
--  Additive : une table. Alimente les colonnes « Dite » et « Acceptée » de l'écran Remises du fork.
--
--  ``resto_remise_offre`` : une ligne par offre dite à un appelant. ``dite_le`` : le moment où l'agent l'a dite (posé par la couche d'accès, source
--  d'heure de l'organisation : aucun défaut SQL) ; ``acceptee_le`` : le moment où la remise s'est retrouvée sur la commande enregistrée (vide = pas
--  acceptée, ou pas encore). ``appel_id`` : l'appel qui l'a dite (la même offre n'est comptée qu'une fois par appel quand il est connu) ;
--  ``commande_numero`` : la commande qui l'a acceptée (elle survit à la purge de la commande : le lien se vide, la ligne reste).
--  Aucune donnée personnelle : ni numéro de téléphone, ni nom. Le fork l'écrit, le portail la lit (RLS par établissement, comme les commandes).
-- =====================================================================
SET search_path = mark;

CREATE TABLE IF NOT EXISTS resto_remise_offre (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    site_id          bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    remise_id        bigint NOT NULL REFERENCES resto_remise(id) ON DELETE CASCADE,
    appel_id         text CHECK (appel_id IS NULL OR btrim(appel_id) <> ''),
    dite_le          timestamptz NOT NULL,
    acceptee_le      timestamptz,
    commande_numero  uuid REFERENCES resto_commande(numero) ON DELETE SET NULL,
    CONSTRAINT resto_remise_offre_ordre CHECK (acceptee_le IS NULL OR acceptee_le >= dite_le)
);
-- Une offre n'est comptée qu'une fois par appel (quand l'appel est connu) ; la lecture de l'écran groupe par remise.
CREATE UNIQUE INDEX IF NOT EXISTS resto_remise_offre_appel_idx ON resto_remise_offre (remise_id, appel_id) WHERE appel_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS resto_remise_offre_site_idx ON resto_remise_offre (site_id, remise_id);

DO $$
BEGIN
    -- Le fork l'écrit (l'agent dit, la commande accepte) ; le portail la lit seulement.
    PERFORM resto_droits('resto_remise_offre', 'lecture');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (34, 'Module Restauration : offres de remise dites par l''agent et leur acceptation (colonnes Dite et Acceptée de l''écran Remises)')
ON CONFLICT (version) DO NOTHING;
