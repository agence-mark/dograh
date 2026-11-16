-- =====================================================================
--  031 : la liste des DOUZE mécanismes de remise se ferme dans la base (chantier module-restauration, lot 20, demande de la fenêtre principale).
--  Additive : une contrainte ``CHECK`` sur ``resto_remise.mecanisme`` (liste fermée de ``restauration_remise.FAMILLE_DU_MECANISME``, E-52).
--  Posée ``NOT VALID`` : elle refuse toute NOUVELLE valeur ou modification hors liste, sans réécrire ni refuser les lignes déjà là (une ligne écrite avant,
--  d'un mécanisme inconnu, reste, jamais appliquée ni annoncée : la couche le garde déjà). Le portail écrit la table directement : la base est la dernière garde.
-- =====================================================================
SET search_path = mark;

ALTER TABLE resto_remise DROP CONSTRAINT IF EXISTS resto_remise_mecanisme_ferme;
ALTER TABLE resto_remise ADD CONSTRAINT resto_remise_mecanisme_ferme CHECK (mecanisme IN (
    'pourcentage', 'montant', 'x_achetes_y_offert', 'deuxieme_moitie_prix', 'prix_du_jour', 'seuil_panier',
    'passage_en_menu', 'taille_superieure', 'offre_famille', 'creneau', 'nouveaute', 'fidelite'
)) NOT VALID;

INSERT INTO schema_version (version, description) VALUES
    (31, 'Module Restauration : la liste des douze mécanismes de remise se ferme dans la base (resto_remise_mecanisme_ferme, posée NOT VALID : aucune ligne d''avant n''est touchée)')
ON CONFLICT (version) DO NOTHING;
