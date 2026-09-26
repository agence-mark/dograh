/**
 * [.mark] The trade vocabulary, as seen on screen.
 *
 * The questions this file answers:
 *
 *     Is the vocabulary editable on the Platform Settings page -- add, change,
 *     remove, import, export -- and does saving carry exactly what is typed?
 *     Is a refusal from the server shown rather than swallowed? On the agent's
 *     page, are the three switches there, on by default, and does each sound
 *     switch disappear while the switch it depends on is off, keeping its
 *     value?
 *
 *     🆕 26/09 (plan « le lexique », Q2, Q4): are the two boxes « Listen for
 *     it » and « The business offers it » there, each saved on its own? Is the
 *     budget the API computed shown as « N / ceiling tokens (provider) », with
 *     the terms left out -- and asked again for the draft being edited?
 *
 * ⛔ .mark rule: a setting we cannot see on screen is a setting we do not
 * touch. And a section that renders is not a section that is MOUNTED: the two
 * last tests render the pages themselves.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { SectionLexiqueMetier } from "./SectionLexiqueMetier";
import { SectionReglagesPipecat } from "./SectionReglagesPipecat";

const organisation = { stt: { provider: "deepgram", model: "nova-3-general" } };

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

const sdk = vi.hoisted(() => ({
    getLexiqueApiV1OrganizationsLexiqueGet: vi.fn(),
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
    budgetLexiqueApiV1OrganizationsLexiqueBudgetPost: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => sdk);

vi.mock("@/context/UnsavedChangesContext", () => ({
    useUnsavedChanges: () => undefined,
}));
vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ externalPbxIntegrationsEnabled: false, userConfig: organisation }),
}));
vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
    useAuth: () => ({ user: { id: "u-1" }, loading: false, redirectToLogin: vi.fn() }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

const LEXIQUE = {
    format: "lexique-mark",
    version: 1,
    modeles_importes: [],
    termes: [
        {
            terme: "Edilkamin",
            variantes: ["Edil Kamin"],
            prononciation: "édile kamine",
            type: "nom",
            categorie: "marque",
            a_ecouter: true,
            propose: true,
        },
    ],
};

const BUDGET = {
    fournisseur: "deepgram",
    nom_du_plafond: "Deepgram",
    plafond_jetons: 450,
    jetons: 212,
    envoyes: ["Edilkamin"],
    non_envoyes: [],
};

/** Un lexique de la taille de la vraie vie : c'est lui qui a motivé la modale. */
const LEXIQUE_LONG = {
    format: "lexique-mark",
    version: 1,
    modeles_importes: [],
    termes: [
        { terme: "Edilkamin", variantes: ["Edil Kamin"], prononciation: "édile kamine", type: "nom", categorie: "marque", a_ecouter: true },
        { terme: "Jøtul", variantes: [], prononciation: "yotoul", type: "nom", categorie: "marque", a_ecouter: false },
        { terme: "Flamebox", variantes: [], prononciation: null, type: "nom", categorie: "marque", a_ecouter: false },
        { terme: "Fonte Flamme", variantes: [], prononciation: null, type: "nom", categorie: "marque", a_ecouter: false },
        { terme: "ramonage", variantes: [], prononciation: null, type: "mot", categorie: "mot du métier", a_ecouter: false },
    ],
};

async function ouvrirLong() {
    sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({ data: LEXIQUE_LONG });
    render(<SectionLexiqueMetier />);
    fireEvent.click(await screen.findByRole("button", { name: /open vocabulary/i }));
    await screen.findByLabelText("Term 1");
}

const chercher = (texte: string) =>
    fireEvent.change(screen.getByLabelText("Search the vocabulary"), { target: { value: texte } });

const coche = (rang: number) =>
    screen.getByRole("switch", { name: `Listen for it ${rang}` }).getAttribute("aria-checked");

const offert = (rang: number) =>
    screen.getByRole("switch", { name: `The business offers it ${rang}` }).getAttribute("aria-checked");

beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.error.mockClear();
    sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockReset();
    sdk.saveLexiqueApiV1OrganizationsLexiquePut.mockReset();
    sdk.importLexiqueApiV1OrganizationsLexiqueImportPost.mockReset();
    sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockReset();
    sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockResolvedValue({ data: BUDGET });
    sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({ data: LEXIQUE });
    sdk.saveLexiqueApiV1OrganizationsLexiquePut.mockImplementation(
        async ({ body }: { body: unknown }) => ({ data: body }),
    );
});

