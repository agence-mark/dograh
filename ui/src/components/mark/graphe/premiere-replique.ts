/**
 * [.mark] Plan porte-parlee (D3): the steps a transition leads to that have no
 * "First reply". The screen lists them under « Transitions in the reply »,
 * without blocking: the code then shows the model a generic line instead.
 *
 * The same rule as `etapes_sans_premiere_replique` in
 * `api/services/workflow/porte_parlee.py` (convention E8): a step reached by an
 * edge, never the greeting, whose `premiere_replique` is empty or blank. Both
 * are played on the same graph by their tests.
 */

interface NoeudDuGraphe {
    id: string;
    type?: string;
    data?: { name?: string; premiere_replique?: string | null };
}

interface AreteDuGraphe {
    target: string;
}

export const etapesSansPremiereReplique = (definition: {
    nodes?: NoeudDuGraphe[];
    edges?: AreteDuGraphe[];
} | null | undefined): string[] => {
    const cibles = new Set((definition?.edges ?? []).map((arete) => arete.target));
    return (definition?.nodes ?? [])
        .filter(
            (noeud) =>
                cibles.has(noeud.id)
                && noeud.type !== "startCall"
                && !(noeud.data?.premiere_replique ?? "").trim(),
        )
        .map((noeud) => noeud.data?.name ?? noeud.id);
};
