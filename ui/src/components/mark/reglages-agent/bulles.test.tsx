/**
 * [.mark] Les bulles d'information de la partie Agents, réécrites (sous-lot 16, d'après `03-reglages-generaux-builder-bulles.md` § 3).
 *
 * | Test | La garantie |
 * |---|---|
 * | historique | aucune anecdote de développement ni « jusqu'ici » dans ce que le client lit |
 * | aide pour chaque réglage | chaque réglage du catalogue a son aide, dans les deux langues ; les réglages repris d'amont aussi (ambiance, transcription, standard externe) |
 * | fausses réécrites | Interventions dit les deux interrupteurs éteints par défaut ; « Toujours répondre » ne promet plus « toujours » ; les tests obligatoires ne « bloquent » que sur « Bloque » ; durée maximale, dupliquer, étape de départ, démarrage différé, statut « recette » |
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TEXTE_TEST_OBLIGATOIRE } from "@/components/builder/tests/FenetreDeTest";
import { NodeEditForm } from "@/components/flow/renderer/NodeEditForm";
import { localiserLaPropriete } from "@/components/flow/renderer/libelles-fr";
import type { NodeSpec } from "@/client/types.gen";

import { TEXTE_DUPLIQUER } from "../BoutonDupliquerAgent";
import { proprietesMasquees } from "../graphe/sections-noeud";
import specs from "../graphe/specs-premiere-replique.json";
import { FournisseurLangue } from "../langue/langue";
import { CATALOGUE } from "./catalogue";
import { MarqueStatut } from "./modeles-de-reglages/marque-statut";
import { DESCRIPTION_INTERVENTIONS } from "./ThemeInterventions";
import { AIDE_DUREE_MAXIMALE } from "./ThemeRythme";

// Le catalogue des variables lit l'utilisateur connecté : le test le fournit.
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false, getAccessToken: async () => "t" }) }));

const SRC = join(__dirname, "..", "..", "..");
const lire = (f: string) => readFileSync(join(SRC, f), "utf8");

afterEach(cleanup);

/** Ce que le client ne lit pas : une anecdote de développement, un ticket, un « jusqu'ici » qui renvoie à un état d'avant. */
const HISTORIQUE = /jusqu'ici|until now|\bso far\b|cinq réécritures|five rewrites|2 appels sur 5|2 voice runs|ticket Pipecat|Pipecat ticket|Pipecat's own value|Valeur de Pipecat/i;

describe("[.mark] bulles : plus d'historique de développement", () => {
    it("ni le catalogue des réglages ni les thèmes ne racontent l'histoire du code", () => {
        const fichiers = [
            "components/mark/reglages-agent/catalogue.tsx",
            "components/mark/reglages-agent/ThemeVoix.tsx",
            "components/mark/reglages-agent/ThemeInterventions.tsx",
            "components/mark/reglages-agent/ThemeRythme.tsx",
        ];
        const trouves = fichiers.flatMap((f) =>
            lire(f)
                .split("\n")
                // Les commentaires de code gardent l'histoire ; seuls les textes montrés sont jugés.
                .filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l))
                .map((l, i) => ({ f, i: i + 1, l }))
                .filter(({ l }) => HISTORIQUE.test(l))
                .map(({ f: fichier, i }) => `${fichier}:${i}`),
        );
        expect(trouves).toEqual([]);
    });

    it("l'anglais ne renvoie pas à un nom de thème français (« Bricks » : le thème s'appelle « Services »)", () => {
        expect(lire("components/mark/graphe/TravailDeFond.tsx")).not.toMatch(/en: "[^"]*\bBricks\b/);
        expect(lire("components/mark/graphe/TravailDeFond.tsx")).toMatch(/set in Services/);
    });
});

describe("[.mark] bulles : chaque réglage a son aide", () => {
    it("chaque réglage du catalogue en a une, dans les deux langues", () => {
        const sans = Object.entries(CATALOGUE)
            .filter(([, def]) => {
                const aides = (def as { aides?: { en: string; fr: string }[] }).aides ?? [];
                return aides.length === 0 || aides.some((a) => !a.en.trim() || !a.fr.trim());
            })
            .map(([cle]) => cle);
        expect(sans).toEqual([]);
    });

    it("l'ambiance, la transcription horodatée et le standard externe ont la leur (réglages repris d'amont)", () => {
        const source = lire("components/mark/reglages-agent/ThemeVoix.tsx") + lire("components/mark/reglages-agent/ThemeDonnees.tsx");
        for (const cle of [
            "ambient_noise_configuration.enabled",
            "ambient_noise_configuration.volume",
            "transcript_configuration.include_end_timestamps",
            "external_pbx_field_mappings",
        ]) {
            const i = source.indexOf(`cle="${cle}"`);
            expect(i, cle).toBeGreaterThan(-1);
            // L'aide est dans les propriétés du même champ, avant la fin de son ouverture.
            expect(source.slice(i, i + 900), cle).toMatch(/aides=/);
        }
    });
});

