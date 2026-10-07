-- =====================================================================
--  003 : rôles propres à CETTE base, et sécurité par ligne par site
--  (chantier l-agent-travaille, L3). Additive seulement.
--
--  Pourquoi : un rôle PostgreSQL appartient au SERVEUR, pas à une base. Les
--  rôles `mark_ecriture` et `mark_interface` de 001 sont donc partagés par
--  toutes les bases clientes d'un même serveur : un compte de connexion qui en
--  hériterait pourrait ouvrir la base d'un autre client. Cette migration
--  ferme la porte (plus de CONNECT pour PUBLIC) et crée des rôles nommés
--  d'après la base : <base>_ecriture, <base>_interface, <base>_direction.
--  L'accès par établissement (Metabase, plus tard) passe par `role_site` et la
--  sécurité par ligne : un rôle d'établissement ne voit que ses lignes.
-- =====================================================================
SET search_path = mark;

DO $$
DECLARE
    base text := current_database();
    ecriture text := base || '_ecriture';
    interface text := base || '_interface';
    direction text := base || '_direction';
BEGIN
    EXECUTE format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', base);
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = ecriture) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', ecriture);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = interface) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN', interface);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = direction) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN IN ROLE %I', direction, interface);
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO %I, %I', base, ecriture, interface);
    EXECUTE format('GRANT mark_ecriture TO %I', ecriture);
    EXECUTE format('GRANT mark_interface TO %I', interface);
END $$;

-- Quel rôle de connexion voit quel établissement (vide = rien, sauf la direction).
CREATE TABLE IF NOT EXISTS role_site (
    role    text   NOT NULL,
    site_id bigint NOT NULL REFERENCES site(id) ON DELETE CASCADE,
    PRIMARY KEY (role, site_id)
);

CREATE OR REPLACE FUNCTION voit_le_site(cible bigint) RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = mark AS $$
    SELECT cible IS NULL
        OR pg_has_role(current_user, current_database() || '_direction', 'MEMBER')
        OR NOT pg_has_role(current_user, 'mark_interface', 'MEMBER')
        OR EXISTS (SELECT 1 FROM role_site r WHERE r.role = current_user AND r.site_id = cible);
$$;

-- La sécurité par ligne ne vise que l'interface : le propriétaire (Dograh) la
-- contourne, `mark_ecriture` lit et écrit tout (NOT pg_has_role … mark_interface).
ALTER TABLE demande ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS demande_par_site ON demande;
CREATE POLICY demande_par_site ON demande USING (voit_le_site(site_id));
ALTER TABLE appel ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS appel_par_site ON appel;
CREATE POLICY appel_par_site ON appel USING (voit_le_site(site_id));

INSERT INTO schema_version (version, description) VALUES
    (3, 'Rôles propres à la base (plus de CONNECT public), accès par établissement par sécurité par ligne');
