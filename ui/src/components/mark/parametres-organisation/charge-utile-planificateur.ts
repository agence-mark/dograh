/**
 * [.mark] Le contenu du planificateur écrit au serveur, commun aux fenêtres Rendez-vous de l'écran Entreprise, à la
 * fiche d'un établissement et aux tests (K4b/J : repris de l'ancien thème, retiré).
 */
import type { Planificateur, ReglagesPlanificateur } from "@/client/types.gen";

/** What the payload sends: empty strings and NaN become null (= the common default). */
export const charge_utile_planificateur = (p: Planificateur): Planificateur => {
    const propre = (r: ReglagesPlanificateur | undefined): ReglagesPlanificateur =>
        Object.fromEntries(
            Object.entries(r ?? {}).map(([k, v]) => [k, v === "" || (typeof v === "number" && Number.isNaN(v)) ? null : v]),
        ) as ReglagesPlanificateur;
    return {
        reglages: propre(p.reglages),
        par_etablissement: Object.fromEntries(Object.entries(p.par_etablissement ?? {}).map(([k, v]) => [k, propre(v)])),
        types: (p.types ?? []).map((x) => ({ ...x, libelle: x.libelle.trim(), sujet: x.sujet || null, etablissement: x.etablissement || null })),
    };
};
