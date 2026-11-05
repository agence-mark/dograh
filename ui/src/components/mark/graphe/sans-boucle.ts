/**
 * [.mark] Partie 3, sous-lot 20 : « empêcher les boucles ». Réglage de l'agent (`empecher_boucles` dans ses réglages) : quand il
 * est allumé, relier deux étapes de façon à fermer un cycle est refusé, et les cycles déjà là sont signalés.
 * Éteint par défaut. Ce réglage garde le DESSIN du graphe ; le moteur d'appel n'en est pas changé.
 */
export type Lien = { source: string; target: string };

/** Poser `source → target` fermerait-il un cycle ? (Une étape reliée à elle-même en est un.) */
export function fermeUnCycle(liens: Lien[], source: string, target: string): boolean {
    if (source === target) return true;
    const suivants = new Map<string, string[]>();
    for (const l of liens) suivants.set(l.source, [...(suivants.get(l.source) ?? []), l.target]);
    const pile = [target];
    const vus = new Set<string>();
    while (pile.length) {
        const courant = pile.pop()!;
        if (courant === source) return true;
        if (vus.has(courant)) continue;
        vus.add(courant);
        pile.push(...(suivants.get(courant) ?? []));
    }
    return false;
}

/** Les liaisons qui ferment un cycle dans le graphe tel qu'il est (pour les signaler quand le réglage est allumé). */
export function liensEnBoucle(liens: Lien[]): Lien[] {
    return liens.filter((l, i) => fermeUnCycle(liens.filter((_, j) => j !== i), l.source, l.target));
}
