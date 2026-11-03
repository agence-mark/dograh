/**
 * [.mark] K5 : l'écran « Connaissances », rendu.
 *
 *   - le tableau des documents (lecture, état), l'état vide, la recherche ;
 *   - « Déposer un document » : le type et la taille sont refusés sous le champ avant tout envoi ; un fichier admis part avec
 *     le mode de lecture choisi ; l'échec dit sa phrase sans le texte brut du serveur ;
 *   - la fenêtre d'un document : « Supprimer » ne part qu'après les 5 secondes d'« Annuler » (le document disparaît tout de suite).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { PageConnaissances } from "./PageConnaissances";

const DOC = (extra: Record<string, unknown> = {}) => ({
    id: 1,
    document_uuid: "d1",
    filename: "Questions.md",
    file_size_bytes: 6144,
    file_hash: "h",
    mime_type: "text/markdown",
    processing_status: "completed",
    total_chunks: 0,
    retrieval_mode: "full_document",
    custom_metadata: {},
    docling_metadata: {},
    created_at: "2026-11-01T10:00:00Z",
    has_live_content: true,
    ...extra,
});

const m = vi.hoisted(() => ({ liste: vi.fn(), adresse: vi.fn(), analyse: vi.fn(), supprimer: vi.fn(), annulable: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listDocumentsApiV1KnowledgeBaseDocumentsGet: (...a: unknown[]) => m.liste(...a),
        getUploadUrlApiV1KnowledgeBaseUploadUrlPost: (...a: unknown[]) => m.adresse(...a),
        processDocumentApiV1KnowledgeBaseProcessDocumentPost: (...a: unknown[]) => m.analyse(...a),
        deleteDocumentApiV1KnowledgeBaseDocumentsDocumentUuidDelete: (...a: unknown[]) => m.supprimer(...a),
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/mark/notifications", () => ({
    notifier: { succes: vi.fn(), echec: vi.fn(), annulable: (...a: unknown[]) => m.annulable(...a) },
}));
vi.mock("@/app/files/ExternalProcessingNotice", () => ({ default: () => null }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const monter = () =>
    render(
        <FournisseurLangue>
            <PageConnaissances />
        </FournisseurLangue>,
    );

describe("[.mark] Connaissances", () => {
    it("liste les documents avec leur lecture et leur état, et dit quand il n'y en a aucun", async () => {
        m.liste.mockResolvedValue({ data: { documents: [DOC(), DOC({ document_uuid: "d2", filename: "Catalogue.pdf", retrieval_mode: "chunked", processing_status: "processing", has_live_content: false })] } });
        monter();
        const ligne = (await screen.findByText("Questions.md")).closest("tr")!;
        expect(ligne.textContent).toContain("Document entier");
        expect(ligne.textContent).toContain("Prêt");
        expect(ligne.textContent).toContain("6 Ko");
        const autre = screen.getByText("Catalogue.pdf").closest("tr")!;
        expect(autre.textContent).toContain("Recherche par extraits");
        expect(autre.textContent).toContain("Lecture en cours");
        cleanup();
        m.liste.mockResolvedValue({ data: { documents: [] } });
        monter();
        expect(await screen.findByText("Aucun document")).toBeTruthy();
    });

    it("refuse un type ou une taille sous le champ, sans rien envoyer", async () => {
        m.liste.mockResolvedValue({ data: { documents: [] } });
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Déposer un document/ }));
        const fenetre = await screen.findByTestId("fenetre-depot");
        const entree = fenetre.querySelector("[data-depot-fichier]") as HTMLInputElement;
        fireEvent.change(entree, { target: { files: [new File(["x"], "x.exe")] } });
        expect((await within(fenetre).findByRole("alert")).textContent).toContain("pas pris en charge");
        const gros = new File(["x"], "gros.pdf");
        Object.defineProperty(gros, "size", { value: 6 * 1024 * 1024 });
        fireEvent.change(entree, { target: { files: [gros] } });
        expect((await within(fenetre).findByRole("alert")).textContent).toContain("5 Mo");
        expect(m.adresse).not.toHaveBeenCalled();
    });

    it("dépose un fichier admis avec le mode de lecture choisi, puis relit la liste", async () => {
        m.liste.mockResolvedValue({ data: { documents: [] } });
        m.adresse.mockResolvedValue({ data: { upload_url: "https://stockage.test/u", document_uuid: "d9", s3_key: "k9" } });
        m.analyse.mockResolvedValue({ data: {} });
        vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true })));
        monter();
        fireEvent.click(await screen.findByRole("button", { name: /Déposer un document/ }));
        const fenetre = await screen.findByTestId("fenetre-depot");
        fireEvent.change(fenetre.querySelector("[data-depot-fichier]") as HTMLInputElement, { target: { files: [new File(["# Règle"], "regle.md", { type: "text/markdown" })] } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Recherche par extraits" }));
        fireEvent.click(screen.getByRole("button", { name: "Déposer" }));
        await waitFor(() => expect(m.analyse).toHaveBeenCalledOnce());
        expect(m.analyse.mock.calls[0][0].body).toEqual({ document_uuid: "d9", s3_key: "k9", retrieval_mode: "chunked" });
        await waitFor(() => expect(m.liste.mock.calls.length).toBeGreaterThan(1));
        vi.unstubAllGlobals();
    });

    it("supprime un document par « Annuler » différé : il disparaît de la liste, le serveur n'est appelé qu'ensuite", async () => {
        m.liste.mockResolvedValue({ data: { documents: [DOC()] } });
        monter();
        fireEvent.click((await screen.findByText("Questions.md")).closest("tr")!);
        fireEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
        expect(m.supprimer).not.toHaveBeenCalled();
        expect(m.annulable).toHaveBeenCalledOnce();
        await waitFor(() => expect(screen.queryByText("Questions.md")).toBeNull());
        m.supprimer.mockResolvedValue({ data: {} });
        await m.annulable.mock.calls[0][1].executer();
        expect(m.supprimer).toHaveBeenCalledWith({ path: { document_uuid: "d1" } });
    });
});
