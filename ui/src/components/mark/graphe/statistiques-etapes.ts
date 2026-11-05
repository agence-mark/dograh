/**
 * [.mark] Partie 3, sous-lot 20 : les statistiques par étape du graphe. Aucun second comptage : on LIT ce que le moteur a
 * déjà écrit dans chaque appel (`gathered_context.nodes_visited`, la liste des étapes traversées, voir
 * `pipecat_engine.py`) sur les appels que la route existante des appels de l'agent rend. Une étape traversée plusieurs fois
 * dans un même appel compte une fois (c'est ce que le moteur écrit : la liste est dédoublonnée par nom d'étape).
 */
export type AppelLu = { gathered_context?: Record<string, unknown> | null };

export interface StatistiquesDesEtapes {
    /** Le nombre d'appels lus. */
    appels: number;
    /** Étape (par son nom) → nombre d'appels qui l'ont traversée. */
    parEtape: Record<string, number>;
}

const nomDeLEtape = (v: unknown): string | null => {
    if (typeof v === "string") return v.trim() || null;
    if (v && typeof v === "object") {
        const e = v as Record<string, unknown>;
        for (const cle of ["etape", "step", "node", "name"]) {
            if (typeof e[cle] === "string" && (e[cle] as string).trim()) return (e[cle] as string).trim();
        }
    }
    return null;
};

export function lireLesEtapes(appels: AppelLu[]): StatistiquesDesEtapes {
    const parEtape: Record<string, number> = {};
    for (const appel of appels) {
        const visites = appel.gathered_context?.nodes_visited;
        if (!Array.isArray(visites)) continue;
        const vues = new Set(visites.map(nomDeLEtape).filter((n): n is string => n !== null));
        vues.forEach((nom) => {
            parEtape[nom] = (parEtape[nom] ?? 0) + 1;
        });
    }
    return { appels: appels.length, parEtape };
}

/** La part des appels lus qui ont traversé l'étape, en pour cent entier ; `null` sans appel lu. */
export const partDesAppels = (stats: StatistiquesDesEtapes, nom: string): number | null =>
    stats.appels === 0 ? null : Math.round(((stats.parEtape[nom] ?? 0) / stats.appels) * 100);
