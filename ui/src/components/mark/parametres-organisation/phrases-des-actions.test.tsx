/**
 * [.mark] R-4 (chantier l-agent-collegue, decision of Evan 07/10): the sentences the code says for
 * the team and the actions are fiches of the catalogue, with their default text.
 *
 *   - each default on screen is, word for word, the default the server says (read in its source:
 *     a text changed on one side only turns this red);
 *   - « Add the sentences of the team and the actions » adds the missing ones, described in the
 *     language of the screen, and « Save » sends them as any sentence of the catalogue.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { charge_utile_phrases, ModalePhrases, PHRASES_DES_ACTIONS } from "./ModalePhrases";

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

const SOURCES = ["services/equipe/diriger.py", "services/planificateur/action.py", "services/verification/action.py"];

describe("[.mark] l-agent-collegue R-4: the sentences of the team and the actions in the catalogue", () => {
    it("each default is the server's, word for word", () => {
        const serveur = SOURCES.map((f) => readFileSync(join(process.cwd(), "..", "api", f), "utf8")).join("\n").replace(/"\s*\n\s*"/g, "");
        expect(PHRASES_DES_ACTIONS.map((p) => p.variable)).toEqual([
            "phrase_transfert_personne", "phrase_transmission_personne", "phrase_planificateur_rappel", "phrase_verification_rappel",
        ]);
        for (const p of PHRASES_DES_ACTIONS) {
            expect(serveur, p.variable).toContain(`"${p.variable}"`);
            expect(serveur, p.variable).toContain(p.contenu);
            expect(p.description.en && p.description.fr).toBeTruthy();
        }
    });

    it("adds the missing ones and saves them like any sentence", async () => {
        m.lire.mockResolvedValue({ data: { format: "phrases-mark", version: 1, phrases: [
            { variable: "phrase_transfert_personne", description: "", contenu: "Un instant, je vous passe {{prenom}}.", niveau: "organisation" },
        ] } });
        m.enregistrer.mockResolvedValue({ data: {} });
        render(
            <FournisseurLangue>
                <ModalePhrases ouverte onFermer={vi.fn()} annonceOrganisation={{}} />
            </FournisseurLangue>,
        );
        fireEvent.click(await screen.findByTestId("ajouter-phrases-actions"));
        expect(screen.queryByTestId("ajouter-phrases-actions")).toBeNull();
        fireEvent.click(screen.getByTestId("enregistrer-phrases"));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalled());
        const envoye = m.enregistrer.mock.calls[0][0].body;
        expect(envoye).toEqual(charge_utile_phrases(envoye.phrases));
        // The one the organization already wrote is kept as it is; the three others are added.
        expect(envoye.phrases.map((p: { variable: string }) => p.variable)).toEqual([
            "phrase_transfert_personne", "phrase_transmission_personne", "phrase_planificateur_rappel", "phrase_verification_rappel",
        ]);
        expect(envoye.phrases[0].contenu).toBe("Un instant, je vous passe {{prenom}}.");
        expect(envoye.phrases[1]).toEqual({
            variable: "phrase_transmission_personne",
            description: PHRASES_DES_ACTIONS[1].description.fr,
            contenu: "Je transmets votre demande à {{prenom}}, qui reviendra vers vous.",
            niveau: "organisation",
        });
    });
});
