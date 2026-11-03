/**
 * [.mark] builder partie 2, D1 (U4, E42, F3) : la liste de préparation et la pastille d'origine, rendues.
 *
 * - la liste est lue du serveur (rien de codé) : cercle rouge pour une étape requise, bleu pour une conseillée, coche
 *   pour une étape faite, rien pour une étape sans objet ; chaque ligne mène à son thème ;
 * - une lecture qui échoue le dit, sans inventer d'état ;
 * - la pastille d'origine dit l'origine de chaque réglage ; « propre à l'agent » offre « revenir à la valeur héritée »,
 *   jamais pour un réglage que le principal règle ni pour la configuration des modèles ; sans contexte, rien.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ChampReglage } from "../ecran/ChampReglage";
import { ContexteHeritage, type ReglageHerite } from "../ecran/heritage";
import { PreparationAgent } from "./PreparationAgent";

const m = vi.hoisted(() => ({
    reponse: { data: undefined, error: undefined } as { data?: unknown; error?: unknown },
}));

vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet: () => Promise.resolve(m.reponse),
    }),
);

afterEach(() => cleanup());

const etape = (id: string, niveau: string, etat: string, theme: string, manquants: string[] = []) => ({
    id,
    niveau,
    etat,
    theme,
    source: "x",
    manquants,
});

const monter = (ui: React.ReactNode) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("liste de préparation", () => {
    it("dessine le cercle de chaque étape, nomme ce qui manque et ouvre le thème de l'étape", async () => {
        m.reponse = {
            data: {
                etapes: [
                    etape("variables", "requis", "a_faire", "agent", ["ville"]),
                    etape("briques", "requis", "fait", "briques"),
                    etape("outils", "requis", "sans_objet", "agent"),
                    etape("panne", "conseille", "a_faire", "etablissement"),
                ],
            },
        };
        const versTheme = vi.fn();
        monter(<PreparationAgent workflowId={1} versTheme={versTheme} />);
        await waitFor(() => expect(document.querySelector("[data-preparation='liste']")).not.toBeNull());
        expect(document.querySelector("[data-etape='variables'] [data-cercle='requis']")).not.toBeNull();
        expect(document.querySelector("[data-etape='briques'] [data-cercle='fait']")).not.toBeNull();
        expect(document.querySelector("[data-etape='panne'] [data-cercle='conseille']")).not.toBeNull();
        // Sans objet : pas de ligne.
        expect(document.querySelector("[data-etape='outils']")).toBeNull();
        expect(screen.getByText("ville")).toBeTruthy();
        expect(document.querySelector("[data-preparation='restantes']")?.textContent).toBe("1 obligatoire à faire");
        fireEvent.click(document.querySelector("[data-etape='variables'] button")!);
        expect(versTheme).toHaveBeenCalledWith("agent");
    });

    it("dit quand la lecture échoue, sans inventer d'étape", async () => {
        m.reponse = { data: undefined, error: { detail: "boom" } };
        monter(<PreparationAgent workflowId={1} versTheme={vi.fn()} />);
        await waitFor(() => expect(document.querySelector("[data-preparation='echec']")).not.toBeNull());
        expect(document.querySelector("[data-etape]")).toBeNull();
    });
});

describe("pastille d'origine", () => {
    const reglage = (r: Partial<ReglageHerite>): ReglageHerite => ({
        origine: "defaut",
        valeur: 1,
        valeur_heritee: 1,
        propre: false,
        modifiable: true,
        masquee: false,
        ...r,
    });
    const champ = (cle: string) => (
        <ChampReglage cle={cle} libelle={{ en: cle, fr: cle }}>
            <input />
        </ChampReglage>
    );

    it("dit l'origine de chaque réglage", () => {
        monter(
            <ContexteHeritage.Provider
                value={{
                    reglages: {
                        a: reglage({ origine: "organisation" }),
                        b: reglage({ origine: "principal", modifiable: false }),
                        c: reglage({ origine: "etablissement" }),
                        d: reglage({ origine: "defaut" }),
                    },
                }}
            >
                {champ("a")}
                {champ("b")}
                {champ("c")}
                {champ("d")}
            </ContexteHeritage.Provider>,
        );
        const lire = (cle: string) => document.querySelector(`[data-reglage-origine='${cle}']`)?.textContent;
        expect(lire("a")).toBe("De l'organisation");
        expect(lire("b")).toBe("Réglé par l'agent principal");
        expect(lire("c")).toBe("De l'établissement");
        expect(lire("d")).toBe("Valeur par défaut");
    });

    it("offre « revenir » seulement à une valeur propre, modifiable et visible", () => {
        const revenir = vi.fn();
        monter(
            <ContexteHeritage.Provider
                value={{
                    reglages: {
                        propre: reglage({ origine: "agent", propre: true }),
                        du_principal: reglage({ origine: "principal", propre: false, modifiable: false }),
                        modeles: reglage({ origine: "agent", propre: true, masquee: true }),
                    },
                    revenir,
                }}
            >
                {champ("propre")}
                {champ("du_principal")}
                {champ("modeles")}
            </ContexteHeritage.Provider>,
        );
        expect(screen.getAllByText("Revenir à la valeur héritée")).toHaveLength(1);
        expect(document.querySelector("[data-reglage-origine='propre']")?.textContent).toContain("Propre à cet agent");
        fireEvent.click(screen.getByText("Revenir à la valeur héritée"));
        expect(revenir).toHaveBeenCalledWith("propre");
    });

    it("n'affiche aucune origine sans contexte ni pour une clé inconnue", () => {
        monter(champ("seul"));
        expect(document.querySelector("[data-reglage-origine]")).toBeNull();
        monter(
            <ContexteHeritage.Provider value={{ reglages: {} }}>{champ("inconnue")}</ContexteHeritage.Provider>,
        );
        expect(document.querySelector("[data-reglage-origine='inconnue']")).toBeNull();
    });
});
