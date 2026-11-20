-- =====================================================================
--  Descente de la 050 (chantier Partie 1, lot 19 bis, K7). À jouer EN PREMIER (avant 049…). Idempotente.
--  Rend à l'ancien code l'heure et le jour (du lieu) de la fin posée, puis retire la colonne de l'instant.
-- =====================================================================
SET search_path = mark;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'mark' AND table_name = 'resto_reglage_type' AND column_name = 'fin_aujourd_hui_a') THEN
        UPDATE resto_reglage_type t
           SET fin_aujourd_hui = (t.fin_aujourd_hui_a AT TIME ZONE s.fuseau)::time,
               fin_aujourd_hui_le = (t.fin_aujourd_hui_a AT TIME ZONE s.fuseau)::date
          FROM site s
         WHERE s.id = t.site_id AND t.fin_aujourd_hui_a IS NOT NULL;
    END IF;
END $$;

ALTER TABLE IF EXISTS resto_reglage_type DROP COLUMN IF EXISTS fin_aujourd_hui_a;

DELETE FROM schema_version WHERE version = 50;
