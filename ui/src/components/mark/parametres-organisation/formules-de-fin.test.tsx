/**
 * [.mark] Lot 2 d'orchestrateur-trois-cerveaux (B2): the « Recognised closing phrases » are a fiche of the
 * catalogue of sentences, read by the end-of-call safety net of the specialised agents.
 *
 *   - the default list on screen is, word for word, the default the server uses (read in its source: a
 *     list changed on one side only turns this red);
 *   - the variable is the one the engine reads in the call context;
 *   - « Add the recognised closing phrases » adds the fiche once and « Save » sends it like any sentence.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { charge_utile_phrases, ModalePhrases, PHRASE_FORMULES_DE_FIN } from "./ModalePhrases";

const m = vi.hoisted(() => ({ lire: vi.fn(), enregistrer: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getPhrasesApiV1OrganizationsPhrasesGet: m.lire,
    savePhrasesApiV1OrganizationsPhrasesPut: m.enregistrer,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const SOURCE = readFileSync(join(process.cwd(), "..", "api/services/groupe/filet_de_fin.py"), "utf8");

describe("[.mark] the recognised closing phrases of the catalogue", () => {
    it("the variable and the default list are the server's, word for word", () => {
        expect(SOURCE).toContain(`VARIABLE_FORMULES = "${PHRASE_FORMULES_DE_FIN.variable}"`);
        const defaut = /FORMULES_PAR_DEFAUT = \(([^)]*)\)/.exec(SOURCE)?.[1] ?? "";
        const formules = [...defaut.matchAll(/"([^"]+)"/g)].map((x) => x[1]);
        expect(formules.length).toBeGreaterThan(0);
        expect(PHRASE_FORMULES_DE_FIN.contenu.split("\n")).toEqual(formules);
        expect(PHRASE_FORMULES_DE_FIN.description.en && PHRASE_FORMULES_DE_FIN.description.fr).toBeTruthy();
        // The server refuses a description of more than 200 characters (``api/schemas/phrases.py``).
        expect(PHRASE_FORMULES_DE_FIN.description.en.length).toBeLessThanOrEqual(200);
        expect(PHRASE_FORMULES_DE_FIN.description.fr.length).toBeLessThanOrEqual(200);
    });

    it("adds the fiche once and saves it like any sentence", async () => {
        m.lire.mockResolvedValue({ data: { format: "phrases-mark", version: 1, phrases: [] } });
        m.enregistrer.mockResolvedValue({ data: {} });
        render(
            <FournisseurLangue>
                <ModalePhrases ouverte onFermer={vi.fn()} annonceOrganisation={{}} />
            </FournisseurLangue>,
        );
        fireEvent.click(await screen.findByTestId("ajouter-formules-de-fin"));
        // Once added, the button is gone: the fiche is edited in the list, like the others.
        expect(screen.queryByTestId("ajouter-formules-de-fin")).toBeNull();
        fireEvent.click(screen.getByTestId("enregistrer-phrases"));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalled());
        const envoye = m.enregistrer.mock.calls[0][0].body;
        expect(envoye).toEqual(charge_utile_phrases(envoye.phrases));
        expect(envoye.phrases).toEqual([
            {
                variable: "formules_de_fin",
                description: PHRASE_FORMULES_DE_FIN.description.fr,
                contenu: "au revoir\nbonne journée\nbonne soirée",
                niveau: "organisation",
            },
        ]);
    });

    it("keeps the list the organization wrote, and does not offer the default again", async () => {
        m.lire.mockResolvedValue({ data: { format: "phrases-mark", version: 1, phrases: [
            { variable: "formules_de_fin", description: "", contenu: "à bientôt\nciao", niveau: "organisation" },
        ] } });
        render(
            <FournisseurLangue>
                <ModalePhrases ouverte onFermer={vi.fn()} annonceOrganisation={{}} />
            </FournisseurLangue>,
        );
        await screen.findByTestId("liste-phrases");
        expect(screen.queryByTestId("ajouter-formules-de-fin")).toBeNull();
        expect(screen.getByDisplayValue(/à bientôt/)).toBeTruthy();
    });
});
