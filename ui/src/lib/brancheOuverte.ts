/**
 * [.mark] Partie 3, SA-L3b : la branche d'agent ouverte dans CET onglet.
 *
 * Comme l'espace (`espaceCourant`), elle se retient dans le `sessionStorage` de l'onglet : deux onglets, deux branches, aucune
 * écriture croisée. Chaque requête faite depuis la page d'un agent porte l'en-tête `X-Mark-Branche` ; le serveur l'applique
 * seulement à l'agent dont la branche est la sienne (sur un autre agent, la principale). Sans branche retenue : aucun en-tête,
 * la principale, comme avant.
 */
export const ENTETE_BRANCHE = "X-Mark-Branche";
const prefixe = "mark:branche:";

/** L'agent que dit l'adresse (`/agents/12/...`, `/workflow/12/...`), ou `null`. */
export function agentDeAdresse(pathname: string): number | null {
    const m = pathname.match(/^\/(?:agents|workflow)\/(\d+)(?:\/|$)/);
    return m ? Number(m[1]) : null;
}

/** La branche ouverte sur cet agent dans cet onglet (`null` : la principale). */
export function brancheOuverte(agentId: number): number | null {
    try {
        const brut = window.sessionStorage.getItem(`${prefixe}${agentId}`);
        return brut && /^\d{1,9}$/.test(brut) ? Number(brut) : null;
    } catch {
        return null;
    }
}

/** Ouvre une branche (`null` : revient à la principale). */
export function ouvrirBranche(agentId: number, brancheId: number | null): void {
    try {
        if (brancheId === null) window.sessionStorage.removeItem(`${prefixe}${agentId}`);
        else window.sessionStorage.setItem(`${prefixe}${agentId}`, String(brancheId));
    } catch {
        /* stockage indisponible : la principale */
    }
}

/** L'en-tête à joindre aux requêtes d'une adresse, ou rien. */
export function entetesDeBranche(pathname: string): Record<string, string> {
    const agent = agentDeAdresse(pathname);
    if (agent === null) return {};
    const branche = brancheOuverte(agent);
    return branche === null ? {} : { [ENTETE_BRANCHE]: String(branche) };
}
