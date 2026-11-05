import type { Texte } from "@/components/mark/langue/langue";

import { T, texte } from "./textes";
import type { PilotageClient } from "./types";

/**
 * [.mark] Partie 3, L5b : la liste « À faire maintenant » (décision 16). Le serveur donne les alertes actives, les problèmes graves
 * et l'installation ; les intégrations à reconnecter viennent de la lecture des connexions que la page fait déjà pour ses
 * branchements (une seule lecture par donnée). Ordre : alertes, intégrations, problèmes graves, étape d'installation suivante.
 */
export type ItemAFaire = {
    id: string;
    gravite: "grave" | "normal";
    texte: Texte;
    bouton: "regler" | "ouvrir" | "reprendre";
    /** Une adresse du client (relative à `/clients/<org>`), ou rien : « Reprendre » ouvre la fenêtre d'installation. */
    vers?: string;
};

export type ConnexionALire = { integration: string; connecteur?: string | null; erreurs?: number };

export function construireAFaire(pilotage: PilotageClient | null, connexions: ConnexionALire[] | null): ItemAFaire[] {
    const items: ItemAFaire[] = [];
    for (const a of pilotage?.alertes?.liste ?? []) {
        items.push({
            id: `alerte-${a.id}`,
            gravite: "grave",
            texte: {
                en: `${T.alerte.en}${a.workflow_nom ? ` (${a.workflow_nom})` : ""}: ${a.resume}`,
                fr: `${T.alerte.fr}${a.workflow_nom ? ` (${a.workflow_nom})` : ""} : ${a.resume}`,
            },
            bouton: "ouvrir",
            vers: "qualite?onglet=alertes",
        });
    }
    for (const c of (connexions ?? []).filter((x) => (x.erreurs ?? 0) > 0)) {
        const nom = c.connecteur || c.integration;
        items.push({
            id: `connexion-${c.integration}`,
            gravite: "grave",
            texte: { en: `${nom} ${T.aReconnecter.en}`, fr: `${nom} ${T.aReconnecter.fr}` },
            bouton: "regler",
            vers: "integrations",
        });
    }
    if (pilotage?.problemes_graves) {
        items.push({ id: "problemes-graves", gravite: "normal", texte: texte(T.problemesGraves, pilotage.problemes_graves), bouton: "ouvrir", vers: "a-ameliorer" });
    }
    const installation = pilotage?.installation;
    if (installation && installation.prochaine !== null) {
        const etape = installation.etapes.find((e) => e.numero === installation.prochaine);
        if (etape) {
            items.push({
                id: "installation",
                gravite: "normal",
                texte: { en: T.etapeSuivante.en(etape.titre.en ?? etape.titre.fr), fr: T.etapeSuivante.fr(etape.titre.fr ?? etape.titre.en) },
                bouton: "reprendre",
            });
        }
    }
    return items;
}

/** Les blocs que le serveur n'a pas pu lire et qui comptent pour « À faire » (jamais un « Rien à faire » menteur). */
export const BLOCS_DE_LA_LISTE = ["alertes", "problemes", "installation"] as const;
export function blocsIllisibles(pilotage: PilotageClient | null): string[] {
    return (pilotage?.illisibles ?? []).filter((b) => (BLOCS_DE_LA_LISTE as readonly string[]).includes(b));
}
