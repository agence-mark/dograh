-- =====================================================================
--  047 : la cause d'un échec d'envoi, la consigne pour le livreur, et le suivi d'une commande restée « nouvelle » (chantier Partie 1, lot 16 ; audit caisse § 3, notes de Pierre du 19/11).
--  EN AJOUT SEULEMENT : des colonnes facultatives, rien d'existant n'est modifié.
--
--  ``resto_commande.cause_echec`` (``caisse`` | ``code``) : pourquoi une commande est en ``echec``. ``code`` = une erreur de NOTRE code (traduction, exception) : jamais prise pour une panne de la
--  caisse, aucune nouvelle tentative inutile, alerte tout de suite. Le chemin fermé des statuts (contrat § 3) ne change pas : le portail lit cette colonne pour distinguer « échec de .mark ».
--  ``resto_commande.consigne_livreur`` : la consigne pour le livreur de CETTE commande (« code 1234 »), envoyée à la caisse dans ``customer.delivery_notes`` (champ HubRise existant).
--  ``envoyee_le`` (l'heure de l'envoi à la caisse), ``acceptee_le`` (l'heure où la caisse l'a acceptée) et ``alerte_nouvelle_le`` (l'heure de l'alerte « restée nouvelle cinq minutes ») :
--  posées par la couche d'accès, jamais par un appelant ; ``alerte_nouvelle_le`` rend la surveillance rejouable sans effet double (une seule alerte par commande).
--  Les droits et la sécurité par ligne de la table ne changent pas (aucune table neuve). Aucune donnée personnelle de plus.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS cause_echec text CHECK (cause_echec IS NULL OR cause_echec IN ('caisse', 'code'));
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS consigne_livreur text CHECK (consigne_livreur IS NULL OR btrim(consigne_livreur) <> '');
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS envoyee_le timestamptz;
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS acceptee_le timestamptz;
ALTER TABLE resto_commande ADD COLUMN IF NOT EXISTS alerte_nouvelle_le timestamptz;
-- Le seuil de l'alerte « restée nouvelle » : cinq minutes par défaut (la documentation HubRise : « typically five minutes within business hours »). Les établissements qui ont réglé
-- eux-mêmes leur seuil le gardent ; seule la valeur par défaut des nouvelles liaisons change (aucune donnée réécrite).
ALTER TABLE resto_liaison ALTER COLUMN alerte_sans_reponse_min SET DEFAULT 5;
CREATE INDEX IF NOT EXISTS resto_commande_envoyee_idx ON resto_commande (site_id, envoyee_le) WHERE statut = 'envoyee' AND alerte_nouvelle_le IS NULL;

INSERT INTO schema_version (version, description) VALUES
    (47, 'Module Restauration : cause d''un échec d''envoi (caisse ou code), consigne pour le livreur, heures d''envoi, d''acceptation et d''alerte « restée nouvelle »')
ON CONFLICT (version) DO NOTHING;
