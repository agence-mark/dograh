-- =====================================================================
--  048 : l'annulation d'une commande qu'il reste à dire à la caisse (chantier Partie 1, lot 19 bis, K5 ; audit caisse de Pierre du 20/11).
--  EN AJOUT SEULEMENT : des colonnes facultatives, rien d'existant n'est modifié.
--
--  Une commande annulée chez nous alors que la caisse ne répond pas restait vivante en caisse : le restaurant la préparait. L'annulation est maintenant gardée « à dire » :
--  ``annulation_a_dire_le`` (posée à l'annulation, effacée quand la caisse l'a reçue), ``annulation_essais`` et ``annulation_essai_le`` (le rattrapage la rejoue, espacée), et
--  ``annulation_alertee_le`` (une seule alerte au restaurant, au 5e essai raté : rejouable sans effet double). Rejouer une annulation est sans risque chez HubRise (prouvé en 04).
--  Les droits et la sécurité par ligne de la table ne changent pas (aucune table neuve). Aucune donnée personnelle de plus.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS annulation_a_dire_le timestamptz;
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS annulation_essais integer NOT NULL DEFAULT 0 CHECK (annulation_essais >= 0);
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS annulation_essai_le timestamptz;
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS annulation_alertee_le timestamptz;
CREATE INDEX IF NOT EXISTS resto_commande_annulation_idx ON resto_commande (site_id, annulation_a_dire_le) WHERE annulation_a_dire_le IS NOT NULL AND annulation_alertee_le IS NULL;

INSERT INTO schema_version (version, description) VALUES
    (48, 'Module Restauration : annulation à dire à la caisse, reprise par le rattrapage (essais, alerte)')
ON CONFLICT (version) DO NOTHING;
