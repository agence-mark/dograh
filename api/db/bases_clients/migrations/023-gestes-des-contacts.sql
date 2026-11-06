-- =====================================================================
--  023 : les gestes des contacts du portail (builder partie 3, SA-17c).
--  Additive seulement : deux colonnes de doute, deux colonnes de contact, une table de renvoi.
--
--  - contact.doublon_de / doublon_raison : le doute d'une fiche sur une autre (D196). Une fiche sans doute
--    n'est pas fusionnée. La fiche qu'elle double peut disparaître : le doute tombe (ON DELETE SET NULL).
--  - contact.mail_declare : le mail a été donné par la personne elle-même (le site), D176.
--  - contact.ne_pas_memoriser : à la demande de la personne, l'agent ne lui lit plus aucun historique (D209).
--  - contact_fusion : le renvoi laissé par une fusion (l'ancienne fiche -> la fiche gardée), pour qu'un geste rejoué
--    ne fasse rien de plus et réponde la même chose. Effacée avec la fiche gardée (conservation).
--  Droits : la fusion peut changer le seul contact_id d'une vérification. Aucun droit nouveau pour le portail : les colonnes se lisent par le droit de lecture déjà donné sur contact
--  (sécurité par ligne de la 015), la table de renvoi ne lui est pas ouverte. Les écritures passent par le serveur.
-- =====================================================================
SET search_path = mark;

ALTER TABLE contact ADD COLUMN IF NOT EXISTS doublon_de bigint REFERENCES contact(id) ON DELETE SET NULL;
ALTER TABLE contact ADD COLUMN IF NOT EXISTS doublon_raison text;
ALTER TABLE contact ADD COLUMN IF NOT EXISTS mail_declare boolean NOT NULL DEFAULT false;
ALTER TABLE contact ADD COLUMN IF NOT EXISTS ne_pas_memoriser boolean NOT NULL DEFAULT false;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'contact_doublon_pas_lui_meme') THEN
        ALTER TABLE contact ADD CONSTRAINT contact_doublon_pas_lui_meme CHECK (doublon_de IS NULL OR doublon_de <> id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'contact_doublon_raison_courte') THEN
        ALTER TABLE contact ADD CONSTRAINT contact_doublon_raison_courte CHECK (doublon_raison IS NULL OR char_length(doublon_raison) <= 200);
    END IF;
END $$;

-- Les fiches qui doutent d'une fiche donnée (fusion : on les rattache à la fiche gardée).
CREATE INDEX IF NOT EXISTS contact_doublon_de_idx ON contact (doublon_de) WHERE doublon_de IS NOT NULL;

CREATE TABLE IF NOT EXISTS contact_fusion (
    ancien_id bigint PRIMARY KEY,
    garde_id  bigint NOT NULL REFERENCES contact(id) ON DELETE CASCADE,
    le        timestamptz NOT NULL DEFAULT now(),
    auteur    text NOT NULL
);
CREATE INDEX IF NOT EXISTS contact_fusion_garde_idx ON contact_fusion (garde_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON contact_fusion TO mark_ecriture;
-- La fusion rattache les vérifications du doublon à la fiche gardée : la table est un journal (011 : pas d'UPDATE),
-- seul le contact peut donc changer, et rien d'autre.
GRANT UPDATE (contact_id) ON verification TO mark_ecriture;

INSERT INTO schema_version (version, description) VALUES
    (23, 'Gestes des contacts du portail : doute de doublon (doublon_de, doublon_raison), mail_declare, ne_pas_memoriser, renvoi des fusions (contact_fusion)')
ON CONFLICT (version) DO NOTHING;
