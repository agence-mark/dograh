/**
 * [.mark] Clôture, SA-9 (3 et 8) : l'écran des clés d'API.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | création refusée | un refus 403 à la création dit en clair qu'une clé sans rôle au Labo exige le droit de modifier les agents, dans les deux langues |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ creer: vi.fn(), echec: vi.fn(), succes: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    archiveApiKeyApiV1UserApiKeysApiKeyIdDelete: vi.fn(),
    createApiKeyApiV1UserApiKeysPost: m.creer,
    getApiKeysApiV1UserApiKeysGet: vi.fn(async () => ({ data: [] })),
    listerLesRolesApiV1EquipeMarkRolesGet: vi.fn(async () => ({ data: [] })),
    reactivateApiKeyApiV1UserApiKeysApiKeyIdReactivatePut: vi.fn(),
}));
vi.mock("@/components/mark/equipe/api-cloture", () => ({ regenererLaClePortail: vi.fn(), changerLeRoleDeLaCle: vi.fn(), suspendreLaCle: vi.fn(), changerLesInterrupteursMcp: vi.fn() }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false, getAccessToken: async () => "t" }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec, information: vi.fn(), reversible: vi.fn() } }));

import { SectionClesApi } from "./SectionClesApi";

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const dans = () => render(<FournisseurLangue><SectionClesApi /></FournisseurLangue>);

describe("[.mark] SA-9 : clés d'API", () => {
    it("création refusée (403) : la phrase dit le droit manquant, pas un simple « Réessayez »", async () => {
        m.creer.mockResolvedValue({ error: { detail: "x" }, response: { status: 403 } });
        dans();
        fireEvent.click(await screen.findByRole("button", { name: /Créer une clé/ }));
        fireEvent.change(await screen.findByLabelText("Nom de la clé"), { target: { value: "k" } });
        fireEvent.click(screen.getAllByRole("button", { name: "Créer une clé" }).at(-1)!);
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        const [phrase] = m.echec.mock.calls[0];
        expect(phrase.fr).toContain("modifier les agents");
        expect(phrase.en).toContain("edit agents");
    });
});
