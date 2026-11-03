/**
 * [.mark] « Prompt général » de la barre du canevas (E36) ouvre la fenêtre du nœud global : la fenêtre d'un nœud est un
 * état local du nœud, la barre lui adresse donc une demande par ce petit magasin. `cle` change à chaque demande, pour
 * qu'une seconde demande du même nœud rouvre la fenêtre.
 */
import { create } from "zustand";

type Demande = { id: string; cle: number } | null;

export const useOuvertureNoeud = create<{ demande: Demande; demander: (id: string) => void }>((set) => ({
    demande: null,
    demander: (id) => set((etat) => ({ demande: { id, cle: (etat.demande?.cle ?? 0) + 1 } })),
}));
