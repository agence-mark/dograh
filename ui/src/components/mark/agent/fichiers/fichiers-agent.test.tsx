/**
 * [.mark] Partie 3, N3b : les fenêtres « Exporter en fichiers » et « Importer des fichiers » d'un agent.
 *
 * Questions de ce fichier :
 *
 *     L'export ne demande-t-il que les contenus cochés, au serveur, sous forme d'archive ? Un dossier choisi donne-t-il l'aperçu fichier
 *     par fichier (sans rien écrire), puis l'import part-il avec exactement les fichiers du dossier ? Un dossier sans fichier reconnu
 *     est-il dit, sans appel au serveur ? Rien d'autre que du YAML et du Markdown n'est lu.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ exporter: vi.fn(), importer: vi.fn(), succes: vi.fn(), avertissement: vi.fn(), echec: vi.fn() }));

vi.mock("@/client/sdk.gen", () => ({
    exporterEnFichiersApiV1AgentFichiersWorkflowIdExportGet: (o: unknown) => m.exporter(o),
    importerDesFichiersApiV1AgentFichiersWorkflowIdImportPost: (o: unknown) => m.importer(o),
}));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, avertissement: m.avertissement, echec: m.echec } }));
vi.mock("@/components/mark/notifications/echec-affiche", () => ({ echecAffiche: () => "Échec." }));

import { FenetreExportFichiers, FenetreImportFichiers, lireLeDossier } from "./FenetreFichiersAgent";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const fichier = (chemin: string, texte: string) => {
    const f = new File([texte], chemin.split("/").pop() ?? chemin);
    Object.defineProperty(f, "webkitRelativePath", { value: chemin });
    return f;
};
const liste = (...fichiers: File[]) => Object.assign(fichiers, { item: (i: number) => fichiers[i] }) as unknown as FileList;
const monter = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("lire un dossier choisi", () => {
    it("retire le nom du dossier, ne garde que le YAML et le Markdown", async () => {
        const lu = await lireLeDossier(liste(fichier("agent/graphe.yaml", "a: 1"), fichier("agent/prompts/1-accueil.md", "Bonjour"), fichier("agent/.env", "SECRET=1"), fichier("agent/image.png", "x")));
        expect(lu).toEqual({ "graphe.yaml": "a: 1", "prompts/1-accueil.md": "Bonjour" });
    });
});

describe("Exporter en fichiers", () => {
    it("demande l'archive des seuls contenus cochés et la télécharge", async () => {
        m.exporter.mockResolvedValue({ data: new Blob(["zip"]), error: undefined });
        Object.assign(URL, { createObjectURL: vi.fn(() => "blob:x"), revokeObjectURL: vi.fn() });
        const fermer = vi.fn();
        monter(<FenetreExportFichiers agentId={42} nom="Standard Durand" fermer={fermer} />);
        fireEvent.click(await screen.findByRole("checkbox", { name: "Tests" }));
        fireEvent.click(screen.getByRole("checkbox", { name: "Blocs" }));
        fireEvent.click(screen.getByRole("button", { name: "Exporter" }));
        await waitFor(() => expect(m.exporter).toHaveBeenCalledTimes(1));
        expect(m.exporter.mock.calls[0][0]).toMatchObject({ path: { workflow_id: 42 }, query: { format: "zip", contenus: "graphe,prompts,reglages,outils" }, parseAs: "blob" });
        await waitFor(() => expect(fermer).toHaveBeenCalled());
        expect(m.succes).toHaveBeenCalled();
    });

    it("sans aucun contenu coché, le bouton est éteint", async () => {
        monter(<FenetreExportFichiers agentId={42} nom="X" fermer={vi.fn()} />);
        for (const nom of ["Graphe", "Prompts", "Réglages", "Outils épinglés", "Blocs", "Tests"]) fireEvent.click(await screen.findByRole("checkbox", { name: nom }));
        expect((screen.getByRole("button", { name: "Exporter" }) as HTMLButtonElement).disabled).toBe(true);
    });
});

describe("Importer des fichiers", () => {
    const choisir = async (fichiers: File[]) => {
        monter(<FenetreImportFichiers agentId={42} fermer={vi.fn()} apres={vi.fn()} />);
        fireEvent.change(await screen.findByTestId("choix-du-dossier"), { target: { files: liste(...fichiers) } });
    };

    it("lit l'aperçu du serveur, puis importe exactement les fichiers du dossier (jamais en ligne)", async () => {
        m.importer.mockImplementation(async ({ body }: { body: { appliquer: boolean } }) => ({
            data: {
                agent_id: 42,
                applique: body.appliquer,
                fichiers: [
                    { fichier: "prompts/1-accueil.md", effet: "modifie", detail: "2 lines" },
                    { fichier: "tests/nouveau.yaml", effet: "ajoute" },
                    { fichier: "reglages.yaml", effet: "inchange" },
                ],
                avertissements: body.appliquer ? [{ code: "outil_absent", nom: "reserver" }] : [],
            },
        }));
        await choisir([fichier("agent/agent.yaml", "format: x"), fichier("agent/prompts/1-accueil.md", "Bonjour")]);
        expect(await screen.findByText("prompts/1-accueil.md")).toBeTruthy();
        expect(screen.getByText("2 lines")).toBeTruthy();
        expect(m.importer.mock.calls[0][0].body.appliquer).toBe(false); // l'aperçu n'écrit rien
        fireEvent.click(screen.getByRole("button", { name: "Importer dans le brouillon" }));
        await waitFor(() => expect(m.importer).toHaveBeenCalledTimes(2));
        expect(m.importer.mock.calls[1][0].body).toEqual({ fichiers: { "agent.yaml": "format: x", "prompts/1-accueil.md": "Bonjour" }, appliquer: true });
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
        expect(m.avertissement).toHaveBeenCalled(); // un outil absent est dit
    });

    it("un dossier sans fichier reconnu est dit et n'appelle pas le serveur", async () => {
        await choisir([fichier("agent/image.png", "x")]);
        expect(await screen.findByText("Aucun fichier reconnu dans ce dossier.")).toBeTruthy();
        expect(m.importer).not.toHaveBeenCalled();
    });

    it("quand rien ne change, l'import est éteint", async () => {
        m.importer.mockResolvedValue({ data: { agent_id: 42, applique: false, fichiers: [{ fichier: "graphe.yaml", effet: "inchange" }], avertissements: [] } });
        await choisir([fichier("agent/graphe.yaml", "a: 1")]);
        await screen.findByText("graphe.yaml");
        expect((screen.getByRole("button", { name: "Importer dans le brouillon" }) as HTMLButtonElement).disabled).toBe(true);
    });
});
