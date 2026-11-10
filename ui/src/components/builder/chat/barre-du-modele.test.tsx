/** Clôture D1 (É50) : la barre de saisie du chat dit le modèle et « dépense sur plafond », et la pièce jointe dépose dans l'agent du chat. */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    cerveau: vi.fn(async () => ({ data: { modele: "Claude Opus 5.5", plafond_depense: 2 }, error: undefined })),
    depot: vi.fn(async (_o?: unknown) => ({ data: {}, error: undefined as unknown })),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { email: "e@x.fr" }, loading: false }) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/client", async (importOriginal) => ({
    ...(await importOriginal<object>()),
    lireLeCerveauApiV1BuilderCerveauGet: () => m.cerveau(),
    deposerUnFichierApiV1BuilderDepotWorkflowIdPost: (o: unknown) => m.depot(o),
}));

const { BarreDuModele, texteDepense } = await import("./barre-du-modele");
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("barre du modèle du chat", () => {
    it("écrit la dépense sur le plafond dans les deux langues", () => {
        expect(texteDepense(0.42, 2, "fr")).toBe("0,42 $ sur 2 $");
        expect(texteDepense(0.42, 2, "en")).toBe("$0.42 of $2");
        expect(texteDepense(1.5, 0, "fr")).toBe("1,50 $");
    });
    it("montre le modèle et la dépense lus du serveur", async () => {
        render(<BarreDuModele cout={0.42} workflowId={5} rafraichir={() => {}} desactive={false} />);
        await waitFor(() => expect(screen.getByText(/Opus 5\.5/)).toBeTruthy());
        expect(document.querySelector("[data-barre-modele]")?.textContent).toContain("$0.42 of $2");
    });
    it("la pièce jointe dépose le fichier dans l'agent du chat, et reste fermée sans agent", async () => {
        const rafraichir = vi.fn();
        const { rerender } = render(<BarreDuModele cout={0} workflowId={5} rafraichir={rafraichir} desactive={false} />);
        const entree = document.querySelector("[data-joindre-chat]") as HTMLInputElement;
        fireEvent.change(entree, { target: { files: [new File(["x"], "audit.pdf")] } });
        await waitFor(() => expect(m.depot).toHaveBeenCalledTimes(1));
        expect((m.depot.mock.calls[0][0] as { path: unknown }).path).toEqual({ workflow_id: 5 });
        await waitFor(() => expect(rafraichir).toHaveBeenCalled());
        rerender(<BarreDuModele cout={0} workflowId={null} rafraichir={rafraichir} desactive={false} />);
        expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    });
});
