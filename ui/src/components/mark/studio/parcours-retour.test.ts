// @vitest-environment node
/**
 * [.mark] T6 (lot « façon Tala par motif », Evan 05/11) : le parcours a ses flèches retour, aucun cul-de-sac.
 *
 * Quatre questions, et seulement elles :
 *   1. Toute page ouverte depuis une autre (une adresse à identifiant, ou « créer / modifier ») porte-t-elle sa flèche retour ?
 *      Une page neuve qui n'est ni dans `PAGES_AVEC_RETOUR` ni dans `EXEMPTEES` (avec sa raison) fait échouer ce test.
 *   2. Une flèche retour est-elle écrite à la main dans une page ? Elle vient du composant commun (`FlecheRetour`,
 *      `TitrePage retour`, la croix-flèche du `Dialog` imbriqué, la flèche de `EnteteAgent`) : un écart se corrige LÀ.
 *   3. Une adresse de retour ramène-t-elle à la liste du MÊME espace (jamais un `/campaigns` neutre qui part chez le Labo) ?
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

import { describe, expect, it } from "vitest";

const SRC = join(__dirname, "..", "..", "..");
const lire = (chemin: string) => readFileSync(join(SRC, chemin), "utf8");
const joli = (f: string) => relative(SRC, f).split(sep).join("/");
function parcourir(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
        const chemin = join(dossier, nom);
        if (nom === "client" || nom === "node_modules") return [];
        return statSync(chemin).isDirectory() ? parcourir(chemin) : [chemin];
    });
}

/** L'écran qui porte la page (une page qui ne fait que ré-exporter une autre se lit à travers elle). */
function mise(fichier: string): string {
    const m = lire(fichier).match(/export \{ default \} from "@\/([^"]+)";/);
    if (!m) return fichier;
    for (const ext of [".tsx", "/index.tsx", ".ts"]) {
        try {
            statSync(join(SRC, m[1] + ext));
            return mise(m[1] + ext);
        } catch {
            // essai suivant
        }
    }
    return fichier;
}