async function ouvrirLexique() {
    render(<SectionLexiqueMetier />);
    // 🆕 18/09 : la liste vit dans une modale. Le résumé s'affiche sur la carte,
    // puis « Open vocabulary » ouvre ce qui s'éditait à plat avant.
    fireEvent.click(await screen.findByRole("button", { name: /open vocabulary/i }));
    await screen.findByLabelText("Term 1");
}

function charge() {
    return sdk.saveLexiqueApiV1OrganizationsLexiquePut.mock.calls[0][0].body;
}

describe("Carte « Trade vocabulary » des réglages de la plateforme", () => {
    it("affiche le lexique de l'organisation, avec ses colonnes", async () => {
        await ouvrirLexique();
        expect((screen.getByLabelText("Term 1") as HTMLInputElement).value).toBe("Edilkamin");
        expect((screen.getByLabelText("Other spellings 1") as HTMLInputElement).value).toBe(
            "Edil Kamin",
        );
        expect((screen.getByLabelText("Say it as 1") as HTMLInputElement).value).toBe(
            "édile kamine",
        );
        expect(document.body.textContent).toMatch(/Names are recognised and corrected/i);
    });

    it("ajoute un terme, écouté par défaut mais pas proposé, et l'emporte tel quel", async () => {
        await ouvrirLexique();
        fireEvent.click(screen.getByRole("button", { name: /add term/i }));
        fireEvent.change(screen.getByLabelText("Term 2"), { target: { value: "Jøtul" } });
        fireEvent.change(screen.getByLabelText("Other spellings 2"), {
            target: { value: "Jotul, Jotule" },
        });
        fireEvent.click(screen.getByRole("button", { name: /save trade vocabulary/i }));
        await waitFor(() => expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).toHaveBeenCalled());
        const envoye = charge().termes[1];
        expect(envoye).toEqual({
            terme: "Jøtul",
            variantes: ["Jotul", "Jotule"],
            prononciation: null,
            type: "nom",
            categorie: null,
            a_ecouter: true,
            // ⛔ Nobody said the business offers it: the agent must not either.
            propose: false,
        });
    });

    it("supprime une ligne", async () => {
        await ouvrirLexique();
        fireEvent.click(screen.getByRole("button", { name: /remove 1/i }));
        expect(screen.queryByLabelText("Term 1")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: /save trade vocabulary/i }));
        await waitFor(() => expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).toHaveBeenCalled());
        expect(charge().termes).toEqual([]);
    });

    it("affiche le refus du serveur au lieu de l'avaler", async () => {
        sdk.saveLexiqueApiV1OrganizationsLexiquePut.mockResolvedValue({
            error: {
                detail: [
                    {
                        msg: "Value error, « Godin » and « Cheminées Godin » share the spelling « godin »",
                    },
                ],
            },
        });
        await ouvrirLexique();
        fireEvent.click(screen.getByRole("button", { name: /save trade vocabulary/i }));
        await waitFor(() =>
            expect(document.body.textContent).toMatch(/share the spelling « godin »/),
        );
    });

    it("refuse d'enregistrer quand le lexique enregistré n'a pas pu être lu", async () => {
        // 🔴 Relecture du 17/09 : enregistrer remplace TOUT le lexique.
        sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({
            error: { detail: "The trade vocabulary saved for this organization cannot be read." },
        });
        render(<SectionLexiqueMetier />);
        await screen.findByText(/cannot be read/i);
        expect(document.body.textContent).toMatch(/Saving is disabled/i);
        // Ni ouvrir la modale, ni importer : les deux mènent à un remplacement.
        expect(
            (screen.getByRole("button", { name: /open vocabulary/i }) as HTMLButtonElement).disabled,
        ).toBe(true);
        expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).not.toHaveBeenCalled();
        // 🔴 L'import remplace lui aussi : il est désactivé tant qu'on n'a pas lu.
        expect(
            (screen.getByRole("button", { name: /import template/i }) as HTMLButtonElement)
                .disabled,
        ).toBe(true);
    });

    it("importe un modèle et affiche le résumé", async () => {
        sdk.importLexiqueApiV1OrganizationsLexiqueImportPost.mockResolvedValue({
            data: { ajoutes: 27, deja_presents: 3 },
        });
        await ouvrirLexique();
        const champ = screen.getByLabelText("Import template") as HTMLInputElement;
        const fichier = new File([JSON.stringify(LEXIQUE)], "poeles.json", {
            type: "application/json",
        });
        Object.defineProperty(fichier, "text", { value: async () => JSON.stringify(LEXIQUE) });
        fireEvent.change(champ, { target: { files: [fichier] } });
        await waitFor(() =>
            expect(sdk.importLexiqueApiV1OrganizationsLexiqueImportPost).toHaveBeenCalled(),
        );
        expect(toastMock.success).toHaveBeenCalledWith("27 added, 3 already there");
        // The screen reads the vocabulary again: the import is the server's answer.
        expect(sdk.getLexiqueApiV1OrganizationsLexiqueGet.mock.calls.length).toBeGreaterThan(1);
    });

    it("refuse un fichier qui n'est pas un lexique, sans rien envoyer", async () => {
        await ouvrirLexique();
        const fichier = new File(["pas du json"], "note.txt", { type: "text/plain" });
        Object.defineProperty(fichier, "text", { value: async () => "pas du json" });
        fireEvent.change(screen.getByLabelText("Import template"), {
            target: { files: [fichier] },
        });
        await waitFor(() =>
            expect(document.body.textContent).toMatch(/not a trade vocabulary/i),
        );
        expect(sdk.importLexiqueApiV1OrganizationsLexiqueImportPost).not.toHaveBeenCalled();
    });

    it("exporte le lexique au format attendu", async () => {
        const blobs: Array<Blob> = [];
        vi.stubGlobal("URL", {
            createObjectURL: (blob: Blob) => {
                blobs.push(blob);
                return "blob:lexique";
            },
            revokeObjectURL: () => {},
        });
        // L'export vit sur la carte : pas besoin d'ouvrir la modale.
        render(<SectionLexiqueMetier />);
        fireEvent.click(await screen.findByRole("button", { name: /export/i }));
        expect(blobs.length).toBe(1);
        const contenu = JSON.parse(await blobs[0].text());
        expect(contenu.format).toBe("lexique-mark");
        expect(contenu.termes[0].terme).toBe("Edilkamin");
        vi.unstubAllGlobals();
    });

    it("affiche le budget calculé par l'API pour le fournisseur, jamais un plafond écrit dans l'écran", async () => {
        render(<SectionLexiqueMetier />);
        await screen.findByText(/212 \/ 450 tokens \(Deepgram\)/);
        expect(document.body.textContent).toMatch(/Dictionary is sent first/);
        // Asked for what is SAVED: the API is the only one that counts.
        expect(sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost).toHaveBeenCalledWith({
            body: LEXIQUE,
        });
        expect(document.body.textContent).not.toMatch(/1600|characters in total/);
    });

    it("nomme les termes cochés qui ne partiraient pas", async () => {
        sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockResolvedValue({
            data: { ...BUDGET, jetons: 449, non_envoyes: ["Palazzetti", "Rika"] },
        });
        render(<SectionLexiqueMetier />);
        await screen.findByText(/Not sent \(2\): Palazzetti, Rika/);
    });

    it("dit qu'aucun terme n'est envoyé quand le fournisseur ne déclare pas de plafond", async () => {
        sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockResolvedValue({
            data: {
                fournisseur: "speechmatics",
                nom_du_plafond: null,
                plafond_jetons: null,
                jetons: 0,
                envoyes: [],
                non_envoyes: ["Edilkamin"],
            },
        });
        render(<SectionLexiqueMetier />);
        await screen.findByText(/No term is sent to the transcription: its provider \(speechmatics\)/);
    });

    it("sans réponse de l'API, la carte reste utilisable et ne montre aucun chiffre inventé", async () => {
        sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockResolvedValue({
            error: { detail: "boom" },
        });
        render(<SectionLexiqueMetier />);
        await screen.findByRole("button", { name: /open vocabulary/i });
        await waitFor(() =>
            expect(sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost).toHaveBeenCalled(),
        );
        expect(screen.queryByTestId("budget-lexique")).toBeNull();
    });
});

