/**
 * [.mark] Clôture SA-6 : le Labo (ou un client sans base rattachée) répond 409 « rattachez d'abord une base » à la lecture des objets.
 * C'est un état attendu, dit par l'état vide « Aucune base rattachée » : aucune notification d'échec par-dessus. Une vraie panne (500) garde la sienne.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ objets: vi.fn(), echec: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), { getObjetsApiV1OrganizationsObjetsGet: m.objets }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("../notifications/notifier", () => ({ notifier: { echec: m.echec, succes: vi.fn() } }));

import { useObjets } from "./SectionObjets";

beforeEach(() => vi.clearAllMocks());

describe("[.mark] lecture des objets sans base rattachée", () => {
    it("409 : l'état « Aucune base rattachée » (refus posé), aucune notification d'échec", async () => {
        m.objets.mockResolvedValue({ error: { detail: "Attach a client database first: the objects live there." }, response: { status: 409 } });
        const { result } = renderHook(() => useObjets());
        await waitFor(() => expect(result.current.refus).not.toBeNull());
        expect(m.echec).not.toHaveBeenCalled();
    });

    it("500 : la notification d'échec reste", async () => {
        m.objets.mockResolvedValue({ error: { detail: "boom" }, response: { status: 500 } });
        const { result } = renderHook(() => useObjets());
        await waitFor(() => expect(result.current.refus).not.toBeNull());
        expect(m.echec).toHaveBeenCalledTimes(1);
    });
});
