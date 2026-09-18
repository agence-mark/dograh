/**
 * [.mark] The closed-business announcement, as seen on screen.
 *
 * The questions this file answers:
 *
 *     Can the two sentences, the forced state and its end date be REACHED and
 *     changed on the Platform Settings page, and does saving carry exactly what
 *     was typed? Does the preview show the sentence the way the server will
 *     build it, brackets and all? Is a refusal from the server shown rather
 *     than swallowed, and is saving kept asleep while the saved settings could
 *     not be read? And is the card really MOUNTED on the page?
 *
 * Why it exists
 * -------------
 * The two sentences were written in the code until 18/09/2026. .mark rule: a
 * setting we cannot see on screen is a setting we do not touch. And a card that
 * renders in its own test is not a card that is mounted: the last block renders
 * the PAGE itself (lesson of 14/09, 29 settings put in a dead file).
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { rendreAnnonce, SectionAnnonceOuverture } from "./SectionAnnonceOuverture";

const DEFAUTS = {
    format: "annonce-ouverture-mark" as const,
    version: 1 as const,
    annonce_fermeture: "Nous sommes fermés en ce moment[, nous rouvrons {reouverture}].",
    annonce_pause: "Nous sommes fermés pour le moment[, nous rouvrons {reouverture}].",
    etat_force: null,
    etat_force_jusqu_a: null,
};

const mocks = vi.hoisted(() => ({
    getAnnonce: vi.fn(),
    saveAnnonce: vi.fn(),
    getPreferences: vi.fn().mockResolvedValue({ data: { timezone: "UTC" } }),
    savePreferences: vi.fn().mockResolvedValue({ data: {} }),
    communes: vi.fn().mockResolvedValue({ data: [] }),
    getLexique: vi
        .fn()
        .mockResolvedValue({ data: { format: "lexique-mark", version: 1, termes: [] } }),
    toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/client/sdk.gen", () => ({
    getAnnonceOuvertureApiV1OrganizationsAnnonceOuvertureGet: mocks.getAnnonce,
    saveAnnonceOuvertureApiV1OrganizationsAnnonceOuverturePut: mocks.saveAnnonce,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: mocks.communes,
    getPreferencesApiV1OrganizationsPreferencesGet: mocks.getPreferences,
    savePreferencesApiV1OrganizationsPreferencesPut: mocks.savePreferences,
    getLexiqueApiV1OrganizationsLexiqueGet: mocks.getLexique,
    saveLexiqueApiV1OrganizationsLexiquePut: vi.fn(),
    importLexiqueApiV1OrganizationsLexiqueImportPost: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: mocks.toast }));
vi.mock("@/context/UnsavedChangesContext", () => ({ useUnsavedChanges: () => undefined }));
vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ organizationPreferences: null, userConfig: null }),
}));
vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));
vi.mock("@/lib/auth", () => ({
    useAuth: () => ({ user: { id: 1 }, loading: false, redirectToLogin: vi.fn() }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

beforeEach(() => {
    vi.clearAllMocks();
    mocks.getAnnonce.mockResolvedValue({ data: DEFAUTS });
    mocks.saveAnnonce.mockImplementation(async ({ body }: { body: unknown }) => ({ data: body }));
});

const champ = (id: string) => document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement;

async function afficher() {
    render(<SectionAnnonceOuverture />);
    await screen.findByText("When the business is closed");
}

// --------------------------------------------------------------------------- //
// 1. The rendering rule, the same one the server applies
// --------------------------------------------------------------------------- //

describe("[.mark] the preview follows the server's rule", () => {
    // ⚠️ The same cases as ``test_le_rendu_dune_phrase`` on the server, minus its
    // trailing space: that space is for the greeting, not for a preview.
    it.each([
        ["Fermé[, retour {reouverture}].", "demain à 10 heures", "Fermé, retour demain à 10 heures."],
        ["Fermé[, retour {reouverture}].", "", "Fermé."],
        ["Fermé[ jusqu'à {reouverture}], merci.", "", "Fermé, merci."],
        ["Nous sommes fermés.", "demain à 10 heures", "Nous sommes fermés."],
        // An unclosed « [ » is optional to the end, exactly like on the server.
        ["Fermé[, retour {reouverture}.", "", "Fermé"],
        ["", "demain à 10 heures", ""],
        ["   ", "", ""],
    ])("%s + %s", (modele, reouverture, attendu) => {
        expect(rendreAnnonce(modele, reouverture)).toBe(attendu);
    });

    it("never leaves a bracket in what would be said", () => {
        for (const modele of ["a[b", "a]b", "a[b]c", "[x]"]) {
            expect(rendreAnnonce(modele, "")).not.toMatch(/[[\]]/);
            expect(rendreAnnonce(modele, "demain")).not.toMatch(/[[\]]/);
        }
    });
});

// --------------------------------------------------------------------------- //
// 2. The card: reach the four settings, change them, save them
// --------------------------------------------------------------------------- //

describe("[.mark] the announcement settings card", () => {
    it("shows what is saved, in the two sentence fields", async () => {
        await afficher();
        expect(champ("annonce_fermeture").value).toBe(DEFAUTS.annonce_fermeture);
        expect(champ("annonce_pause").value).toBe(DEFAUTS.annonce_pause);
    });

    it("previews both sentences, with and without a reopening", async () => {
        await afficher();
        expect(document.body.textContent).toContain(
            "Nous sommes fermés en ce moment, nous rouvrons demain à 10 heures",
        );
        expect(document.body.textContent).toContain("Nous sommes fermés en ce moment.");
    });

    it("updates the preview as the sentence is typed", async () => {
        await afficher();
        fireEvent.change(champ("annonce_fermeture"), {
            target: { value: "Le magasin est fermé[, retour {reouverture}]." },
        });
        await waitFor(() =>
            expect(document.body.textContent).toContain("Le magasin est fermé, retour demain à 10 heures"),
        );
        expect(document.body.textContent).toContain("Le magasin est fermé.");
    });

    it("says so when a sentence is emptied, rather than showing nothing", async () => {
        await afficher();
        fireEvent.change(champ("annonce_fermeture"), { target: { value: "" } });
        await waitFor(() => expect(document.body.textContent).toContain("nothing is announced"));
    });

    it("sends exactly what was typed", async () => {
        await afficher();
        fireEvent.change(champ("annonce_fermeture"), { target: { value: "Fermé aujourd'hui." } });
        fireEvent.click(screen.getByRole("button", { name: /save announcement settings/i }));
        await waitFor(() => expect(mocks.saveAnnonce).toHaveBeenCalledTimes(1));
        expect(mocks.saveAnnonce.mock.calls[0][0].body).toMatchObject({
            annonce_fermeture: "Fermé aujourd'hui.",
            annonce_pause: DEFAUTS.annonce_pause,
            etat_force: null,
            etat_force_jusqu_a: null,
        });
    });

    it("hides the end date while the state is computed, and shows it once forced", async () => {
        await afficher();
        expect(champ("etat_force_jusqu_a")).toBeNull();
        fireEvent.change(champ("etat_force"), { target: { value: "FERME" } });
        await waitFor(() => expect(champ("etat_force_jusqu_a")).not.toBeNull());
    });

    it("warns that a forced state closes every agent, and how to close one site", async () => {
        await afficher();
        fireEvent.change(champ("etat_force"), { target: { value: "FERME" } });
        await waitFor(() =>
            expect(document.body.textContent).toContain("EVERY agent of this organization"),
        );
        expect(document.body.textContent).toContain("24/12/2026 : fermé");
    });

    it("sends the forced state with its end date", async () => {
        await afficher();
        fireEvent.change(champ("etat_force"), { target: { value: "FERME" } });
        await waitFor(() => expect(champ("etat_force_jusqu_a")).not.toBeNull());
        fireEvent.change(champ("etat_force_jusqu_a"), { target: { value: "2026-12-26T09:00" } });
        fireEvent.click(screen.getByRole("button", { name: /save announcement settings/i }));
        await waitFor(() => expect(mocks.saveAnnonce).toHaveBeenCalledTimes(1));
        expect(mocks.saveAnnonce.mock.calls[0][0].body).toMatchObject({
            etat_force: "FERME",
            etat_force_jusqu_a: "2026-12-26T09:00",
        });
    });

    it("drops the end date when going back to « computed »", async () => {
        // ⛔ A date with no forced state is refused by the server; leaving it
        // behind would make « back to computed » fail for a reason nobody sees.
        mocks.getAnnonce.mockResolvedValue({
            data: { ...DEFAUTS, etat_force: "FERME", etat_force_jusqu_a: "2026-12-26T09:00:00" },
        });
        await afficher();
        expect(champ("etat_force_jusqu_a").value).toBe("2026-12-26T09:00");
        fireEvent.change(champ("etat_force"), { target: { value: "" } });
        await waitFor(() => expect(champ("etat_force_jusqu_a")).toBeNull());
        fireEvent.click(screen.getByRole("button", { name: /save announcement settings/i }));
        await waitFor(() => expect(mocks.saveAnnonce).toHaveBeenCalledTimes(1));
        expect(mocks.saveAnnonce.mock.calls[0][0].body).toMatchObject({
            etat_force: null,
            etat_force_jusqu_a: null,
        });
    });

    it("shows a refusal from the server instead of swallowing it", async () => {
        mocks.saveAnnonce.mockResolvedValue({
            error: { detail: "Un « [ » qui ne se referme jamais." },
            response: { status: 422 },
        });
        await afficher();
        fireEvent.click(screen.getByRole("button", { name: /save announcement settings/i }));
        const alerte = await screen.findByRole("alert");
        expect(alerte.textContent).toContain("ne se referme jamais");
    });

    it("keeps Save asleep when the saved settings could not be read", async () => {
        // ⛔ Saving REPLACES them whole: never overwrite what was never read.
        mocks.getAnnonce.mockResolvedValue({ error: { detail: "unreadable" } });
        render(<SectionAnnonceOuverture />);
        const bouton = (await screen.findByRole("button", {
            name: /save announcement settings/i,
        })) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        expect(document.body.textContent).toContain("Nothing was changed");
    });
});

// --------------------------------------------------------------------------- //
// 3. The card is really MOUNTED on the Platform Settings page
// --------------------------------------------------------------------------- //

const { default: PageReglagesPlateforme } = await import("@/app/settings/page");

describe("[.mark] the announcement settings, on the Platform Settings page", () => {
    it("is on the page, and its four settings can be reached there", async () => {
        render(<PageReglagesPlateforme />);
        await screen.findByText("Closed-business announcement");
        // The two sentences and the state selector are on the PAGE, not only in
        // the card's own test.
        await waitFor(() => expect(champ("annonce_fermeture")).not.toBeNull());
        expect(champ("annonce_pause")).not.toBeNull();
        expect(champ("etat_force")).not.toBeNull();
        // The fourth one appears once a state is forced, on the page too.
        fireEvent.change(champ("etat_force"), { target: { value: "FERME" } });
        await waitFor(() => expect(champ("etat_force_jusqu_a")).not.toBeNull());
    });

    it("the agent's Opening Hours card points at it", async () => {
        // Without this line, nobody would know where the sentences went.
        const { SectionHorairesOuverture } = await import("./SectionHorairesOuverture");
        render(
            <SectionHorairesOuverture
                workflowConfigurations={{ horaires_ouverture: null } as never}
                workflowName="agent"
                onSave={vi.fn()}
            />,
        );
        const lien = screen.getByRole("link", {
            name: /Platform Settings.*Closed-business announcement/i,
        });
        expect(lien.getAttribute("href")).toBe("/settings");
    });
});
