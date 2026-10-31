/**
 * [.mark] builder-agent-vocal (lot 4): what the screen remembers about the builder, for ONE open editor.
 *
 *  - the panel (open or not), the node the person asked about (`@node`);
 *  - the changes under review: the graph `avant` (as it was when the builder started), the construction
 *    operations drawn live, the before/after switch, and the summary of the saved draft;
 *  - the context of the agent (deposits, sheet, proposed knowledge-base documents), read from the server and
 *    refreshed after every action of the builder.
 *
 * Nothing here is saved: the server keeps the agent, the sheet and the draft. Zustand, as the rest of the editor.
 */
import { create } from "zustand";

import { lireLeContexteApiV1BuilderContexteWorkflowIdGet } from "@/client";
import type { VueContexte } from "@/client/types.gen";

import type { Bascule, GrapheDuBuilder, OperationDuBuilder } from "./graphe";

export interface ChangementsEnregistres {
    version?: number;
    nombreOperations?: number;
    noeuds?: number;
    liaisons?: number;
}

export interface Citation {
    id: string;
    nom: string;
}

interface EtatDuBuilder {
    ouvert: boolean;
    pleinEcran: boolean;
    reglagesOuverts: boolean;
    /** The Deposit card pinned above the conversation (opened by « + »). */
    depotVisible: boolean;
    /** The graph as it was before the builder's changes; `null` when nothing is under review. */
    avant: GrapheDuBuilder | null;
    /** Construction operations received during the turn, not yet saved as a draft. */
    operationsVives: OperationDuBuilder[];
    bascule: Bascule;
    changements: ChangementsEnregistres | null;
    citation: Citation | null;
    enCours: boolean;
    contexte: VueContexte | null;
    contexteErreur: string | null;
}

interface ActionsDuBuilder {
    ouvrir: () => void;
    fermer: () => void;
    basculerLePanneau: () => void;
    definirPleinEcran: (actif: boolean) => void;
    ouvrirLesReglages: (ouverts: boolean) => void;
    montrerLeDepot: (visible: boolean) => void;
    /** First operation of a turn: remember the graph as it is. Later ones only add to the list. */
    recevoirUneOperation: (operation: OperationDuBuilder, grapheCourant: GrapheDuBuilder) => void;
    /** The draft was saved on the server: the operations are now part of the graph, the review stays. */
    brouillonEnregistre: (changements: ChangementsEnregistres, grapheCourant: GrapheDuBuilder) => void;
    choisirLaBascule: (bascule: Bascule) => void;
    /** Accepter or Refuser done: nothing left to review. */
    solderLesChangements: () => void;
    citer: (citation: Citation | null) => void;
    marquerEnCours: (actif: boolean) => void;
    rafraichirLeContexte: (workflowId: number) => Promise<void>;
    reinitialiser: () => void;
}

const VIDE: EtatDuBuilder = {
    ouvert: false,
    pleinEcran: false,
    reglagesOuverts: false,
    depotVisible: false,
    avant: null,
    operationsVives: [],
    bascule: "apres",
    changements: null,
    citation: null,
    enCours: false,
    contexte: null,
    contexteErreur: null,
};

export const useBuilderEcran = create<EtatDuBuilder & ActionsDuBuilder>((set) => ({
    ...VIDE,
    ouvrir: () => set({ ouvert: true }),
    fermer: () => set({ ouvert: false, pleinEcran: false }),
    basculerLePanneau: () => set((s) => ({ ouvert: !s.ouvert, pleinEcran: s.ouvert ? false : s.pleinEcran })),
    definirPleinEcran: (actif) => set({ pleinEcran: actif }),
    ouvrirLesReglages: (ouverts) => set({ reglagesOuverts: ouverts }),
    montrerLeDepot: (visible) => set({ depotVisible: visible }),
    recevoirUneOperation: (operation, grapheCourant) =>
        set((s) => ({
            avant: s.avant ?? grapheCourant,
            operationsVives: [...s.operationsVives, operation],
            bascule: "apres",
        })),
    brouillonEnregistre: (changements, grapheCourant) =>
        set((s) => ({
            avant: s.avant ?? grapheCourant,
            operationsVives: [],
            changements,
            bascule: "apres",
        })),
    choisirLaBascule: (bascule) => set({ bascule }),
    solderLesChangements: () => set({ avant: null, operationsVives: [], changements: null, bascule: "apres" }),
    citer: (citation) => set({ citation }),
    marquerEnCours: (actif) => set({ enCours: actif }),
    rafraichirLeContexte: async (workflowId) => {
        const reponse = await lireLeContexteApiV1BuilderContexteWorkflowIdGet({ path: { workflow_id: workflowId } });
        if (reponse.error || !reponse.data) {
            set({ contexteErreur: "context" });
            return;
        }
        set({ contexte: reponse.data, contexteErreur: null });
    },
    reinitialiser: () => set({ ...VIDE }),
}));
