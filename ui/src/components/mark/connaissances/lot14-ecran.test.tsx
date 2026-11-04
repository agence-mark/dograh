/**
 * [.mark] Partie 3, lot 14 (SE-21, K-1, K-2) : « Connaissances ».
 *
 *   - K-2 : la fenêtre d'un document dit combien d'agents le lisent (lu sur le serveur, jamais inventé) et montre le début de son texte ;
 *     une lecture en échec le dit au lieu d'un chiffre ;
 *   - K-1 : l'éditeur d'un document (fichier d'amont) est en français et en anglais.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DocumentEditor from "@/app/files/DocumentEditor";

import { FournisseurLangue } from "../langue/langue";
import { PageConnaissances } from "./PageConnaissances";

const DOC = {
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
};

const m = vi.hoisted(() => ({ liste: vi.fn(), usage: vi.fn(), contenu: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listDocumentsApiV1KnowledgeBaseDocumentsGet: (...a: unknown[]) => m.liste(...a),
        utilisationDUnDocumentApiV1KnowledgeBaseDocumentsDocumentUuidUtilisationGet: (...a: unknown[]) => m.usage(...a),
        getDocumentContentApiV1KnowledgeBaseDocumentsDocumentUuidContentGet: (...a: unknown[]) => m.contenu(...a),
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: vi.fn(), echec: vi.fn(), annulable: vi.fn(), information: vi.fn() } }));
vi.mock("@/app/files/ExternalProcessingNotice", () => ({ default: () => null }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const ouvrirLeDocument = async () => {
    render(
        <FournisseurLangue>
            <PageConnaissances />
        </FournisseurLangue>,
    );
    fireEvent.click((await screen.findByText("Questions.md")).closest("tr")!);
    return screen.findByTestId("fenetre-document");
};

describe("[.mark] lot 14 : la fenêtre d'un document (K-2)", () => {
    it("dit combien d'agents lisent le document (les noms au survol) et montre le début de son texte", async () => {
        m.liste.mockResolvedValue({ data: { documents: [DOC] } });
        m.usage.mockResolvedValue({ data: { nombre: 2, agents: [{ workflow_id: 1, nom: "Alice" }, { workflow_id: 2, nom: "Zoé" }] } });
        m.contenu.mockResolvedValue({ data: { content: "Bonjour, voici le texte du document.", file_hash: "h" } });
        const fenetre = await ouvrirLeDocument();
        const lu = await screen.findByTestId("agents-du-document");
        expect(lu.textContent).toBe("2 agents");
        expect(lu.getAttribute("title")).toBe("Alice, Zoé");
        expect((await screen.findByTestId("texte-du-document")).textContent).toBe("Bonjour, voici le texte du document.");
        expect(fenetre.textContent).toContain("Lu par");
        expect(m.usage).toHaveBeenCalledWith({ path: { document_uuid: "d1" } });
    });

    it("« aucun agent » quand aucun ne le lit ; « indisponible » quand la lecture échoue, jamais un chiffre inventé", async () => {
        m.liste.mockResolvedValue({ data: { documents: [DOC] } });
        m.usage.mockResolvedValue({ data: { nombre: 0, agents: [] } });
        m.contenu.mockResolvedValue({ error: { detail: "x" } });
        const fenetre = await ouvrirLeDocument();
        await waitFor(() => expect(fenetre.textContent).toContain("aucun agent"));
        expect(fenetre.textContent).toContain("Le texte n'a pas pu être lu.");
        cleanup();
        m.usage.mockResolvedValue({ error: { detail: "x" } });
        const encore = await ouvrirLeDocument();
        await waitFor(() => expect(encore.textContent).toContain("indisponible"));
        expect(screen.queryByTestId("agents-du-document")).toBeNull();
    });

    it("un document qui n'est pas du texte (PDF) ne lit pas son contenu", async () => {
        m.liste.mockResolvedValue({ data: { documents: [{ ...DOC, filename: "Catalogue.pdf", mime_type: "application/pdf" }] } });
        m.usage.mockResolvedValue({ data: { nombre: 1, agents: [{ workflow_id: 1, nom: "Alice" }] } });
        render(
            <FournisseurLangue>
                <PageConnaissances />
            </FournisseurLangue>,
        );
        fireEvent.click((await screen.findByText("Catalogue.pdf")).closest("tr")!);
        expect((await screen.findByTestId("agents-du-document")).textContent).toBe("1 agent");
        expect(m.contenu).not.toHaveBeenCalled();
        expect(screen.queryByTestId("texte-du-document")).toBeNull();
    });
});

describe("[.mark] lot 14 : l'éditeur d'un document est en français (K-1)", () => {
    it("ses textes visibles, son champ et ses boutons sont en français", async () => {
        m.contenu.mockResolvedValue({ data: { content: "texte", file_hash: "h" } });
        render(
            <FournisseurLangue>
                <DocumentEditor doc={DOC as never} onClose={vi.fn()} onSaved={vi.fn()} />
            </FournisseurLangue>,
        );
        const champ = await screen.findByLabelText("Texte du document");
        expect((champ as HTMLTextAreaElement).value).toBe("texte");
        expect(screen.getByRole("button", { name: "Annuler" })).toBeTruthy();
        expect(screen.getByRole("button", { name: "Enregistrer" })).toBeTruthy();
        expect(document.body.textContent).toContain("Les agents gardent la version actuelle");
        expect(document.body.textContent).not.toMatch(/Agents keep using|Cancel|Loading document/);
    });
});
