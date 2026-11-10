/**
 * [.mark] Correctifs d'écran, point 15 : deux lectures des espaces qui se croisent.
 *
 * La question de ce fichier : une lecture ANCIENNE qui répond après une lecture plus récente efface-t-elle un logo posé ?
 * Elle ne doit pas : seul le rang le plus récent met à jour les logos.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ lire: vi.fn(), logo: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    listerLesEspacesApiV1EspacesGet: () => m.lire(),
    lireLeLogoApiV1EspacesOrganizationIdLogoGet: () => m.logo(),
    reglerUnEspaceApiV1EspacesOrganizationIdPut: vi.fn(),
    remplacerLeLogoApiV1EspacesOrganizationIdLogoPut: vi.fn(),
    retirerLeLogoApiV1EspacesOrganizationIdLogoDelete: vi.fn(),
}));

import { listerEspaces } from "./espaces";
import { oublierLesLogos } from "./logos-espaces";

const espace = (logo_version: string | null) => ({
    espaces: [{ id: 2, nom: "Client", provider_id: "c", espace: "client", selectionne: true, logo_version }],
});

beforeEach(() => {
    oublierLesLogos();
    m.lire.mockReset();
    m.logo.mockReset().mockResolvedValue({ data: new Blob(["x"]), error: undefined });
    URL.createObjectURL = vi.fn(() => "blob:x");
    URL.revokeObjectURL = vi.fn();
});

describe("lectures des espaces qui se croisent", () => {
    it("une lecture ancienne, arrivée en dernier, n'efface pas le logo de la lecture récente", async () => {
        let finAncienne!: (v: unknown) => void;
        m.lire.mockReturnValueOnce(new Promise((r) => (finAncienne = r))); // lancée d'abord, répond en dernier
        m.lire.mockResolvedValueOnce({ data: espace("v2"), error: undefined }); // lancée ensuite, répond tout de suite
        const ancienne = listerEspaces();
        await listerEspaces();
        expect(m.logo).toHaveBeenCalledTimes(1); // le logo de la version v2 est lu
        finAncienne({ data: espace(null), error: undefined });
        await ancienne;
        const { useLogoEspace } = await import("./logos-espaces");
        const { renderHook } = await import("@testing-library/react");
        expect(renderHook(() => useLogoEspace(2)).result.current).toBe("blob:x");
    });
});
