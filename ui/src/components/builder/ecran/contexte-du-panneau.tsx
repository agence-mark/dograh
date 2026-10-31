"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): what the editor lends to the panel and its cards, so the cards stay
 * independent of the editor's internals (nodes in a Zustand store, the page's own save, the test dialogs).
 */
import { createContext, useContext } from "react";

import type { GrapheDuBuilder } from "./graphe";

export interface ContexteDuPanneau {
    workflowId: number;
    /** The graph the editor holds right now (plain data). */
    lireLeGraphe: () => GrapheDuBuilder;
    /** Reads the agent's draft again from the server and puts it on the canvas (nothing unsaved is kept). */
    recharger: () => Promise<boolean>;
    /** Puts a graph on the canvas AND saves it as the draft (« Refuser » goes back to the graph from before). */
    restaurer: (graphe: GrapheDuBuilder) => Promise<boolean>;
    /** The existing phone-call window and keyboard tester, on the draft (B28). */
    appelerLAgent: () => void;
    essayerAuClavier: () => void;
}

const Contexte = createContext<ContexteDuPanneau | null>(null);

export const FournisseurDuPanneau = Contexte.Provider;

export function useContexteDuPanneau(): ContexteDuPanneau {
    const valeur = useContext(Contexte);
    if (!valeur) throw new Error("The builder panel context is missing");
    return valeur;
}
