/**
 * [.mark] U12 (lot I1) : les deux sources de chaque cerveau à l'écran, la conversation Claude Code en lecture seule, le direct.
 *
 * Questions : l'onglet Sources règle-t-il UNE brique à la fois, tout sur Claude Code au départ ? Le miroir est-il éteint au départ ?
 * Une conversation Claude Code montre-t-elle sa marque et pas de saisie ? Le builder sur Claude Code ferme-t-il la saisie et le dit-il ?
 * Une écriture de Claude Code s'affiche-t-elle « Modifié par Claude Code (Evan) · à l'instant » et relit-elle l'écran ?
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const etat = vi.hoisted(() => ({
    sources: { builder: "claude_code", appelant: "claude_code", juge_tests: "claude_code", juge_appels: "claude_code", analyse: "claude_code" } as Record<string, string>,
    miroir: false,
    flux: [] as string[],
}));

const regler = vi.fn(async (o: { path: { brique: string }; body: { source: string } }) => {
    etat.sources = { ...etat.sources, [o.path.brique]: o.body.source };
    return { data: { sources: etat.sources } };
});
const reglerMiroir = vi.fn(async (o: { body: { actif: boolean } }) => {
    etat.miroir = o.body.actif;
    return { data: { actif: etat.miroir } };
});

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/client", () => ({
    lireLesSourcesApiV1BuilderSourcesGet: async () => ({ data: { sources: etat.sources } }),
    reglerUneSourceApiV1BuilderSourcesBriquePut: (o: never) => regler(o),
    lireLeMiroirApiV1BuilderMiroirReglageGet: async () => ({ data: { actif: etat.miroir } }),
    reglerLeMiroirApiV1BuilderMiroirReglagePut: (o: never) => reglerMiroir(o),
    suivreLesModificationsApiV1BuilderLiveGet: async () => {
        const blocs = etat.flux;
        etat.flux = []; // le serveur ne renvoie que ce qui suit le dernier identifiant reçu
        return {
        data: new ReadableStream<Uint8Array>({
            start(c) {
                for (const b of blocs) c.enqueue(new TextEncoder().encode(b));
                c.close();
            },
        }),
        };
    },
}));
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: { suivre: (p: Promise<unknown>) => void p } }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));

const filCourant = vi.hoisted(() => ({
    fil: { id: 6, titre: "Corriger la relecture", etat: "en_cours", genre: "claude_code", auteur: "Evan", jetons: 0, cout: 0, jauge: 0, changements: 0, sous_agents_actifs: true, workflow_id: 320 } as Record<string, unknown>,
}));
vi.mock("@/components/builder/chat/useFil", () => ({
    useFil: () => ({
        fil: filCourant.fil,
        lignes: [],
        erreur: null,
        enCours: filCourant.fil.etat === "en_cours",
        dernier: null,
        envoyer: vi.fn(),
        arreter: vi.fn(),
        reprendre: vi.fn(),
        modifierDernier: vi.fn(),
        rafraichir: vi.fn(),
        repondreDepense: vi.fn(),
    }),
}));
vi.mock("@/components/builder/chat/SousAgents", () => ({
    useSousAgents: () => ({ sous_agents: [], recharger: vi.fn() }),
    ListeDesSousAgents: () => null,
    CarteSousAgents: () => null,
    libelleEtat: (e: string) => e,
}));
vi.mock("@/components/builder/chat/RevueChampParChamp", () => ({ RevueChampParChamp: () => null }));

import { FilDuBuilder } from "@/components/builder/chat/FilDuBuilder";

import { OngletSources } from "./OngletSources";
import { AvertissementClaudeCode } from "./marques";
import { LigneLive } from "./useModifications";

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    etat.sources = { builder: "claude_code", appelant: "claude_code", juge_tests: "claude_code", juge_appels: "claude_code", analyse: "claude_code" };
    etat.miroir = false;
    etat.flux = [];
    filCourant.fil = { id: 6, titre: "Corriger la relecture", etat: "en_cours", genre: "claude_code", auteur: "Evan", jetons: 0, cout: 0, jauge: 0, changements: 0, sous_agents_actifs: true, workflow_id: 320 };
});

const bloc = (id: number, m: Record<string, unknown>) => `id: ${id}\ndata: ${JSON.stringify({ type: "modification", ...m })}\n\n`;

describe("onglet Sources", () => {
    it("une ligne par brique, tout sur Claude Code au départ, le miroir éteint", async () => {
        render(<OngletSources />);
        await screen.findByText("Builder");
        for (const nom of ["Builder", "Simulated caller", "Test judge", "Real-call judge", "Call analysis"]) {
            expect(screen.getByText(nom)).toBeTruthy();
        }
        const claudeCode = screen.getAllByRole("button", { name: "Claude Code" });
        expect(claudeCode).toHaveLength(5);
        claudeCode.forEach((b) => expect(b.getAttribute("aria-pressed")).toBe("true"));
        expect(screen.getByRole("button", { name: "Off" }).getAttribute("aria-pressed")).toBe("true");
    });

    it("choisir « Clé d'API » règle UNE seule brique", async () => {
        render(<OngletSources />);
        await screen.findByText("Builder");
        fireEvent.click(screen.getAllByRole("button", { name: "API key" })[1]);
        await waitFor(() => expect(regler).toHaveBeenCalledTimes(1));
        expect(regler.mock.calls[0][0]).toEqual({ path: { brique: "appelant" }, body: { source: "cle_api" } });
        await waitFor(() => expect(screen.getAllByRole("button", { name: "Claude Code" })).toHaveLength(5));
    });

    it("allumer le miroir règle l'interrupteur de la personne", async () => {
        render(<OngletSources />);
        await screen.findByText("Builder");
        await screen.findByRole("button", { name: "On" });
        fireEvent.click(screen.getByRole("button", { name: "On" }));
        await waitFor(() => expect(reglerMiroir).toHaveBeenCalledWith({ body: { actif: true } }));
    });
});

describe("la conversation Claude Code et le builder sur Claude Code", () => {
    it("une conversation Claude Code montre sa marque et « lecture seule », sans saisie", async () => {
        render(<FilDuBuilder filId={6} />);
        expect(await screen.findByText(/Claude Code · Evan/)).toBeTruthy();
        expect(screen.getByText(/Conversation led in Claude Code: read only/)).toBeTruthy();
        expect(screen.getByText("Live")).toBeTruthy();
        expect(screen.queryByRole("textbox")).toBeNull();
        expect(screen.queryByText(/builder is working/)).toBeNull(); // le travail se fait dans Claude Code, pas ici
    });

    it("le builder sur Claude Code ferme la saisie du chat de l'écran et le dit", async () => {
        filCourant.fil = { ...filCourant.fil, genre: "principal", etat: "terminee", auteur: null };
        render(<FilDuBuilder filId={7} />);
        expect(await screen.findByText(/set to be used in Claude Code/)).toBeTruthy();
        expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(true);
        expect((screen.getByRole("button", { name: "Send" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("sur clé d'API la saisie reste ouverte et l'avertissement disparaît", async () => {
        etat.sources = { ...etat.sources, builder: "cle_api" };
        filCourant.fil = { ...filCourant.fil, genre: "principal", etat: "terminee", auteur: null };
        render(<FilDuBuilder filId={7} />);
        await waitFor(() => expect(screen.queryByText(/set to be used in Claude Code/)).toBeNull());
        expect((screen.getByRole("textbox") as HTMLTextAreaElement).disabled).toBe(false);
    });

    it("la carte rouge mène à l'onglet Sources", () => {
        render(<AvertissementClaudeCode />);
        expect(screen.getByRole("link", { name: "Change the source" }).getAttribute("href")).toBe("/labo/reglages?onglet=sources");
    });
});

describe("mise à jour en direct", () => {
    it("une écriture de Claude Code s'affiche, nomme son auteur et relit l'écran", async () => {
        etat.flux = [bloc(1, { objet: "agent:320", action: "brouillon_operation", source: "claude_code", auteur: "Evan", le: null })];
        const quand = vi.fn();
        render(<LigneLive objet="agent:320" quand={quand} />);
        expect(await screen.findByText(/Modified by Claude Code \(Evan\)/)).toBeTruthy();
        expect(quand).toHaveBeenCalledTimes(1);
    });

    it("une écriture de l'écran relit l'écran mais ne porte pas la mention Claude Code", async () => {
        etat.flux = [bloc(1, { objet: "agent:320", action: "reglages_regler", source: "ecran", auteur: "Evan", le: null })];
        const quand = vi.fn();
        render(<LigneLive objet="agent:320" quand={quand} />);
        await waitFor(() => expect(quand).toHaveBeenCalledTimes(1));
        await act(async () => {});
        expect(screen.queryByText(/Modified by Claude Code/)).toBeNull();
    });
});
