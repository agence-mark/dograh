/**
 * [.mark] L6+ (audit 01 A8) : la PORTE à identifiant stable. Le nom de la fonction qu'un modèle appelle pour passer une liaison est
 * son `identifiant` ; sans identifiant (ancien graphe), il vient du libellé, comme avant. Renommer le libellé pose l'identifiant
 * manquant (le nom d'avant) : la porte garde son nom, et les conditions, traces et tests qui la citent restent justes. Même règle
 * que `api/services/workflow/portes.py`.
 */
export const nomDuLibelle = (label: string): string => label.toLowerCase().replace(/[^a-z0-9]/g, "_");

const IDENTIFIANT = /^[a-z0-9_]{1,200}$/;

/** L'identifiant à garder après une modification de la liaison (`undefined` : pas encore posé, le libellé n'a pas changé). */
export const identifiantGarde = (avant: { label?: string; identifiant?: string } | undefined, nouveauLabel: string): string | undefined => {
    if (avant?.identifiant && IDENTIFIANT.test(avant.identifiant)) return avant.identifiant;
    if (avant?.label && avant.label !== nouveauLabel) {
        const nom = nomDuLibelle(avant.label);
        return IDENTIFIANT.test(nom) ? nom : undefined;
    }
    return undefined;
};
