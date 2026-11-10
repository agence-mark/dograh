/**
 * [.mark] Correctifs d'écran, point 3 : l'ordre des lignes de la liste des Agents. Chaque spécialisé est rangé SOUS son
 * principal (dans l'ordre du principal) quand ce principal est lui aussi dans la liste affichée ; sinon (autre dossier,
 * filtre, archive) il reste une ligne à part, jamais caché. Pur.
 */
export interface LigneAgent<A extends { id: number }> {
    agent: A;
    enfants: A[];
}

export const lignesAvecSpecialises = <A extends { id: number }>(
    visibles: A[],
    roles: Map<number, { role: "principal" | "specialise"; principalId: number | null; specialises: number[] }>,
): LigneAgent<A>[] => {
    const presents = new Set(visibles.map((a) => a.id));
    const rangeSous = (a: A) => {
        const r = roles.get(a.id);
        return r?.role === "specialise" && r.principalId != null && presents.has(r.principalId) ? r.principalId : null;
    };
    const enfantsDe = new Map<number, A[]>();
    for (const a of visibles) {
        const p = rangeSous(a);
        if (p !== null) enfantsDe.set(p, [...(enfantsDe.get(p) ?? []), a]);
    }
    return visibles
        .filter((a) => rangeSous(a) === null)
        .map((a) => {
            const ordre = roles.get(a.id)?.specialises ?? [];
            const enfants = (enfantsDe.get(a.id) ?? []).slice().sort((x, y) => {
                const i = ordre.indexOf(x.id);
                const j = ordre.indexOf(y.id);
                return (i < 0 ? ordre.length : i) - (j < 0 ? ordre.length : j);
            });
            return { agent: a, enfants };
        });
};
