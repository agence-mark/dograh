/**
 * [.mark] Builder partie 3, SA-L3a : « Régler » mène à l'endroit EXACT d'une ligne de « Prêt à publier ».
 * Une étape du graphe (`?etape=`), l'onglet Tests, ou un thème des Réglages de l'agent (sur la page des Réglages, le thème
 * s'ouvre sur place ; ailleurs, on y va).
 */
import type { LigneDePret } from "./ListePret";

export type Endroit = { sorte: "theme"; theme: string } | { sorte: "adresse"; adresse: string };

/** Les thèmes de la page des Réglages (`THEMES_AGENT`) : un thème inconnu ouvre la page sans thème. */
export function endroitDeLaLigne(ligne: Pick<LigneDePret, "noeud_id" | "onglet" | "theme">, workflowId: number): Endroit & { adresse: string; theme: string } {
    if (ligne.noeud_id) return { sorte: "adresse", adresse: `/workflow/${workflowId}?etape=${encodeURIComponent(ligne.noeud_id)}`, theme: ligne.theme };
    if (ligne.onglet === "tests") return { sorte: "adresse", adresse: `/workflow/${workflowId}/tests`, theme: ligne.theme };
    if (ligne.onglet === "parcours") return { sorte: "adresse", adresse: `/workflow/${workflowId}`, theme: ligne.theme };
    return { sorte: "theme", theme: ligne.theme, adresse: `/workflow/${workflowId}/settings?theme=${encodeURIComponent(ligne.theme)}` };
}
