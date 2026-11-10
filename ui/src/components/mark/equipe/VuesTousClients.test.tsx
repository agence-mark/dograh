/**
 * [.mark] Partie 3, sous-lot 10 : les listes « tous clients » du Labo (colonne Client des conversations, Chat du Labo).
 * Lecture seule : une ligne mène chez le client ; un refus (403) dit « accès » ; la pagination ne lit que la page demandée.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ conv: vi.fn(), chat: vi.fn(), push: vi.fn() }));
vi.mock("@/client", () => ({
    conversationsDeTousLesClientsApiV1VuesEquipeConversationsGet: (o: unknown) => m.conv(o),
    chatDeTousLesClientsApiV1VuesEquipeChatGet: (o: unknown) => m.chat(o),
}));
vi.mock("@/lib/auth", () => ({ useAuth: (() => { const s = { user: { id: "u" }, loading: false }; return () => s; })() }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: m.push }), usePathname: () => "/labo/conversations" }));

const { ChatTousClients, ConversationsTousClients } = await import("./VuesTousClients");

const monter = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);
const CONV = { id: 5, name: "Appel 5", workflow_id: 3, workflow_name: "Accueil", organization_id: 41, organization_nom: "Plomberie Garnier", mode: "twilio", is_completed: true, created_at: "2026-11-04T09:00:00Z" };
const FIL = { id: 9, organization_id: 41, organization_nom: "Plomberie Garnier", workflow_id: 3, titre: "Ajoute les horaires", etat: "terminee", cout: 0.1, changements: 2, auteur: null, genre: "principal", modifie_le: "2026-11-04T09:00:00Z" };

beforeEach(() => {
    m.conv.mockResolvedValue({ data: { conversations: [CONV], total: 1, limit: 25, offset: 0 } });
    m.chat.mockResolvedValue({ data: { fils: [FIL], total: 60, limit: 25, offset: 0 } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("Conversations, tous clients", () => {
    it("montre le client de chaque appel et mène chez lui", async () => {
        monter(<ConversationsTousClients />);
        const ligne = (await screen.findByText("Plomberie Garnier")).closest("tr")!;
        expect(ligne.textContent).toContain("Accueil");
        fireEvent.click(ligne);
        expect(m.push).toHaveBeenCalledWith("/clients/41/conversations");
        expect(m.conv).toHaveBeenCalledWith({ query: { limit: 25, offset: 0 } });
    });

    it("sans appel : un état vide, jamais un tableau vide", async () => {
        m.conv.mockResolvedValue({ data: { conversations: [], total: 0, limit: 25, offset: 0 } });
        monter(<ConversationsTousClients />);
        expect(await screen.findByText("Aucun appel encore")).toBeTruthy();
        expect(document.querySelector("table")).toBeNull();
    });

    it("refus (403) = accès ; panne = réessayer", async () => {
        m.conv.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 403 } });
        monter(<ConversationsTousClients />);
        await waitFor(() => expect(m.conv).toHaveBeenCalledTimes(1));
        expect(screen.queryByRole("button", { name: /Réessayer/ })).toBeNull();
        cleanup();
        m.conv.mockResolvedValueOnce({ error: { detail: "x" }, response: { status: 500 } });
        monter(<ConversationsTousClients />);
        fireEvent.click(await screen.findByRole("button", { name: /Réessayer/ }));
        expect(await screen.findByText("Plomberie Garnier")).toBeTruthy();
    });
});

describe("Conversations, tous clients : la liste de la maquette (clôture SA-5, É8)", () => {
    const COMPLETE = { ...CONV, motif: "Devis", resume: "Un devis pour une chaudière.", resume_source: "synthese", issue: "RDV_pris", duree: 192, juge_par: "Claude Code · Léa", note_juge: 2.5 };

    it("montre Quand, Agent, Client, Motif, Résumé, Issue, Durée, Jugé par et Note", async () => {
        m.conv.mockResolvedValue({ data: { conversations: [COMPLETE], total: 1, limit: 25, offset: 0, motifs: ["Devis", "Dépannage"] } });
        monter(<ConversationsTousClients />);
        await screen.findByText("Plomberie Garnier");
        expect(Array.from(document.querySelectorAll("thead th")).map((t) => t.textContent)).toEqual(["Quand", "Agent", "Client", "Motif", "Résumé", "Issue", "Durée", "Jugé par", "Note"]);
        const ligne = document.querySelector("tbody tr")!;
        for (const texte of ["Accueil", "Devis", "Un devis pour une chaudière.", "RDV_pris", "3m 12s", "Claude Code · Léa", "2,5"]) expect(ligne.textContent).toContain(texte);
        expect(ligne.querySelector("[data-urgente]")).not.toBeNull(); // sous le seuil : pastille rouge
        expect(document.body.textContent).not.toMatch(/twilio|Terminée|En cours/); // plus de Mode ni d'État : la maquette
    });

    it("le motif choisi et la recherche partent au serveur, la liste des motifs vient du serveur", async () => {
        m.conv.mockResolvedValue({ data: { conversations: [COMPLETE], total: 1, limit: 25, offset: 0, motifs: ["Devis", "Dépannage"] } });
        monter(<ConversationsTousClients />);
        const liste = (await screen.findByLabelText("Motif")) as HTMLSelectElement;
        expect(Array.from(liste.options).map((o) => o.textContent)).toEqual(["Tous les motifs", "Devis", "Dépannage"]);
        fireEvent.change(liste, { target: { value: "Dépannage" } });
        await waitFor(() => expect(m.conv).toHaveBeenLastCalledWith({ query: { limit: 25, offset: 0, motif: "Dépannage" } }));
    });

    it("sans résultat pour un filtre : la barre reste, avec « Effacer les filtres »", async () => {
        m.conv.mockResolvedValueOnce({ data: { conversations: [COMPLETE], total: 1, limit: 25, offset: 0, motifs: ["Devis"] } });
        monter(<ConversationsTousClients />);
        const liste = (await screen.findByLabelText("Motif")) as HTMLSelectElement;
        m.conv.mockResolvedValue({ data: { conversations: [], total: 0, limit: 25, offset: 0, motifs: ["Devis"] } });
        fireEvent.change(liste, { target: { value: "Devis" } });
        await waitFor(() => expect(document.querySelector("table")).toBeNull());
        expect(screen.getByLabelText("Chercher un mot")).toBeTruthy();
        expect(screen.queryByText("Aucun appel encore")).toBeNull();
        expect(screen.getAllByText("Effacer les filtres").length).toBeGreaterThan(0);
    });
});

describe("Chat du Labo, tous clients", () => {
    it("cherche dans les titres et les clients, et dit la marque de Claude Code", async () => {
        m.chat.mockResolvedValue({ data: { fils: [FIL, { ...FIL, id: 10, titre: "Corrige l'accueil", organization_nom: "Atelier", genre: "claude_code", auteur: "Evan", etat: "en_cours" }], total: 2, limit: 25, offset: 0 } });
        monter(<ChatTousClients />);
        await screen.findByText("Corrige l'accueil");
        expect(screen.getByText(/Claude Code/)).toBeTruthy();
        fireEvent.change(screen.getByRole("textbox", { name: "Rechercher un chat" }), { target: { value: "atelier" } });
        expect(screen.queryByText("Ajoute les horaires")).toBeNull();
        expect(screen.getByText("Corrige l'accueil")).toBeTruthy();
    });

    it("liste les conversations du builder avec leur client, et la page suivante lit le décalage suivant", async () => {
        monter(<ChatTousClients />);
        // Clôture D2 (É6) : une liste nue (plus un tableau) : titre, client, quand ; la ligne est un lien chez le client.
        const ligne = (await screen.findByText("Ajoute les horaires")).closest("a")!;
        expect(ligne.textContent).toContain("Plomberie Garnier");
        expect(ligne.getAttribute("href")).toBe("/clients/41/chat/9");
        expect(document.querySelector("table")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Suivant" }));
        await waitFor(() => expect(m.chat).toHaveBeenLastCalledWith({ query: { limit: 25, offset: 25 } }));
    });
});
