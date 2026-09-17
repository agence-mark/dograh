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
        },
    ],
};

beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.error.mockClear();
    sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockReset();
    sdk.saveLexiqueApiV1OrganizationsLexiquePut.mockReset();
    sdk.importLexiqueApiV1OrganizationsLexiqueImportPost.mockReset();
    sdk.getLexiqueApiV1OrganizationsLexiqueGet.mockResolvedValue({ data: LEXIQUE });
    sdk.saveLexiqueApiV1OrganizationsLexiquePut.mockImplementation(
        async ({ body }: { body: unknown }) => ({ data: body }),
    );
});

async function ouvrirLexique() {
    render(<SectionLexiqueMetier />);
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

    it("ajoute un terme, coché par défaut, et l'emporte tel quel dans l'enregistrement", async () => {
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
        expect(
            (screen.getByRole("button", { name: /save trade vocabulary/i }) as HTMLButtonElement)
                .disabled,
        ).toBe(true);
        expect(sdk.saveLexiqueApiV1OrganizationsLexiquePut).not.toHaveBeenCalled();
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
        await ouvrirLexique();
        fireEvent.click(screen.getByRole("button", { name: /export/i }));
        expect(blobs.length).toBe(1);
        const contenu = JSON.parse(await blobs[0].text());
        expect(contenu.format).toBe("lexique-mark");
        expect(contenu.termes[0].terme).toBe("Edilkamin");
        vi.unstubAllGlobals();
    });

    it("compte les termes écoutés et rappelle le budget", async () => {
        await ouvrirLexique();
        expect(document.body.textContent).toMatch(/1 terms listened for/);
        expect(document.body.textContent).toMatch(/120 terms \/ 1600 characters in total/);
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
