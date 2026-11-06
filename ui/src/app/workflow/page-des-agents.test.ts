// [.mark] V1 : la liste des agents se lit côté serveur ; l'organisation doit venir de l'adresse, jamais du compte
// (sinon `/clients/2/agents` montrait les agents du Labo sous le nom du client).
import { describe, expect, it, vi } from "vitest";

const espaces = vi.fn();
vi.mock("@/client/sdk.gen", () => ({
    getAgentsServisApiV1OrganizationsAgentsServisGet: vi.fn(),
    getWorkflowsApiV1WorkflowFetchGet: vi.fn(),
    lireLesGroupesApiV1WorkflowGroupesGet: vi.fn(),
    listFoldersApiV1FolderGet: vi.fn(),
    listerLesEspacesApiV1EspacesGet: (...a: unknown[]) => espaces(...a),
}));
vi.mock("@/lib/auth/server", () => ({ getServerAccessToken: vi.fn(), getServerAuthProvider: vi.fn() }));
vi.mock("@/components/mark/agent/ListeAgents", () => ({ ListeAgents: () => null }));
vi.mock("./WorkflowLayout", () => ({ default: () => null }));

const introuvable = vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
});
vi.mock("next/navigation", () => ({ notFound: () => introuvable(), redirect: vi.fn() }));

const { enteteOrganisation, PageDesAgents } = await import("./page-des-agents");

describe("organisation de la liste des agents (côté serveur)", () => {
    it("chez un client, l'identifiant de l'adresse part en en-tête", async () => {
        expect(await enteteOrganisation("jeton", "2", false)).toEqual({ "X-Mark-Organisation": "2" });
    });

    it("sur /labo, c'est le Labo que disent les espaces du compte", async () => {
        espaces.mockResolvedValue({ data: { espaces: [{ id: 2, espace: "client" }, { id: 1, espace: "labo" }] } });
        expect(await enteteOrganisation("jeton", undefined, true)).toEqual({ "X-Mark-Espace": "labo", "X-Mark-Organisation": "1" });
    });

    it("sur /labo, si la lecture des espaces échoue, le serveur reçoit quand même l'espace Labo (jamais le compte)", async () => {
        espaces.mockRejectedValue(new Error("panne"));
        expect(await enteteOrganisation("jeton", undefined, true)).toEqual({ "X-Mark-Espace": "labo" });
    });

    it("une adresse neutre garde l'organisation du compte, et une adresse truquée n'envoie rien", async () => {
        expect(await enteteOrganisation("jeton", undefined, false)).toEqual({});
        expect(await enteteOrganisation("jeton", "2; DROP", false)).toEqual({});
    });

    it("/clients/<pas un nombre> est une page introuvable (R3)", async () => {
        await expect(PageDesAgents({ params: Promise.resolve({ org: "acme" }) })).rejects.toThrow("NEXT_NOT_FOUND");
        expect(introuvable).toHaveBeenCalled();
    });
});
