/**
 * [.mark] J : les compteurs de la barre latérale viennent de vraies routes.
 *   - Relation clients › Messages : la somme des messages non lus des clients (`/relation/clients`) ;
 *   - un compteur sans source ou à zéro n'est pas affiché (jamais de fausse valeur) ;
 *   - Chat = les conversations du builder qui attendent, À améliorer = à trier + à juger (rouge dans le Labo, gris chez un client) ;
 *   - ces deux compteurs partent ensemble ; à zéro ou refusés, rien n'est affiché ; dans l'espace Relation clients ils ne sont pas lus ;
 *   - la page et la barre partagent UNE lecture de la liste des clients.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ clients: vi.fn(), chat: vi.fn(), amelio: vi.fn(), tous: vi.fn(), auth: { user: { id: 1 } as { id: number } | null, loading: false } }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        listerClientsApiV1RelationClientsGet: m.clients,
        compterLesFilsApiV1BuilderFilsCompteurGet: m.chat,
        compterLesAmeliorationsApiV1AmeliorationsCompteurGet: m.amelio,
        compteursDeTousLesClientsApiV1VuesEquipeCompteursGet: m.tous,
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => m.auth }));

const { useCompteursBarre } = await import("./compteurs-barre");
const { lireClientsRelation, oublierLectureClients } = await import("../relation/lecture-clients");

afterEach(() => {
    m.clients.mockReset();
    m.chat.mockReset();
    m.amelio.mockReset();
    m.tous.mockReset();
    m.auth.user = { id: 1 };
    m.auth.loading = false;
    oublierLectureClients();
});

describe("[.mark] J : compteurs de la barre", () => {
    it("Messages = la somme des non lus des clients, en urgent", async () => {
        m.clients.mockResolvedValue({ data: [{ id: 1, non_lus: 2 }, { id: 2, non_lus: 3 }, { id: 3, non_lus: 0 }] });
        const { result } = renderHook(() => useCompteursBarre("relation", "/relation"));
        await waitFor(() => expect(result.current).toEqual({ "relation-messages": { n: 5, urgent: true } }));
    });

    it("rien de non lu ou lecture refusée : aucun compteur", async () => {
        m.clients.mockResolvedValue({ data: [{ id: 1, non_lus: 0 }] });
        const { result, unmount } = renderHook(() => useCompteursBarre("relation", "/relation"));
        await waitFor(() => expect(m.clients).toHaveBeenCalledTimes(1));
        expect(result.current).toEqual({});
        unmount();
        oublierLectureClients();
        m.clients.mockResolvedValue({ error: { detail: "x" } });
        const refus = renderHook(() => useCompteursBarre("relation", "/relation"));
        await waitFor(() => expect(m.clients).toHaveBeenCalledTimes(2));
        expect(refus.result.current).toEqual({});
    });

    it("Labo : les pastilles comptent tous les clients ouverts (une seule route d'équipe)", async () => {
        m.tous.mockResolvedValue({ data: { totaux: { chat_en_attente: 5, a_trier: 7 } } });
        const { result } = renderHook(() => useCompteursBarre("labo", "/labo/qualite"));
        await waitFor(() => expect(result.current).toEqual({ chat: { n: 5, urgent: true }, "a-ameliorer": { n: 7, urgent: true } }));
        expect(m.chat).not.toHaveBeenCalled();
        expect(m.amelio).not.toHaveBeenCalled();
    });

    it("Chat et À améliorer : rouges dans le Labo, partent ensemble (route d'équipe refusée : le Labo seul)", async () => {
        m.tous.mockResolvedValue({ error: { detail: "x" } });
        m.chat.mockResolvedValue({ data: { en_attente: 2 } });
        m.amelio.mockResolvedValue({ data: { a_trier: 3, a_juger: 1, total: 4 } });
        const { result } = renderHook(() => useCompteursBarre("labo", "/labo/builder"));
        await waitFor(() => expect(result.current).toEqual({ chat: { n: 2, urgent: true }, "a-ameliorer": { n: 4, urgent: true } }));
        expect(m.chat).toHaveBeenCalledTimes(1);
        expect(m.amelio).toHaveBeenCalledTimes(1);
        expect(m.clients).not.toHaveBeenCalled();
    });

    it("chez un client les pastilles sont grises ; à zéro ou refusées, rien", async () => {
        m.chat.mockResolvedValue({ data: { en_attente: 0 } });
        m.amelio.mockResolvedValue({ data: { a_trier: 1, a_juger: 0, total: 1 } });
        const { result } = renderHook(() => useCompteursBarre("client", "/clients/a/chat"));
        await waitFor(() => expect(result.current).toEqual({ "a-ameliorer": { n: 1, urgent: false } }));
        m.chat.mockResolvedValue({ error: { detail: "x" } });
        m.amelio.mockResolvedValue({ error: { detail: "x" } });
        const refus = renderHook(() => useCompteursBarre("client", "/clients/b/chat"));
        await waitFor(() => expect(m.amelio).toHaveBeenCalledTimes(2));
        expect(refus.result.current).toEqual({});
    });

    it("hors du Labo et des clients, ou avant la connexion, ne lit rien", () => {
        m.clients.mockResolvedValue({ data: [] });
        renderHook(() => useCompteursBarre("relation", "/relation"));
        m.auth.user = null;
        renderHook(() => useCompteursBarre("labo", "/labo"));
        expect(m.chat).not.toHaveBeenCalled();
        expect(m.amelio).not.toHaveBeenCalled();
    });

    it("la barre et la page partagent une seule lecture des clients", async () => {
        m.clients.mockResolvedValue({ data: [] });
        await Promise.all([lireClientsRelation(), lireClientsRelation()]);
        expect(m.clients).toHaveBeenCalledTimes(1);
    });
});
