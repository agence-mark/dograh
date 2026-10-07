/**
 * [.mark] The theme « Caller verification » (chantier l-agent-collegue, L6), rendered.
 *
 *   - every key of the published settings is ON SCREEN (convention § 6, inventory);
 *   - the fields of the question show only with the question on (E8: the server refuses the
 *     question without a field, the screen names it and blocks the save, E7);
 *   - a level higher than the factors switched on is said (« never read »);
 *   - « Save » sends exactly what is on screen (charge utile);
 *   - texts in English and in French (T2).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { CHAMPS_CONTROLE, charge_utile_verification, FACTEURS, ThemeVerification, TYPES_LISIBLES } from "./ThemeVerification";

const LU = {
    numero: true,
    question: true,
    code_sms: false,
    champs_controle: ["nom", "code_postal"],
    lisibles: {
        demandes: { facteurs_requis: 2, champs: ["reference", "type", "statut", "creee_le"] },
        rendez_vous: { facteurs_requis: 2, champs: ["debut", "libelle", "statut"] },
    },
    logiciel: null,
};

const m = vi.hoisted(() => ({ lire: vi.fn(), enregistrer: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getVerificationAppelantApiV1OrganizationsVerificationAppelantGet: m.lire,
    putVerificationAppelantApiV1OrganizationsVerificationAppelantPut: m.enregistrer,
    getLogicielsDossierApiV1OrganizationsVerificationAppelantLogicielsGet: () => Promise.resolve({ data: [] }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const rendre = () =>
    render(
        <FournisseurLangue>
            <ThemeVerification ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={vi.fn()} />
        </FournisseurLangue>,
    );

const clesDuType = (nom: string): string[] => {
    const genere = readFileSync(join(process.cwd(), "src/client/types.gen.ts"), "utf8");
    const debut = `export type ${nom} = {`;
    const i = genere.indexOf(debut);
    const bloc = genere.slice(i + debut.length, genere.indexOf("\n};", i));
    return [...bloc.matchAll(/^ {4}([a-z_0-9]+)\??:/gm)].map((x) => x[1]);
};

describe("[.mark] l-agent-collegue L6: the theme « Caller verification »", () => {
    it("draws every key of the published settings", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        const { container } = rendre();
        await screen.findByTestId("verif-champs-controle");
        const cles = clesDuType("ReglagesVerification");
        expect(cles).toEqual(["numero", "question", "code_sms", "champs_controle", "lisibles", "logiciel"]);
        for (const cle of cles) {
            const ici = cle === "lisibles" ? '[data-reglage^="lisibles."]' : `[data-reglage="${cle}"]`;
            expect(container.querySelector(ici), cle).not.toBeNull();
        }
        expect(container.querySelectorAll('[data-reglage^="lisibles."]').length).toBe(2);
    });

    it("saves exactly what is on screen", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(LU) });
        m.enregistrer.mockImplementation(async ({ body }) => ({ data: body }));
        rendre();
        await screen.findByTestId("verif-champs-controle");
        fireEvent.click(screen.getByLabelText("Code postal"));
        fireEvent.click(screen.getByTestId("verif-lisible-demandes-resume"));
        fireEvent.change(document.getElementById("verif-niveau-rendez_vous") as HTMLSelectElement, { target: { value: "1" } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer/ }));
        await waitFor(() =>
            expect(m.enregistrer).toHaveBeenCalledWith({
                body: charge_utile_verification({
                    ...LU,
                    champs_controle: ["nom"],
                    lisibles: {
                        demandes: { facteurs_requis: 2, champs: ["reference", "type", "statut", "creee_le", "resume"] },
                        rendez_vous: { facteurs_requis: 1, champs: ["debut", "libelle", "statut"] },
                    },
                }),
            }),
        );
    });

    it("the question without a field is named and blocks the save; off, its fields go", async () => {
        m.lire.mockResolvedValue({ data: { ...structuredClone(LU), champs_controle: ["nom"] } });
        const { container } = rendre();
        await screen.findByTestId("verif-champs-controle");
        fireEvent.click(screen.getByLabelText("Nom"));
        await waitFor(() => expect(container.textContent).toMatch(/choisissez-en au moins un/));
        expect((screen.getByRole("button", { name: /Enregistrer/ }) as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(document.getElementById("verif-question") as HTMLElement);
        await waitFor(() => expect(screen.queryByTestId("verif-champs-controle")).toBeNull());
    });

    it("a level higher than the factors switched on is said", async () => {
        m.lire.mockResolvedValue({ data: { ...structuredClone(LU), numero: false } });
        rendre();
        await screen.findByTestId("verif-champs-controle");
        expect(screen.getByTestId("verif-inaccessible-demandes").textContent).toMatch(/jamais lu/);
    });

    it("every text has its two languages", () => {
        for (const x of [...FACTEURS.flatMap((f) => [f.libelle, f.aide]), ...CHAMPS_CONTROLE.map((c) => c.libelle),
            ...TYPES_LISIBLES.flatMap((t) => [t.libelle, ...t.champs.map((c) => c.libelle)])])
            expect(x.en && x.fr, JSON.stringify(x)).toBeTruthy();
    });
});
