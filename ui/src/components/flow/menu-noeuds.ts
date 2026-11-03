/**
 * [.mark] K2b : le menu « Nœud » de la barre du canevas (maquette `canevas.tsx`) : Étape · Fin · Global · Déclencheur ·
 * Webhook · Contrôle qualité, dans cet ordre, en français. Le serveur dit quels types existent ; ce module en retire ce que
 * l'écran ne propose pas (le début, qu'un agent a déjà, et les intégrations d'observation retirées en U1) et les range.
 * Remplace l'ancien panneau latéral d'ajout (`AddNodePanel`), retiré parce qu'il n'était plus monté.
 */
import type { NodeSpec } from "@/client/types.gen";

// [.mark] U1 : les intégrations d'observation de l'amont qui envoient un appel à un tiers ne sont plus proposées. Un parcours
// qui en porte déjà une continue de l'afficher (GenericNode) : seul le menu d'ajout change.
export const NOEUDS_RETIRES_DU_MENU: ReadonlySet<string> = new Set(["noveum", "paygent", "tuner"]);

/** L'ordre du menu de la maquette ; un type que ce tableau ne connaît pas passe après, dans l'ordre du serveur. */
export const ORDRE_DU_MENU = ["agentNode", "endCall", "globalNode", "trigger", "webhook", "qa"] as const;

/** Les types que le serveur sait poser, sans ceux que l'écran n'offre jamais (le début se pose à la création de l'agent). */
export const specsProposees = (specs: NodeSpec[]) => specs.filter((spec) => !NOEUDS_RETIRES_DU_MENU.has(spec.name));

/** Les entrées du menu « Nœud », dans l'ordre de la maquette. */
export function specsDuMenu(specs: NodeSpec[]): NodeSpec[] {
    const rang = (nom: string) => {
        const i = (ORDRE_DU_MENU as readonly string[]).indexOf(nom);
        return i === -1 ? ORDRE_DU_MENU.length : i;
    };
    return specsProposees(specs)
        .filter((spec) => spec.name !== "startCall")
        .map((spec, i) => ({ spec, i }))
        .sort((a, b) => rang(a.spec.name) - rang(b.spec.name) || a.i - b.i)
        .map(({ spec }) => spec);
}
