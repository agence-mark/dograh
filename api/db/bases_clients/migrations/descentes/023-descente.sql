-- =====================================================================
--  Descente de la 023 (clôture, lot B) : retire les gestes des contacts du portail.
--  À jouer APRÈS la descente de la 024 (la 024 s'appuie sur doublon_de) et AVANT celle de la 022.
--  ⛔ Elle SUPPRIME les doutes de doublon, les mails déclarés, les « ne pas mémoriser » et le renvoi des fusions (table contact_fusion) :
--  sauvegarder la base avant, comme pour toute descente réelle. Idempotente (IF EXISTS partout).
-- =====================================================================
SET search_path = mark;

DROP TABLE IF EXISTS contact_fusion;
REVOKE UPDATE (contact_id) ON verification FROM mark_ecriture;
DROP INDEX IF EXISTS contact_doublon_de_idx;
ALTER TABLE contact DROP CONSTRAINT IF EXISTS contact_doublon_pas_lui_meme;
ALTER TABLE contact DROP CONSTRAINT IF EXISTS contact_doublon_raison_courte;
ALTER TABLE contact DROP COLUMN IF EXISTS ne_pas_memoriser;
ALTER TABLE contact DROP COLUMN IF EXISTS mail_declare;
ALTER TABLE contact DROP COLUMN IF EXISTS doublon_raison;
ALTER TABLE contact DROP COLUMN IF EXISTS doublon_de;

DELETE FROM schema_version WHERE version = 23;