describe("La modale, la recherche et les deux boutons", () => {
    it("la carte ne montre qu'un résumé : la liste est derrière le bouton", async () => {
        sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({ data: LEXIQUE_LONG });
        render(<SectionLexiqueMetier />);
        await screen.findByRole("button", { name: /open vocabulary/i });
        expect(document.body.textContent).toMatch(/5 terms/);
        expect(document.body.textContent).toMatch(/1 listened for/);
        expect(document.body.textContent).toMatch(/2 pronunciations/);
        // Rien de la liste n'est rendu tant qu'on n'a pas ouvert.
        expect(screen.queryByLabelText("Term 1")).toBeNull();
        expect(screen.queryByLabelText("Search the vocabulary")).toBeNull();
    });

    it("ouvre la modale et referme sans rien changer", async () => {
        await ouvrirLong();
        fireEvent.change(screen.getByLabelText("Term 1"), { target: { value: "Autre chose" } });
        fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));
        await waitFor(() => expect(screen.queryByLabelText("Search the vocabulary")).toBeNull());
        expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).not.toHaveBeenCalled();
        // Rouverte, la modale repart de ce qui est enregistré.
        fireEvent.click(screen.getByRole("button", { name: /open vocabulary/i }));
        expect((await screen.findByLabelText("Term 1")).getAttribute("value")).toBe("Edilkamin");
    });

    it("la recherche ne garde que ce qui correspond, accents et casse ignorés", async () => {
        await ouvrirLong();
        chercher("flam");
        expect(screen.queryByLabelText("Term 1")).toBeNull();
        expect(screen.getByLabelText("Term 3")).toBeTruthy();
        expect(screen.getByLabelText("Term 4")).toBeTruthy();
        expect(document.body.textContent).toMatch(/2 shown/);
        // « jotul » trouve « Jøtul », « metier » trouve « mot du métier ».
        chercher("jotul");
        expect(screen.getByLabelText("Term 2")).toBeTruthy();
        chercher("metier");
        expect(screen.getByLabelText("Term 5")).toBeTruthy();
        chercher("xyz");
        expect(document.body.textContent).toMatch(/No term matches/);
    });

    it("coche et décoche ce qui est affiché, et rien d'autre", async () => {
        await ouvrirLong();
        chercher("flam");
        fireEvent.click(screen.getByRole("button", { name: /^tick the 2 shown$/i }));
        expect(coche(3)).toBe("true");
        expect(coche(4)).toBe("true");
        chercher("");
        // Edilkamin, hors de la recherche, garde sa case ; les autres aussi.
        expect(coche(1)).toBe("true");
        expect(coche(2)).toBe("false");
        expect(coche(5)).toBe("false");
        expect(document.body.textContent).toMatch(/3 of 5 listened for/);
    });

    it("sans recherche, les boutons portent sur tout le lexique", async () => {
        await ouvrirLong();
        fireEvent.click(screen.getByRole("button", { name: /^tick the 5 shown$/i }));
        expect(document.body.textContent).toMatch(/5 of 5 listened for/);
        fireEvent.click(screen.getByRole("button", { name: /^untick the 5 shown$/i }));
        expect(document.body.textContent).toMatch(/0 of 5 listened for/);
    });

    it("enregistre ce que la modale a changé, puis se referme", async () => {
        await ouvrirLong();
        chercher("flam");
        fireEvent.click(screen.getByRole("button", { name: /^tick the 2 shown$/i }));
        fireEvent.click(screen.getByRole("button", { name: /save trade vocabulary/i }));
        await waitFor(() => expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).toHaveBeenCalled());
        const envoye = charge().termes;
        expect(envoye.map((t: { a_ecouter: boolean }) => t.a_ecouter)).toEqual([
            true, false, true, true, false,
        ]);
        // ⚠️ Pas « Term 1 » : la recherche le masque déjà, l'assertion serait vraie
        // dialogue ouvert comme fermé. La barre de recherche, elle, n'existe que
        // dans le dialogue.
        await waitFor(() => expect(screen.queryByLabelText("Search the vocabulary")).toBeNull());
        // Le résumé de la carte suit.
        expect(document.body.textContent).toMatch(/3 listened for/);
    });

    it("un terme ajouté sous une recherche reste visible", async () => {
        await ouvrirLong();
        chercher("flam");
        fireEvent.click(screen.getByRole("button", { name: /add term/i }));
        expect((screen.getByLabelText("Search the vocabulary") as HTMLInputElement).value).toBe("");
        expect(screen.getByLabelText("Term 6")).toBeTruthy();
        expect((screen.getByLabelText("Term 6") as HTMLInputElement).value).toBe("");
    });
});

