/**
 * [.mark] J : les compteurs de la barre latérale viennent de vraies routes.
 *   - Relation clients › Messages : la somme des messages non lus des clients (`/relation/clients`) ;
 *   - un compteur sans source ou à zéro n'est pas affiché (jamais de fausse valeur) ;
 *   - hors de l'espace Relation clients, rien n'est lu ;
 *   - la page et la barre partagent UNE lecture de la liste des clients.
 */
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ clients: vi.fn(), auth: { user: { id: 1 } as { id: number } | null, loading: false } }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), { listerClientsApiV1RelationClientsGet: m.clients }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => m.auth }));

const { useCompteursBarre } = await import("./compteurs-barre");
const { lireClientsRelation, oublierLectureClients } = await import("../relation/lecture-clients");

afterEach(() => {
    m.clients.mockReset();
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

    it("hors de l'espace Relation clients, ou avant la connexion, ne lit rien", () => {
        renderHook(() => useCompteursBarre("labo", "/labo"));
        renderHook(() => useCompteursBarre("client", "/clients/a"));
        m.auth.user = null;
        renderHook(() => useCompteursBarre("relation", "/relation"));
        expect(m.clients).not.toHaveBeenCalled();
    });

    it("la barre et la page partagent une seule lecture des clients", async () => {
        m.clients.mockResolvedValue({ data: [] });
        await Promise.all([lireClientsRelation(), lireClientsRelation()]);
        expect(m.clients).toHaveBeenCalledTimes(1);
    });
});
