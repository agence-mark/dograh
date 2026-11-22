-- =====================================================================
--  Descente de la 051 (clôture de la Partie 1, lot B4). À jouer EN PREMIER (avant 050…). Idempotente.
--  L'index redevient unique sur toutes les commandes : la clé d'une commande annulée qui en double une autre est d'abord vidée (sinon l'index
--  ne se recrée pas) ; rien d'autre ne change.
-- =====================================================================
SET search_path = mark;

UPDATE resto_commande a SET cle_doublon = NULL
 WHERE a.statut = 'annulee' AND a.cle_doublon IS NOT NULL
   AND EXISTS (SELECT 1 FROM resto_commande b WHERE b.site_id = a.site_id AND b.cle_doublon = a.cle_doublon AND b.numero <> a.numero);

DROP INDEX IF EXISTS resto_commande_doublon_idx;
CREATE UNIQUE INDEX IF NOT EXISTS resto_commande_doublon_idx ON resto_commande (site_id, cle_doublon) WHERE cle_doublon IS NOT NULL;

DELETE FROM schema_version WHERE version = 51;
