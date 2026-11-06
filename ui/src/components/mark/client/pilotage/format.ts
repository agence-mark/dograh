import type { Langue } from "@/components/mark/langue/langue";

import type { ChiffrePilotage } from "./types";

/** [.mark] Partie 3, L5b : la valeur affichée de chaque chiffre de la période (une seule mise en forme, testée). */
const nombre = (n: number, langue: Langue, max = 0) =>
    new Intl.NumberFormat(langue === "fr" ? "fr-FR" : "en-GB", { maximumFractionDigits: max }).format(n);

export function valeurAffichee(c: ChiffrePilotage, langue: Langue): string {
    if (!c.disponible || c.valeur === null) return "–";
    switch (c.id) {
        case "appels":
            return nombre(c.valeur, langue);
        case "resolus":
        case "transferes":
            return `${nombre(c.valeur, langue)}${langue === "fr" ? " %" : "%"}`;
        case "note":
            return nombre(c.valeur, langue, 1);
        case "cout":
            // Le coût est celui du journal des appels, en dollars.
            return langue === "fr" ? `${nombre(c.valeur, langue, 3)} $` : `$${nombre(c.valeur, langue, 3)}`;
        case "duree": {
            const secondes = Math.round(c.valeur);
            const m = Math.floor(secondes / 60);
            const s = String(secondes % 60).padStart(2, "0");
            return m > 0 ? `${m} min ${s}` : `${secondes} s`;
        }
    }
}

/** Un chiffre dont la baisse est une bonne nouvelle (« haut » : monter est bon). */
export const SENS: Record<ChiffrePilotage["id"], "haut" | "bas" | "neutre"> = {
    appels: "neutre",
    resolus: "haut",
    transferes: "bas",
    note: "haut",
    cout: "bas",
    duree: "neutre",
};
