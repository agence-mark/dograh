-- =====================================================================
--  029 : la liaison à la caisse (accès, veille, avertissements) et le journal des tickets d'imprimante (module Restauration, lots 9 et 10).
--  Additive seulement. Droits par ``resto_droits`` (025).
--
--  - ``resto_liaison`` (026) garde l'état lisible par le portail. Elle reçoit : ``mode_passif`` (la relève toutes les 30 s remplace les
--    messages signés si notre adresse de réception tombe), ``derniere_releve``, ``avertissements`` (codes, jamais un texte de caisse :
--    ex. ``horaires_differents``, jamais écrasés).
--  - ``resto_liaison_acces`` : la RÉFÉRENCE (jamais la valeur) du jeton de la caisse, rangé dans le coffre d'identifiants de Dograh.
--    Le portail n'y a aucun accès (et le journal des changements ne la copie pas : pas de déclencheur ici).
--  - ``resto_imprimante`` : l'imprimante d'un établissement (Star CloudPRNT). Son jeton n'est gardé qu'EN EMPREINTE.
--  - ``resto_ticket`` : un ticket par commande envoyée à l'imprimante ; le portail le lit (état d'impression).
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_liaison ADD COLUMN IF NOT EXISTS mode_passif boolean NOT NULL DEFAULT false;
ALTER TABLE resto_liaison ADD COLUMN IF NOT EXISTS derniere_releve timestamptz;
ALTER TABLE resto_liaison ADD COLUMN IF NOT EXISTS avertissements text[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS resto_liaison_acces (
    site_id         bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    credential_uuid text NOT NULL CHECK (btrim(credential_uuid) <> ''),
    maj_le          timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resto_imprimante (
    site_id                bigint PRIMARY KEY REFERENCES site(id) ON DELETE CASCADE,
    jeton_empreinte        text NOT NULL UNIQUE CHECK (char_length(jeton_empreinte) = 64),   -- SHA-256 en hexadécimal
    nom                    text,
    mode_planifiee         text NOT NULL DEFAULT 'differe' CHECK (mode_planifiee IN ('differe', 'immediat')),
    minutes_avant          integer NOT NULL DEFAULT 20 CHECK (minutes_avant >= 0),
    derniere_interrogation timestamptz,
    etat                   text NOT NULL DEFAULT 'inconnu' CHECK (etat IN ('inconnu', 'ok', 'papier', 'capot', 'erreur')),
    maj_le                 timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS resto_ticket (
    numero       uuid PRIMARY KEY REFERENCES resto_commande(numero) ON DELETE CASCADE,
    site_id      bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    statut       text NOT NULL DEFAULT 'en_file' CHECK (statut IN ('en_file', 'recupere', 'imprime', 'erreur')),
    liberer_le   timestamptz,                    -- vide : tout de suite
    programmee   boolean NOT NULL DEFAULT false, -- imprimée marquée « PROGRAMMÉE »
    code         text CHECK (code IS NULL OR char_length(code) <= 40),
    tentatives   integer NOT NULL DEFAULT 0 CHECK (tentatives >= 0),
    recupere_le  timestamptz,
    imprime_le   timestamptz,
    alerte_le    timestamptz,                    -- l'alerte « non imprimé » n'est dite qu'une fois
    cree_le      timestamptz NOT NULL DEFAULT now(),
    maj_le       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS resto_ticket_file_idx ON resto_ticket (site_id, statut, liberer_le);

DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['resto_liaison_acces', 'resto_imprimante', 'resto_ticket'] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I', t || '_maj_le', t);
        EXECUTE format('CREATE TRIGGER %I BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION resto_maj_le()', t || '_maj_le', t);
    END LOOP;
    PERFORM resto_droits('resto_liaison_acces', 'aucun');
    PERFORM resto_droits('resto_imprimante', 'aucun');
    PERFORM resto_droits('resto_ticket', 'lecture');
END $$;

INSERT INTO schema_version (version, description) VALUES
    (29, 'Module Restauration : accès de la liaison à la caisse (référence du jeton), veille et avertissements, imprimante Star CloudPRNT (jeton en empreinte), journal des tickets')
ON CONFLICT (version) DO NOTHING;
