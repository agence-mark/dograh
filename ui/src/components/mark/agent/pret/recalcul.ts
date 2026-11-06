/**
 * [.mark] Builder partie 3, SA-L3a : « Prêt à publier » se recalcule après chaque enregistrement et chaque geste du builder.
 * Un compteur que tout enregistrement incrémente ; chaque liste affichée le lit et relit le serveur (rien n'est gardé côté écran).
 */
import { create } from "zustand";

export const useRecalculDuPret = create<{ n: number; demander: () => void }>((set) => ({
    n: 0,
    demander: () => set((s) => ({ n: s.n + 1 })),
}));
