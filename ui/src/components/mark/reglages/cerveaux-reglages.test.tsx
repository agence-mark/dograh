/**
 * [.mark] K6 : les onglets « Builder IA » et « Appelant simulé » des Réglages du Labo. Questions : un champ quitté s'enregistre-t-il
 * (et une valeur inchangée n'écrit-elle rien) ? la clé n'est-elle jamais relue ? les sous-agents s'écrivent-ils par leur route ?
 * chaque écriture dit-elle son résultat par une notification ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { montant } from "@/components/mark/appelant-simule/montant";
import { OngletAppelantOuJuge, OngletBuilderIA } from "./CerveauxReglages";

const m = vi.hoisted(() => ({
    cerveauPut: vi.fn(),
    sousPut: vi.fn(),
    notifier: { suivre: vi.fn() },
    optionsPut: vi.fn(),
    // Ce que le serveur garde : l'écriture d'une option ne doit jamais en écraser une autre.
    options: { sauvegarde_avant_modification: false, builder_coupe: false, porte_ecran_coupee: false, porte_claude_code_coupee: true, recette_par_defaut: "" },
}));

const vueCerveaux = {
    builder: {
        prompt: { famille: "methode-builder", libelle_famille: "Méthode du builder", slug: "methode", titre: "Méthode du builder", version: 3, statut: "recette" },
        recoit: [{ cle: "methode", present: null }, { cle: "conventions", present: false }, { cle: "preferences", present: true }],
    },
    appelant: { prompt: { famille: "personnages-appelant", libelle_famille: "Personnages d'appelant", slug: "consigne", titre: null, version: null, statut: null }, recoit: [{ cle: "personnage", present: null }] },
    juge: { prompt: { famille: "criteres-types", libelle_famille: "Critères types", slug: "grille-juge", titre: null, version: null, statut: null }, recoit: [{ cle: "transcription", present: null }] },
    builder_actif: true,
    portes: { ecran: { ouverte: true, actions: 61 }, claude_code: { ouverte: false, actions: 58 }, source_du_builder: "cle_api" },
    depense_du_mois: 12.5,
    plafond_du_mois: 60,
    limites_du_juge: { passes_max: 3, seuil_de_confiance: 0.7, notes_min: 5, accord_min: 0.8 },
};

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: m.notifier }));
vi.mock("@/components/mark/sources/useSources", () => ({ useSources: () => ({ sources: { builder: "cle_api", appelant: "claude_code" } }) }));
vi.mock("@/components/builder/ecran/OptionsDeConstruction", () => ({ OptionsDeConstruction: () => <div data-testid="options-de-construction" /> }));
vi.mock("@/components/mark/appelant-simule/ModaleReglagesAppelantSimule", () => ({ ModaleReglagesAppelantSimule: ({ ouverte }: { ouverte: boolean }) => (ouverte ? <div>fenetre-reglages</div> : null) }));
vi.mock("@/client", () => ({
    lireLeCerveauApiV1BuilderCerveauGet: async () => ({ data: { format: "anthropic", modele: "claude-x", adresse: "", cle_posee: true, plafond_depense: 2, plafond_jetons: 1500000, plafond_mois: 60 } }),
    lireLesPreferencesApiV1BuilderPreferencesGet: async () => ({ data: { texte: "" } }),
    ecrireLesPreferencesApiV1BuilderPreferencesPut: async () => ({}),
    lireLesReglagesDesSousAgentsApiV1BuilderSousAgentsReglagesGet: async () => ({ data: { actif: true, usages: ["analyser", "tester"], modele: "m", en_meme_temps: 3, plafond_delegation: 1 } }),
    listerLesActionsApiV1BuilderActionsGet: async () => ({ data: [{ nom: "agent_lire", description: "d", groupe: "g", famille: "lecture", ecriture: false, disponible: true, mcp: true }, { nom: "tests_rejouer", description: "d", groupe: "tests", famille: "depense", ecriture: true, disponible: true, mcp: true }] }),
    reglerLeCerveauApiV1BuilderCerveauPut: (...a: unknown[]) => (m.cerveauPut(...a), Promise.resolve({ data: {} })),
    reglerLesSousAgentsApiV1BuilderSousAgentsReglagesPut: (...a: unknown[]) => (m.sousPut(...a), Promise.resolve({})),
    lireLesCerveauxApiV1BuilderCerveauxGet: async () => ({ data: vueCerveaux }),
    lireLesOptionsApiV1BuilderOptionsGet: async () => ({ data: { ...m.options } }),
    reglerLesOptionsApiV1BuilderOptionsPut: (o: { body: typeof m.options }) => (m.optionsPut(o), (m.options = o.body), Promise.resolve({ data: o.body })),
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet: async () => ({
        data: {
            appelant: { modele: "mistral/a", source: "cle_api", actif: true, budget_mois: 0 },
            juge: { modele: "mistral/j", source: "cle_api", actif: false, budget_mois: 7 },
            simultanes: 2,
        },
    }),
    getDepenseDesRolesApiV1AppelSimuleDepenseGet: async () => ({
        data: {
            mois: "2026-11-01",
            appelant: { appels: 2, jetons: 300, cout: 0.5, budget_mois: 0, actif: true, atteint: false },
            juge: { appels: 5, jetons: 900, cout: 3.25, budget_mois: 7, actif: false, atteint: true },
        },
    }),
}));

beforeEach(() => {
    vi.clearAllMocks();
    m.options = { sauvegarde_avant_modification: false, builder_coupe: false, porte_ecran_coupee: false, porte_claude_code_coupee: true, recette_par_defaut: "" };
});
afterEach(cleanup);

describe("Réglages du Labo, onglet Builder IA", () => {
    it("M-4 : les options de la construction ne sont plus ici (elles vivent dans la fenêtre du panneau, avec les plafonds)", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        await screen.findByText(/Modèle et clé|Model and key/);
        expect(screen.queryByTestId("options-de-construction")).toBeNull();
    });

    it("V4 : la ligne « Modèle et clé » montre le modèle et ouvre la fenêtre ; Enregistrer écrit le modèle, rien si on ferme", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const lu = (await screen.findByTestId("cerveau-modele-lu")) as HTMLInputElement;
        expect(lu.value).toBe("claude-x");
        expect(lu.readOnly).toBe(true);
        fireEvent.click(screen.getByTestId("ouvrir-modele-et-cle"));
        const champ = (await screen.findByLabelText(/^(Modèle|Model)$/, { selector: "input:not([readonly])" })) as HTMLInputElement;
        fireEvent.click(screen.getByRole("button", { name: /^(Annuler|Cancel)$/ }));
        expect(m.cerveauPut).not.toHaveBeenCalled();
        fireEvent.click(screen.getByTestId("ouvrir-modele-et-cle"));
        const champ2 = (await screen.findByLabelText(/^(Modèle|Model)$/, { selector: "input:not([readonly])" })) as HTMLInputElement;
        expect(champ.isConnected || champ2.isConnected).toBe(true);
        fireEvent.change(champ2, { target: { value: "claude-y" } });
        fireEvent.click(screen.getByRole("button", { name: /^(Enregistrer|Save)$/ }));
        await waitFor(() => expect(m.cerveauPut).toHaveBeenCalledTimes(1));
        expect(m.cerveauPut.mock.calls[0][0].body).toMatchObject({ modele: "claude-y", format: "anthropic" });
        expect(m.cerveauPut.mock.calls[0][0].body.cle).toBeUndefined();
        expect(m.notifier.suivre).toHaveBeenCalled();
    });

    it("ne relit jamais la clé et l'envoie seulement quand elle est saisie", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        fireEvent.click(await screen.findByTestId("ouvrir-modele-et-cle"));
        const cle = (await screen.findByLabelText(/^(Clé|Key)$/)) as HTMLInputElement;
        expect(cle.value).toBe("");
        expect(document.querySelector("[data-cle-posee]")?.getAttribute("data-cle-posee")).toBe("oui");
        fireEvent.change(cle, { target: { value: "secret-de-test" } });
        fireEvent.click(screen.getByRole("button", { name: /^(Enregistrer|Save)$/ }));
        await waitFor(() => expect(m.cerveauPut.mock.calls[0][0].body.cle).toBe("secret-de-test"));
    });

    it("écrit les sous-agents par leur route", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        fireEvent.click(await screen.findByRole("switch", { name: /Comparer|Compare/ }));
        await waitFor(() => expect(m.sousPut).toHaveBeenCalledTimes(1));
        expect(m.sousPut.mock.calls[0][0].body.usages).toContain("comparer");
    });

    it("liste les outils du registre et renvoie vers Sources", async () => {
        const aller = vi.fn();
        render(<OngletBuilderIA aller={aller} />);
        expect(await screen.findByText("agent_lire")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Sources" }));
        expect(aller).toHaveBeenCalled();
    });
});

describe("Réglages du Labo, onglet Builder IA : les vraies données (K7)", () => {
    it("montre le prompt système avec sa version et son statut, et ce qu'il reçoit avec les blocs vides ou absents", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        expect(await screen.findByText(/v3 · Proven/)).toBeTruthy();
        const liste = screen.getByText(/Conventions .mark|\.mark conventions/).closest("li") as HTMLElement;
        expect(liste.textContent).toMatch(/absent|missing/);
        expect((screen.getByText(/Vos préférences|Your preferences/).closest("li") as HTMLElement).textContent).not.toMatch(/vide|empty/);
    });

    it("É44 : les outils du builder se lisent par famille de permission, en phrases ; le nom technique reste dans le détail", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const lecture = await waitFor(() => {
            const el = document.querySelector('[data-famille-outils="lecture"]');
            if (!el) throw new Error("absent");
            return el as HTMLElement;
        });
        expect(lecture.textContent).toMatch(/Read the agent|Lire l'agent/);
        expect(document.querySelector('[data-famille-outils="depense"]')?.textContent).toMatch(/tests_rejouer/);
        expect(document.querySelector('[data-famille-outils="publication"]')).toBeNull();
    });

    it("É45 : libellés courts, unité à côté du champ, grands nombres groupés", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const jetons = (await screen.findByLabelText(/Tokens per conversation|Jetons par conversation/)) as HTMLInputElement;
        expect(jetons.value.replace(/\s/g, "")).toBe("1500000");
        expect(jetons.value).toMatch(/1\s500\s000/);
        const depense = (await screen.findByLabelText(/Spending per conversation|Dépense par conversation/)) as HTMLInputElement;
        expect(depense.parentElement?.textContent).toContain("$");
        expect(screen.queryByLabelText(/0 = aucun/)).toBeNull();
    });

    it("règle le plafond du mois par la route du cerveau et dit la dépense du mois", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const champ = (await screen.findByLabelText(/Par mois, tout le Labo|Per month, whole Lab/)) as HTMLInputElement;
        expect(champ.value).toBe("60");
        expect(screen.getByText(/12\.50 \$/)).toBeTruthy();
        fireEvent.change(champ, { target: { value: "80" } });
        fireEvent.blur(champ);
        await waitFor(() => expect(m.cerveauPut).toHaveBeenCalledTimes(1));
        expect(m.cerveauPut.mock.calls[0][0].body.plafond_mois).toBe(80);
    });

    it("R3 M2 : une virgule décimale se lit comme un point ; un texte non numérique est refusé sous le champ sans rien enregistrer", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const champ = (await screen.findByLabelText(/Spending per conversation|Dépense par conversation/)) as HTMLInputElement;
        fireEvent.change(champ, { target: { value: "2,5" } });
        fireEvent.blur(champ);
        await waitFor(() => expect(m.cerveauPut).toHaveBeenCalledTimes(1));
        expect(m.cerveauPut.mock.calls[0][0].body.plafond_depense).toBe(2.5);
        m.cerveauPut.mockClear();
        fireEvent.change(champ, { target: { value: "beaucoup" } });
        fireEvent.blur(champ);
        expect((await screen.findByRole("alert")).textContent).toMatch(/nombre|number/);
        expect(m.cerveauPut).not.toHaveBeenCalled();
    });

    it("l'interrupteur et les portes écrivent UNE option, sans écraser les autres", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const porte = await screen.findByRole("switch", { name: /Dans l'écran|In the screen/ });
        expect(porte.getAttribute("aria-checked")).toBe("true");
        // la porte de Claude Code est coupée côté serveur : son interrupteur le montre
        expect(screen.getByRole("switch", { name: /Dans Claude Code|In Claude Code/ }).getAttribute("aria-checked")).toBe("false");
        fireEvent.click(porte);
        await waitFor(() => expect(m.optionsPut).toHaveBeenCalledTimes(1));
        expect(m.optionsPut.mock.calls[0][0].body).toMatchObject({ porte_ecran_coupee: true, porte_claude_code_coupee: true });
        fireEvent.click(screen.getByRole("switch", { name: /Builder allumé|Builder on/ }));
        await waitFor(() => expect(m.optionsPut).toHaveBeenCalledTimes(2));
        expect(m.optionsPut.mock.calls[1][0].body).toMatchObject({ builder_coupe: true, porte_ecran_coupee: true });
    });
});

describe("Réglages du Labo, onglet Juge (K7)", () => {
    it("lit la version de sa grille et les limites réelles du juge", async () => {
        render(<OngletAppelantOuJuge role="juge" aller={vi.fn()} />);
        expect(await screen.findByText(/80 % /)).toBeTruthy();
        expect(screen.getByText("3")).toBeTruthy();
        expect(screen.getByText(/transcript|transcription/i)).toBeTruthy();
    });
});

describe("Réglages du Labo, onglet Appelant simulé", () => {
    it("lit ses réglages réels et ouvre la fenêtre de réglage", async () => {
        render(<OngletAppelantOuJuge role="appelant" aller={vi.fn()} />);
        expect(await screen.findByText("mistral/a")).toBeTruthy();
        expect(screen.getByText("2")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /Régler|Settings/ }));
        expect(screen.getByText("fenetre-reglages")).toBeTruthy();
    });
});

describe("Réglages du Labo, appelant simulé et juge séparés (lot 12)", () => {
    it("un montant s'écrit à la façon de la langue", () => {
        expect(montant(1.37, "fr").replace(/\s/g, "")).toBe("1,37");
        expect(montant(1.37, "en")).toBe("1.37");
        expect(montant(undefined, "en")).toBe("0.00");
    });

    it("chaque rôle montre son interrupteur, son budget du mois et ce qu'il a dépensé", async () => {
        const { unmount } = render(<OngletAppelantOuJuge role="appelant" aller={vi.fn()} />);
        await screen.findByText("mistral/a");
        expect(document.querySelector("[data-interrupteur-du-role]")?.textContent).toMatch(/Yes|Oui/);
        expect(document.querySelector("[data-budget-du-role]")?.textContent).toMatch(/No cap|Aucun plafond/);
        await vi.waitFor(() => expect(document.querySelector("[data-depense-du-role]")?.textContent).toBe("0.50"));
        unmount();
        render(<OngletAppelantOuJuge role="juge" aller={vi.fn()} />);
        await screen.findByText("mistral/j");
        expect(document.querySelector("[data-interrupteur-du-role]")?.textContent).toMatch(/No|Non/);
        expect(document.querySelector("[data-budget-du-role]")?.textContent).toBe("7");
        await vi.waitFor(() => expect(document.querySelector("[data-depense-du-role]")?.textContent).toMatch(/^3\.25 · (Budget reached|Budget atteint)$/));
    });
});