// --------------------------------------------------------------------------- //
// The three switches on the agent's page
// --------------------------------------------------------------------------- //

const ouvrirAgent = (configurations: Record<string, unknown> | null, onSave = vi.fn()) => {
    render(
        <SectionReglagesPipecat
            workflowConfigurations={resolveWorkflowConfigurations(configurations as never)}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

const interrupteur = (nom: RegExp) => screen.getByRole("switch", { name: nom });

describe("Les trois interrupteurs de l'agent", () => {
    it("sont allumés par défaut", () => {
        const defauts = resolveWorkflowConfigurations(null);
        expect(defauts.lexique_metier).toBe(true);
        expect(defauts.sons_communes).toBe(true);
        expect(defauts.sons_lexique).toBe(true);
        ouvrirAgent(null);
        for (const nom of [
            /use the organization's trade vocabulary/i,
            /use sounds to recognise towns/i,
            /use sounds to recognise names/i,
        ]) {
            expect(interrupteur(nom).getAttribute("aria-checked")).toBe("true");
        }
    });

    it("emportent false quand on les éteint", async () => {
        const onSave = ouvrirAgent(null);
        fireEvent.click(interrupteur(/use the organization's trade vocabulary/i));
        fireEvent.click(interrupteur(/use sounds to recognise towns/i));
        fireEvent.click(screen.getByRole("button", { name: /save speech tuning/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0].lexique_metier).toBe(false);
        expect(onSave.mock.calls[0][0].sons_communes).toBe(false);
        // Untouched, and still carried out.
        expect(onSave.mock.calls[0][0].sons_lexique).toBe(true);
    });

    it("gardent la valeur déjà enregistrée sur l'agent", () => {
        ouvrirAgent({ sons_lexique: false, lexique_metier: true });
        expect(interrupteur(/use sounds to recognise names/i).getAttribute("aria-checked")).toBe(
            "false",
        );
    });

    it("l'interrupteur des sons du lexique disparaît quand le lexique est éteint, et revient avec sa valeur", async () => {
        const onSave = ouvrirAgent({ lexique_metier: false, sons_lexique: false });
        expect(screen.queryByRole("switch", { name: /use sounds to recognise names/i })).toBeNull();
        fireEvent.click(interrupteur(/use the organization's trade vocabulary/i));
        expect(interrupteur(/use sounds to recognise names/i).getAttribute("aria-checked")).toBe(
            "false",
        );
        fireEvent.click(screen.getByRole("button", { name: /save speech tuning/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        // Hidden is not lost: the value travels with the rest.
        expect(onSave.mock.calls[0][0].sons_lexique).toBe(false);
    });

    it("l'interrupteur des sons des communes disparaît quand les communes sont éteintes, sans perdre sa valeur", async () => {
        const onSave = ouvrirAgent({ verification_communes: false, sons_communes: false });
        expect(screen.queryByRole("switch", { name: /use sounds to recognise towns/i })).toBeNull();
        fireEvent.click(interrupteur(/recognise the caller's town/i));
        expect(interrupteur(/use sounds to recognise towns/i).getAttribute("aria-checked")).toBe(
            "false",
        );
        fireEvent.click(screen.getByRole("button", { name: /save speech tuning/i }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0].sons_communes).toBe(false);
    });

    it("place les sons des communes APRÈS le champ des variables et sa notice", () => {
        ouvrirAgent(null);
        const texte = document.body.textContent ?? "";
        expect(texte.indexOf("Variables that trigger the town check")).toBeGreaterThan(-1);
        expect(texte.indexOf("Use sounds to recognise towns")).toBeGreaterThan(
            texte.indexOf("Leave empty to go back to the default"),
        );
        // And the vocabulary's own sound switch sits right under its switch.
        expect(texte.indexOf("Use sounds to recognise names")).toBeGreaterThan(
            texte.indexOf("Use the organization's trade vocabulary"),
        );
    });

    it("dit ce que chaque interrupteur fait", () => {
        ouvrirAgent(null);
        const texte = document.body.textContent ?? "";
        expect(texte).toMatch(/Listens for the ticked terms, corrects misheard names/i);
        expect(texte).toMatch(/pronunciation library\), in addition to the spelling/i);
        expect(texte).toMatch(/A name found by its sound alone is asked for confirmation/i);
    });
});

// --------------------------------------------------------------------------- //
// 🆕 26/09 — the second box and the budget of the draft (plan « le lexique »)
// --------------------------------------------------------------------------- //

describe("Les deux cases « Listen for it » et « The business offers it »", () => {
    it("montre les deux cases de chaque terme, chacune avec sa valeur", async () => {
        sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({
            data: {
                ...LEXIQUE_LONG,
                termes: LEXIQUE_LONG.termes.map((t, i) => ({ ...t, propose: i === 1 })),
            },
        });
        render(<SectionLexiqueMetier />);
        fireEvent.click(await screen.findByRole("button", { name: /open vocabulary/i }));
        await screen.findByLabelText("Term 1");
        // Edilkamin: listened for, not offered. Jøtul: offered, not listened for.
        expect(coche(1)).toBe("true");
        expect(offert(1)).toBe("false");
        expect(coche(2)).toBe("false");
        expect(offert(2)).toBe("true");
        expect(document.body.textContent).toMatch(/Listen for it/);
        expect(document.body.textContent).toMatch(/The business offers it/);
    });

    it("enregistre chaque case pour elle-même", async () => {
        await ouvrirLexique();
        // Untick « listen for it » (to shorten the list) : « offered » must stay.
        fireEvent.click(screen.getByRole("switch", { name: "Listen for it 1" }));
        fireEvent.click(screen.getByRole("button", { name: /save trade vocabulary/i }));
        await waitFor(() => expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).toHaveBeenCalled());
        const envoye = charge().termes[0];
        expect(envoye.a_ecouter).toBe(false);
        expect(envoye.propose).toBe(true);
    });

    it("les boutons « Tick / Untick the shown » ne touchent que « Listen for it »", async () => {
        await ouvrirLexique();
        fireEvent.click(screen.getByRole("button", { name: /^untick the 1 shown$/i }));
        expect(coche(1)).toBe("false");
        expect(offert(1)).toBe("true");
    });

    it("le résumé de la carte compte les termes proposés", async () => {
        render(<SectionLexiqueMetier />);
        await screen.findByRole("button", { name: /open vocabulary/i });
        expect(document.body.textContent).toMatch(/1 listened for · 1 offered/);
    });

    it("redemande le budget pour le brouillon quand une case « Listen for it » change", async () => {
        await ouvrirLexique();
        sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockClear();
        sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mockResolvedValue({
            data: { ...BUDGET, jetons: 0, envoyes: [] },
        });
        fireEvent.click(screen.getByRole("switch", { name: "Listen for it 1" }));
        await waitFor(() =>
            expect(sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost).toHaveBeenCalled(),
        );
        const demande = sdk.budgetLexiqueApiV1OrganizationsLexiqueBudgetPost.mock.calls.at(-1)?.[0];
        expect(demande?.body.termes[0].a_ecouter).toBe(false);
        await screen.findByText(/0 \/ 450 tokens \(Deepgram\)/);
    });
});

// The card really MOUNTED on the Platform Settings page, with its two boxes and its budget.
const { default: PageReglagesPlateforme } = await import("@/app/settings/page");

describe("[.mark] le lexique, sur la page des réglages de la plateforme", () => {
    beforeEach(() => {
        // Un test plus haut retire les globales simulées (export) : la page en a besoin.
        vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
    });

    it("porte les deux cases et le budget", async () => {
        render(<PageReglagesPlateforme />);
        await screen.findByText(/212 \/ 450 tokens \(Deepgram\)/);
        fireEvent.click(await screen.findByRole("button", { name: /open vocabulary/i }));
        await screen.findByLabelText("Term 1");
        expect(screen.getByRole("switch", { name: "Listen for it 1" })).toBeTruthy();
        expect(screen.getByRole("switch", { name: "The business offers it 1" })).toBeTruthy();
    });
});
