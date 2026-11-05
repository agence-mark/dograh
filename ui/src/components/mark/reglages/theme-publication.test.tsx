/**
 * [.mark] Partie 3, sous-lot 3 (SE-12 / D-1) : le thème « Publication » des Réglages de l'organisation.
 *
 *   - les défauts viennent du serveur : déploiement progressif ÉTEINT, tests obligatoires et bilan du prompt qui bloquent ;
 *   - « Enregistrer » envoie exactement ce qui est à l'écran (l'interrupteur et les cinq positions) ;
 *   - un enregistrement refusé le dit et garde le brouillon (jamais le texte brut du serveur) ;
 *   - sans modification, « Enregistrer » ne part pas.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ThemePublication } from "./ThemePublication";

const DEFAUTS = {
    controles: { tests_obligatoires: "bloque", bilan_du_prompt: "bloque", liste_vocale: "eteint", attaques: "eteint", garde_fous: "eteint" },
    deploiement: { actif: false },
};

const m = vi.hoisted(() => ({ lire: vi.fn(), ecrire: vi.fn(), signaler: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        defautsDeLOrganisationApiV1BuilderPublicationOrganisationGet: (o: unknown) => m.lire(o),
        reglerLesDefautsDeLOrganisationApiV1BuilderPublicationOrganisationPut: (o: unknown) => m.ecrire(o),
    }),
);
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

beforeEach(() => {
    m.lire.mockReset().mockResolvedValue({ data: structuredClone(DEFAUTS) });
    m.ecrire.mockReset().mockImplementation(async ({ body }: { body: unknown }) => ({ data: body }));
});
afterEach(cleanup);

const rendre = () =>
    render(
        <FournisseurLangue>
            <ThemePublication ouvert onBasculer={() => {}} ouvrir={() => {}} signaler={m.signaler} plat />
        </FournisseurLangue>,
    );

describe("le thème « Publication »", () => {
    it("montre les défauts du serveur : déploiement éteint, deux contrôles qui bloquent", async () => {
        const { container } = rendre();
        await screen.findByRole("switch");
        expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("false");
        expect(container.querySelectorAll("[data-reglage^='publication.controles.']").length).toBe(11);
        const ligne = container.querySelector("[data-reglage='publication.controles.tests_obligatoires']") as HTMLElement;
        expect(ligne.querySelector("button[aria-pressed='true']")?.textContent).toBe("Bloque");
        const eteinte = container.querySelector("[data-reglage='publication.controles.attaques']") as HTMLElement;
        expect(eteinte.querySelector("button[aria-pressed='true']")?.textContent).toBe("Éteint");
    });

    it("enregistre exactement ce qui est à l'écran", async () => {
        const { container } = rendre();
        await screen.findByRole("switch");
        const enregistrer = () => screen.getByRole("button", { name: /Enregistrer/ }) as HTMLButtonElement;
        expect(enregistrer().disabled).toBe(true);
        fireEvent.click(screen.getByRole("switch"));
        const attaques = container.querySelector("[data-reglage='publication.controles.attaques']") as HTMLElement;
        fireEvent.click(Array.from(attaques.querySelectorAll("button")).find((b) => b.textContent === "Prévient")!);
        expect(enregistrer().disabled).toBe(false);
        fireEvent.click(enregistrer());
        await waitFor(() => expect(m.ecrire).toHaveBeenCalledTimes(1));
        expect(m.ecrire.mock.calls[0][0].body).toEqual({
            controles: { ...DEFAUTS.controles, attaques: "previent" },
            deploiement: { actif: true },
        });
        await waitFor(() => expect(enregistrer().disabled).toBe(true));
    });

    it("un enregistrement refusé garde le brouillon et ne montre jamais le texte du serveur", async () => {
        m.ecrire.mockResolvedValue({ error: { detail: "boom-serveur" } });
        rendre();
        await screen.findByRole("switch");
        fireEvent.click(screen.getByRole("switch"));
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer/ }));
        await waitFor(() => expect(m.ecrire).toHaveBeenCalled());
        expect(screen.getByRole("switch").getAttribute("aria-checked")).toBe("true");
        expect(document.body.textContent).not.toContain("boom-serveur");
    });
});