/** Ce qui prouve une flèche retour dans le fichier qui dessine la page. */
const PREUVES = {
    titre: /<TitrePage[\s\S]{0,60}?retour=\{/,
    fleche: /<FlecheRetour\b/,
    entete: /data-fleche-retour/,
} as const;

/** Les pages ouvertes depuis une autre, avec l'écran qui les dessine, la preuve attendue et l'endroit où la flèche ramène. */
const PAGES_AVEC_RETOUR: Record<string, { ecran: string; preuve: keyof typeof PREUVES; retour: string }> = {
    "campagne (détail)": { ecran: "app/campaigns/[campaignId]/page.tsx", preuve: "titre", retour: "campagnes de l'espace" },
    "campagne (modifier)": { ecran: "app/campaigns/[campaignId]/edit/page.tsx", preuve: "titre", retour: "la campagne" },
    "configuration de téléphonie": { ecran: "app/telephony-configurations/[configId]/page.tsx", preuve: "fleche", retour: "téléphonie de l'espace" },
    "conversation (un appel)": { ecran: "app/workflow/[workflowId]/run/[runId]/page.tsx", preuve: "fleche", retour: "conversations de l'espace" },
    "fil d'un chat": { ecran: "components/builder/chat/FilDuBuilder.tsx", preuve: "fleche", retour: "chats de l'espace" },
    "fiche d'un client (relation)": { ecran: "components/mark/relation/EcransRelation.tsx", preuve: "fleche", retour: "clients de la relation" },
    "comparer deux branches": { ecran: "components/mark/agent/branches/PageComparer.tsx", preuve: "titre", retour: "l'agent" },
    "page d'un agent et ses onglets": { ecran: "components/mark/agent/EnteteAgent.tsx", preuve: "entete", retour: "agents de l'espace" },
};

/** Les pages à identifiant ou de création qui n'ont pas de flèche à elles, avec la raison écrite. */
const EXEMPTEES: Record<string, string> = {
    "app/campaigns/new/page.tsx": "fenêtre centrée posée sur la liste ; la croix la ferme et ramène à la liste de l'espace",
    "app/handler/[...stack]/page.tsx": "pile d'authentification de l'amont, hors parcours du studio",
    "app/workflow/[workflowId]/page.tsx": "redirigée vers /agents/<id> (lib/redirections.ts)",
    "app/workflow/[workflowId]/runs/page.tsx": "redirigée vers l'onglet Appels de l'agent",
    "app/workflow/[workflowId]/settings/page.tsx": "redirigée vers l'onglet Réglages de l'agent (EnteteAgent porte la flèche)",
    "app/workflow/[workflowId]/tests/page.tsx": "redirigée vers l'onglet Tests de l'agent",
};

describe("T6 : le parcours a ses flèches retour", () => {
    it("chaque page ouverte depuis une autre porte sa flèche retour (composant commun)", () => {
        const manques = Object.entries(PAGES_AVEC_RETOUR)
            .filter(([, { ecran, preuve }]) => !PREUVES[preuve].test(lire(ecran)))
            .map(([nom, { ecran }]) => `${nom} (${ecran})`);
        expect(manques).toEqual([]);
    });

    it("toute page à identifiant ou de création est déclarée : avec sa flèche, ou exemptée avec sa raison", () => {
        const declarees = new Set(Object.values(PAGES_AVEC_RETOUR).map((p) => p.ecran));
        const pages = parcourir(join(SRC, "app"))
            .map(joli)
            .filter((f) => /\/page\.tsx$/.test(f) && (/\[(?!org\])[^\]]+\]/.test(f) || /\/(new|edit)\//.test(f)));
        const nomsDeclares = [...declarees].map((e) => e.split("/").pop()!.replace(/\.tsx$/, ""));
        const inconnues = pages.filter((f) => {
            const ecran = mise(f);
            if (declarees.has(ecran) || declarees.has(f) || f in EXEMPTEES || ecran in EXEMPTEES) return false;
            // une page qui monte un écran déclaré (PageFil monte FilDuBuilder, la fiche monte EcransRelation)
            const texte = lire(ecran);
            if (nomsDeclares.some((n) => n !== "page" && texte.includes(n))) return false;
            // un onglet d'agent monte son écran sous EntetePageAgent : la flèche est celle de l'en-tête de l'agent
            return !/<EntetePageAgent\b/.test(lire(f));
        });
        expect(inconnues).toEqual([]);
    });

    it("aucune flèche retour n'est écrite à la main : elle vient du composant commun", () => {
        const AUTORISES = new Set([
            "components/mark/studio/titre-page.tsx", // FlecheRetour
            "components/ui/dialog.tsx", // fenêtre imbriquée (E71)
            "components/mark/agent/EnteteAgent.tsx", // flèche de la barre d'un agent
            "components/builder/chat/FilDuBuilder.tsx", // « Principale » : sortir d'une conversation relue, pas une page
            "components/mark/variables/EditeurDeTableau.tsx", // déplacer une colonne
            "app/handler/[...stack]/BackButton.tsx", // authentification de l'amont
            "app/workflow/[workflowId]/settings/page.tsx", // ancienne page de l'amont, remplacée par PageReglagesAgent
        ]);
        const fautifs = parcourir(SRC)
            .map(joli)
            .filter((f) => /\.tsx$/.test(f) && !/\.test\./.test(f))
            .filter((f) => /\bArrowLeft\b/.test(lire(f)) && !AUTORISES.has(f));
        expect(fautifs).toEqual([]);
    });

    it("une adresse de retour reste dans l'espace où l'on est (jamais un /campaigns, /telephony-configurations ou /labo en dur)", () => {
        const sources = [
            "app/campaigns/[campaignId]/page.tsx",
            "app/campaigns/[campaignId]/edit/page.tsx",
            "app/telephony-configurations/[configId]/page.tsx",
            "app/workflow/[workflowId]/run/[runId]/page.tsx",
        ];
        for (const f of sources) {
            const s = lire(f);
            expect(s, f).toMatch(/useBaseEspace/);
            expect(s, f).not.toMatch(/retour=\{\{\s*href:\s*['"`]\/|<FlecheRetour[^>]*href=['"`]\//);
        }
    });
});
