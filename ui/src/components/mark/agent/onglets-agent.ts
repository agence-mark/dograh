/**
 * [.mark] Les cinq onglets de la page d'un agent (U3, E46) : Parcours · Réglages · Tests · Appels · Versions.
 * « Autour de l'appel » est supprimé. Chaque onglet est une adresse (`/agents/<id>`, `/agents/<id>/settings`...) :
 * un lien, un rechargement ou une ancienne adresse retombent au bon endroit.
 */
import type { Texte } from "@/components/mark/langue/langue";

export type OngletAgent = "parcours" | "reglages" | "tests" | "appels" | "versions";

export const ONGLETS_AGENT: { id: OngletAgent; titre: Texte; suite: string }[] = [
    { id: "parcours", titre: { en: "Flow", fr: "Parcours" }, suite: "" },
    { id: "reglages", titre: { en: "Settings", fr: "Réglages" }, suite: "/settings" },
    { id: "tests", titre: { en: "Tests", fr: "Tests" }, suite: "/tests" },
    { id: "appels", titre: { en: "Calls", fr: "Appels" }, suite: "/runs" },
    { id: "versions", titre: { en: "Versions", fr: "Versions" }, suite: "/versions" },
];

/** L'adresse d'un onglet de l'agent `agentId`. */
export const adresseOnglet = (agentId: number | string, onglet: OngletAgent): string =>
    `/agents/${agentId}${ONGLETS_AGENT.find((o) => o.id === onglet)?.suite ?? ""}`;

/** L'onglet que dit une adresse (`/agents/12/tests` → `tests`) ; toute autre suite est le Parcours. */
export function ongletDeAdresse(pathname: string): OngletAgent {
    const m = pathname.match(/^\/agents\/[^/]+\/([^/?#]+)/);
    return ONGLETS_AGENT.find((o) => m && o.suite === `/${m[1]}`)?.id ?? "parcours";
}
