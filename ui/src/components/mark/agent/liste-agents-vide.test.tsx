/**
 * [.mark] K2b : la liste des agents quand rien ne s'affiche. Sans recherche ni filtre, c'est « Aucun agent » (l'état
 * premier de la convention des états vides), jamais « Aucun résultat pour «  » » ; avec une recherche, c'est le filtre.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FolderResponse } from "@/client/types.gen";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn(), replace: vi.fn(), back: vi.fn() }) }));
vi.mock("@/hooks/useOrganizationTimezone", () => ({ useOrganizationTimezone: () => "Europe/Paris" }));
vi.mock("@/lib/auth", () => {
    const auth = { user: { id: "u" }, loading: false };
    return { useAuth: () => auth };
});
vi.mock("@/client/sdk.gen", async (importOriginal) => {
    return (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        lireLesEtiquettesApiV1EtiquettesGet: () => Promise.resolve({ data: { etiquettes: [], par_agent: {} }, error: undefined }),
    });
});

const { ListeAgents } = await import("./ListeAgents");

const dossier: FolderResponse = { id: 1, name: "Dossier", created_at: "2026-10-16T08:00:00Z", parent_id: null };
const agent = { id: 1, name: "Principal", status: "active", created_at: "2026-10-16T08:00:00Z", total_runs: 0, folder_id: 1 };

afterEach(cleanup);

describe("liste des agents vide (K2b)", () => {
    it("sans recherche ni filtre : « No agent », pas « No result for »", () => {
        render(<ListeAgents actifs={[]} archives={[agent as never]} dossiers={[dossier]} liens={[]} dossierOuvertId={null} />);
        expect(screen.getByText("No agent")).toBeTruthy();
        expect(screen.queryByText(/No result for/)).toBeNull();
    });

    it("avec une recherche sans résultat : l'état du filtre, qui dit la recherche", () => {
        render(<ListeAgents actifs={[agent as never]} archives={[]} dossiers={[dossier]} liens={[]} dossierOuvertId={null} />);
        fireEvent.change(screen.getByPlaceholderText(/Search an agent/i), { target: { value: "zzz" } });
        expect(screen.getByText(/No result for/)).toBeTruthy();
    });
});
