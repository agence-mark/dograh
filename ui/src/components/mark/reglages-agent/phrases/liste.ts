/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.7, 4.11) : ce que la liste du thème Phrases montre pour un agent.
 *
 * « Toutes les règles en vigueur pour cet agent, y compris les défauts du catalogue » : ses règles à lui (une
 * carte chacune), les règles du groupe héritées du principal quand c'est un spécialisé (en lecture), puis, pour
 * chaque motif qu'aucune règle ne couvre, la carte du défaut du catalogue (éteinte ou allumée comme le code).
 */
import type { ReglePhrase } from "@/types/workflow-configurations";

import {
    cleDeRegle,
    type EtapeGraphe,
    etapeSupprimee,
    motifDe,
    type MotifDePhrase,
    MOTIFS_DE_PHRASES,
    normaliserRegle,
    type Origine,
    origineDe,
    regleNeuve,
} from "./modele";

export interface LigneDeListe {
    id: string;
    regle: ReglePhrase;
    motif: MotifDePhrase;
    origine: Origine;
    /** Position dans le brouillon de l'agent ; null pour un défaut ou une règle héritée. */
    index: number | null;
    active: boolean;
    defaut: boolean;
    heritee: boolean;
    /** Héritée mais remplacée dans cet agent par une règle propre au même endroit. */
    remplacee: boolean;
    supprimee: boolean;
}

const RANG_PORTEE: Record<string, number> = { etape: 0, agent: 1, groupe: 2 };

export const lignesDeLaListe = (regles: ReglePhrase[], heritees: ReglePhrase[], etapes: EtapeGraphe[]): LigneDeListe[] => {
    const lignes: LigneDeListe[] = [];
    regles.forEach((brute, index) => {
        const regle = normaliserRegle(brute);
        const motif = motifDe(regle.motif);
        if (!motif) return;
        lignes.push({
            id: cleDeRegle(regle),
            regle,
            motif,
            origine: origineDe(regle),
            index,
            active: regle.active !== false,
            defaut: false,
            heritee: false,
            remplacee: false,
            supprimee: etapeSupprimee(regle, etapes),
        });
    });
    const propres = new Set(lignes.map((l) => l.id));
    for (const brute of heritees) {
        const regle = normaliserRegle(brute);
        const motif = motifDe(regle.motif);
        if (!motif) continue;
        const id = `heritee|${cleDeRegle(regle)}`;
        lignes.push({
            id,
            regle,
            motif,
            origine: "heritee",
            index: null,
            active: regle.active !== false,
            defaut: false,
            heritee: true,
            remplacee: propres.has(cleDeRegle({ ...regle, portee: "agent" })),
            supprimee: false,
        });
    }
    for (const motif of MOTIFS_DE_PHRASES) {
        if (lignes.some((l) => l.motif.id === motif.id)) continue;
        const regle = { ...regleNeuve(motif, { portee: "agent" }), active: motif.actif_par_defaut };
        lignes.push({
            id: `defaut|${motif.id}`,
            regle,
            motif,
            origine: "defaut",
            index: null,
            active: motif.actif_par_defaut,
            defaut: true,
            heritee: false,
            remplacee: false,
            supprimee: false,
        });
    }
    const ordreDuMotif = (l: LigneDeListe) => MOTIFS_DE_PHRASES.findIndex((m) => m.id === l.motif.id);
    return lignes
        .map((l, i) => ({ l, i }))
        .sort((a, b) => ordreDuMotif(a.l) - ordreDuMotif(b.l) || (RANG_PORTEE[a.l.regle.portee ?? "agent"] ?? 1) - (RANG_PORTEE[b.l.regle.portee ?? "agent"] ?? 1) || a.i - b.i)
        .map(({ l }) => l);
};
