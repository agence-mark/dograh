/**
 * [.mark] Partie 3, sous-lot 20 : les statistiques par étape du graphe. Aucun second comptage : on LIT ce que le moteur a
 * déjà écrit dans chaque appel (`gathered_context.nodes_visited`, la liste des étapes traversées, voir
 * `pipecat_engine.py`) sur les appels que la route existante des appels de l'agent rend. Une étape traversée plusieurs fois
 * dans un même appel compte une fois (c'est ce que le moteur écrit : la liste est dédoublonnée par nom d'étape).
 */
export type LatenceDUneEtape = { tours?: number; total?: { moyenne_ms?: number; pire_ms?: number } };
export type AppelLu = {
    gathered_context?: Record<string, unknown> | null;
    /** N3a : seule la latence par phase sort des annotations d'un appel (`annotations.latence`, rangée à la fin de l'appel). */
    annotations?: { latence?: { par_etape?: Record<string, LatenceDUneEtape> } | null } | null;
};

/** La latence d'une étape sur les appels lus : la moyenne PONDÉRÉE par les tours et le pire tour ; les appels non mesurés n'y comptent pas. */
export interface LatenceMesuree {
    moyenne_ms: number;
    pire_ms: number;
    /** Le nombre de tours mesurés sur cette étape. */
    tours: number;
}

export interface StatistiquesDesEtapes {
    /** Le nombre d'appels lus. */
    appels: number;
    /** Étape (par son nom) → nombre d'appels qui l'ont traversée. */
    parEtape: Record<string, number>;
    /** Étape (par son nom) → sa latence, absente quand aucun appel lu ne l'a mesurée (« non mesuré », jamais zéro). */
    latenceParEtape: Record<string, LatenceMesuree>;
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
    const cumul: Record<string, { somme: number; tours: number; pire: number }> = {};
    for (const appel of appels) {
        for (const [nom, mesure] of Object.entries(appel.annotations?.latence?.par_etape ?? {})) {
            const moyenne = mesure?.total?.moyenne_ms;
            const tours = mesure?.tours;
            if (typeof moyenne !== "number" || typeof tours !== "number" || tours <= 0) continue;
            const c = (cumul[nom] ??= { somme: 0, tours: 0, pire: 0 });
            c.somme += moyenne * tours;
            c.tours += tours;
            c.pire = Math.max(c.pire, typeof mesure.total?.pire_ms === "number" ? mesure.total.pire_ms : moyenne);
        }
        const visites = appel.gathered_context?.nodes_visited;
        if (!Array.isArray(visites)) continue;
        const vues = new Set(visites.map(nomDeLEtape).filter((n): n is string => n !== null));
        vues.forEach((nom) => {
            parEtape[nom] = (parEtape[nom] ?? 0) + 1;
        });
    }
    const latenceParEtape = Object.fromEntries(
        Object.entries(cumul).map(([nom, c]) => [nom, { moyenne_ms: Math.round(c.somme / c.tours), pire_ms: Math.round(c.pire), tours: c.tours }]),
    );
    return { appels: appels.length, parEtape, latenceParEtape };
}

/** La latence d'une étape, ou `null` quand aucun appel lu ne l'a mesurée. */
export const latenceDeLEtape = (stats: StatistiquesDesEtapes, nom: string): LatenceMesuree | null => stats.latenceParEtape[nom] ?? null;

/** La part des appels lus qui ont traversé l'étape, en pour cent entier ; `null` sans appel lu. */
export const partDesAppels = (stats: StatistiquesDesEtapes, nom: string): number | null =>
    stats.appels === 0 ? null : Math.round(((stats.parEtape[nom] ?? 0) / stats.appels) * 100);