describe("[.mark] bulles : les fausses, réécrites", () => {
    it("Interventions dit que deux interrupteurs sur douze sont éteints par défaut", () => {
        expect(DESCRIPTION_INTERVENTIONS.fr).not.toMatch(/Tout est allumé/);
        expect(DESCRIPTION_INTERVENTIONS.en).not.toMatch(/All on by default/);
        expect(DESCRIPTION_INTERVENTIONS.fr).toMatch(/Dix sont allumés par défaut/);
        expect(DESCRIPTION_INTERVENTIONS.fr).toMatch(/éteints par défaut/);
        expect(DESCRIPTION_INTERVENTIONS.en).toMatch(/off by default/);
    });

    it("« Toujours répondre après un outil » ne promet plus « toujours » : il couvre un cas étroit", () => {
        const def = CATALOGUE.relance_apres_outil;
        expect(def.libelle.fr).not.toMatch(/Toujours/);
        expect(def.libelle.en).not.toMatch(/Always/);
        expect(def.libelle.fr).toMatch(/finit trop tôt/);
    });

    it("un test obligatoire ne bloque que si le contrôle est sur « Bloque » (trois endroits)", () => {
        expect(TEXTE_TEST_OBLIGATOIRE.fr).toMatch(/« Bloque »/);
        expect(TEXTE_TEST_OBLIGATOIRE.en).toMatch(/« Blocks »/);
        for (const f of ["PageTests.tsx", "NouveauTest.tsx", "FenetreDeTest.tsx"]) {
            const source = lire(`components/builder/tests/${f}`);
            expect(source, f).not.toMatch(/fails blocks the publication|échoue bloque la publication/);
        }
        expect(lire("components/builder/tests/NouveauTest.tsx")).not.toMatch(/Obligatoire \(bloque la publication\)/);
    });

    it("la durée maximale dit son défaut, son plafond et ce qui se passe à la limite", () => {
        expect(AIDE_DUREE_MAXIMALE.fr).toMatch(/600 s/);
        expect(AIDE_DUREE_MAXIMALE.fr).toMatch(/1 200 s/);
        expect(AIDE_DUREE_MAXIMALE.fr).toMatch(/terminé/);
        expect(AIDE_DUREE_MAXIMALE.en).toMatch(/1,200 s/);
        expect(AIDE_DUREE_MAXIMALE.en).toMatch(/ended/);
        // Le plafond dit est celui du serveur.
        expect(lire("components/mark/bornes-reglages.ts")).toMatch(/max_call_duration: \{ min: 0, minStrict: true, max: 1200 \}/);
    });

    it("« Dupliquer » dit qu'un agent principal copie tout son groupe", () => {
        expect(TEXTE_DUPLIQUER.fr).toMatch(/principal copie tout son groupe/);
        expect(TEXTE_DUPLIQUER.en).toMatch(/main agent copies its whole group/);
    });

    it("« L'appelant peut couper la parole » dit que l'agent peut l'annuler ; « Démarrage différé » dit qu'il faut la messagerie vocale", () => {
        const fr = (nom: string) => {
            const p = (specs as unknown as Record<string, NodeSpec>).agentNode.properties.find((x) => x.name === nom) ?? (specs as unknown as Record<string, NodeSpec>).startCall.properties.find((x) => x.name === nom);
            return localiserLaPropriete(p!, "fr").description ?? "";
        };
        expect(fr("allow_interrupt")).toMatch(/peut l'annuler/);
        expect(fr("delayed_start")).toMatch(/messagerie vocale/);
    });

    it("le thème Agent annonce ce qu'il contient, pas seulement « nom, identifiant, variables, diffusion et rapport »", () => {
        expect(lire("components/mark/reglages-agent/ThemeAgent.tsx")).not.toMatch(/description=\{\{ en: "Name, ID, variables, deployment and report\."/);
    });

    it("le statut « recette » d'un modèle de réglages ne porte plus le nom de la recette d'un agent", () => {
        render(
            <FournisseurLangue>
                <MarqueStatut statut="recette" />
            </FournisseurLangue>,
        );
        expect(screen.getByText(/Éprouvé|Proven/)).toBeTruthy();
        expect(screen.queryByText("Recette")).toBeNull();
    });
});

describe("[.mark] étape de départ : « L'appelant peut couper la parole » est masqué (05 § 17)", () => {
    const champ = (type: "startCall" | "agentNode") => {
        render(
            <NodeEditForm
                spec={(specs as Record<string, unknown>)[type] as NodeSpec}
                values={{ name: "Étape", prompt: "x" }}
                onChange={() => {}}
                masquer={proprietesMasquees(type, {})}
                context={{ tools: [], documents: [], recordings: [] }}
            />,
        );
        return screen.queryByText("Allow Interruption");
    };

    it("masqué sur l'étape de départ, montré sur une autre étape", () => {
        expect(proprietesMasquees("startCall", {})).toContain("allow_interrupt");
        expect(proprietesMasquees("agentNode", {})).not.toContain("allow_interrupt");
        expect(champ("agentNode")).toBeTruthy();
        cleanup();
        expect(champ("startCall")).toBeNull();
    });
});

describe("[.mark] la fiche : la colonne « Origine » est « Rempli par » (05 § 17)", () => {
    it("le mot « origine » reste à l'origine d'une valeur de réglage (héritage), pas aux champs de la fiche", () => {
        const fiche = lire("components/mark/SectionFiche.tsx");
        expect(fiche).toMatch(/en: "Filled in by", fr: "Rempli par"/);
        expect(fiche).not.toMatch(/en: "Origin", fr: "Origine"/);
    });
});
