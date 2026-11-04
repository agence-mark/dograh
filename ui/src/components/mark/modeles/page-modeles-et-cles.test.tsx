/**
 * [.mark] V2b (E51) : la page « Modèles et clés » à la maquette (quatre cartes, tableau des clés), montée sur la
 * vraie fenêtre d'un service.
 *
 * Questions de ce fichier :
 *
 *     La page montre-t-elle une carte par brique, avec le fournisseur, le modèle, la clé NOMMÉE (jamais sa valeur)
 *     et « remplacé par N agents » ? Un clic ouvre la fenêtre de la bonne brique ? Enregistrer une brique envoie la
 *     configuration entière (les autres briques gardées) ? Un refus du serveur dit une phrase, jamais son texte ?
 *     Le mode temps réel montre-t-il le modèle temps réel ? Le tableau des clés dit où chaque clé sert, d'après une
 *     seule lecture ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    enregistrer: vi.fn(),
    lireUsages: vi.fn(),
    fenetre: vi.fn(),
    echec: vi.fn(),
    succes: vi.fn(),
}));

const CONFIGURATION = {
    version: 2,
    mode: "byok",
    byok: {
        mode: "pipeline",
        pipeline: {
            llm: { provider: "mistral", api_key: "mark-cle:c-mistral", model: "mistral-small-2603" },
            tts: { provider: "cartesia", api_key: "mark-cle:c-cartesia", model: "sonic-3.6", voice: "3faa81ae-d3d8-4ab1" },
            stt: { provider: "soniox", api_key: "****1234", model: "stt-rt-v3" },
        },
    },
};
const schema = { required: ["api_key"], properties: {} };
const DEFAUTS = {
    dograh: {},
    byok: {
        pipeline: {
            llm: { mistral: schema },
            tts: { cartesia: schema },
            stt: { soniox: schema },
            embeddings: { openai: schema },
            default_providers: {},
        },
        realtime: { realtime: { openai_realtime: schema }, llm: { mistral: schema }, embeddings: { openai: schema }, default_providers: {} },
    },
};
const CLES = [
    { uuid: "c-mistral", nom: "Mistral (Labo)", fournisseur: "mistral" },
    { uuid: "c-cartesia", nom: "Cartesia (Labo)", fournisseur: "cartesia" },
    { uuid: "c-vieille", nom: "ElevenLabs (essai)", fournisseur: "elevenlabs" },
];

vi.mock("@/client", () => ({
    listerLesClesApiV1ClesGet: async () => ({ data: CLES }),
    usagesDeToutesLesClesApiV1ClesUsagesGet: m.lireUsages,
    fournisseursDesClesApiV1ClesFournisseursGet: async () => ({ data: ["mistral"] }),
    ajouterUneCleApiV1ClesPost: vi.fn(),
    supprimerUneCleApiV1ClesUuidDelete: vi.fn(),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: async () => ({ data: DEFAUTS }),
        getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: async () => ({
            data: { configuration: CONFIGURATION, effective_configuration: {}, source: "organization" },
        }),
        getModelConfigurationV2RemplacementsApiV1OrganizationsModelConfigurationsV2RemplacementsGet: async () => ({
            data: { llm: 0, tts: 1, stt: 0, realtime: 0 },
        }),
        saveModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Put: m.enregistrer,
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ refreshConfig: async () => undefined }) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { echec: m.echec, succes: m.succes } }));
vi.mock("./FenetreService", () => ({
    FenetreService: (props: Record<string, unknown>) => {
        m.fenetre(props);
        return (
            <div role="dialog" data-service={String(props.service)}>
                <button onClick={() => void (props.enregistrer as (c: Record<string, unknown>) => Promise<void>)(SORTIE_LLM).catch((e: Error) => {
                    document.body.setAttribute("data-erreur", e.message);
                })}>
                    enregistrer
                </button>
            </div>
        );
    },
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const SORTIE_LLM = { llm: { provider: "mistral", api_key: "mark-cle:c-mistral", model: "mistral-medium-2508" } };

import { PageModelesEtCles } from "./PageModelesEtCles";

beforeEach(() => {
    m.enregistrer.mockReset();
    m.fenetre.mockReset();
    m.echec.mockReset();
    m.succes.mockReset();
    m.lireUsages.mockReset();
    m.lireUsages.mockResolvedValue({
        data: {
            "c-mistral": [{ ou: "modeles_organisation", nom: null }, { ou: "reglages_modele", nom: null }],
            "c-cartesia": [{ ou: "modeles_organisation", nom: null }],
            "c-vieille": [],
        },
    });
    document.body.removeAttribute("data-erreur");
});
afterEach(cleanup);

const carte = (service: string) => document.querySelector(`[data-brique="${service}"]`) as HTMLElement;

describe("les cartes", () => {
    it("montrent chaque brique : fournisseur, modèle, clé nommée, agents qui la remplacent", async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        await waitFor(() => expect(carte("llm").textContent).toContain("Mistral (Labo)"));
        expect(carte("llm").textContent).toContain("mistral-small-2603");
        // La voix : le modèle, jamais l'identifiant de voix ; « remplacé par 1 agent ».
        expect(carte("tts").textContent).toContain("sonic-3.6");
        expect(carte("tts").textContent).not.toContain("3faa81ae");
        expect(carte("tts").textContent).toContain("replaced by 1 agent");
        // Une clé tapée à la main : dite, jamais montrée.
        expect(carte("stt").textContent).toContain("Typed key");
        expect(carte("stt").textContent).not.toContain("1234");
        // Plongement jamais réglé.
        expect(carte("embeddings").textContent).toContain("Not set");
    });

    it("le temps réel montre le modèle temps réel, le cerveau et le plongement", async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        expect(carte("realtime")).not.toBeNull();
        expect(carte("tts")).toBeNull();
        expect(carte("llm")).not.toBeNull();
        expect(carte("realtime").textContent).toContain("Not set");
    });
});

describe("une carte ouvre la fenêtre de sa brique", () => {
    it("avec la seule brique, quand la configuration est complète", async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("tts")).not.toBeNull());
        fireEvent.click(carte("tts"));
        const props = m.fenetre.mock.calls.at(-1)![0];
        expect(props).toMatchObject({ service: "tts", portee: "organisation", segments: ["tts"] });
    });

    it("avec la brique à régler en plus, pour le temps réel quand il n'est pas réglé", async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        fireEvent.click(carte("realtime"));
        expect(m.fenetre.mock.calls.at(-1)![0]).toMatchObject({ service: "realtime", segments: ["realtime"] });
    });
});

describe("enregistrer", () => {
    const enregistrerDepuisLaFenetre = async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(carte("llm"));
        fireEvent.click(within(screen.getByRole("dialog")).getByText("enregistrer"));
    };

    it("envoie la configuration entière : le cerveau change, la voix et la transcription restent", async () => {
        m.enregistrer.mockResolvedValue({ data: { configuration: CONFIGURATION, effective_configuration: {}, source: "organization" } });
        await enregistrerDepuisLaFenetre();
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalled());
        const pipeline = m.enregistrer.mock.calls[0][0].body.byok.pipeline;
        expect(pipeline.llm.model).toBe("mistral-medium-2508");
        expect(pipeline.tts.provider).toBe("cartesia");
        expect(pipeline.stt.api_key).toBe("****1234");
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
    });

    it("un refus du fournisseur dit une phrase, jamais le texte du serveur", async () => {
        m.enregistrer.mockResolvedValue({ error: { detail: "Mistral: 401 invalid_api_key sk-SECRET" }, response: { status: 422 } });
        await enregistrerDepuisLaFenetre();
        await waitFor(() => expect(document.body.getAttribute("data-erreur")).toContain("The provider refuses this configuration"));
        expect(document.body.getAttribute("data-erreur")).not.toContain("sk-SECRET");
        expect(m.echec).toHaveBeenCalled();
        expect(m.succes).not.toHaveBeenCalled();
    });

    it("un refus de droits dit qu'on n'a pas le droit", async () => {
        m.enregistrer.mockResolvedValue({ error: { detail: "Forbidden" }, response: { status: 403 } });
        await enregistrerDepuisLaFenetre();
        await waitFor(() => expect(document.body.getAttribute("data-erreur")).toContain("not allowed"));
        // La notification dit le refus de droits, elle ne propose pas de « réessayer ».
        expect(m.echec.mock.calls[0][0].fr).not.toMatch(/Réessayez/);
    });
});

describe("le tableau des clés", () => {
    it("dit où chaque clé sert, d'après UNE lecture, et « nulle part » pour une clé libre", async () => {
        render(<PageModelesEtCles />);
        const tableau = await screen.findByTestId("page-cles");
        await waitFor(() => expect(within(tableau).getByText("Mistral (Labo)")).toBeTruthy());
        await waitFor(() => expect(tableau.textContent).toContain("Models of the organization · Simulated caller"));
        expect(tableau.textContent).toContain("nowhere");
        expect(m.lireUsages).toHaveBeenCalledTimes(1);
    });

    it("ne lit pas les usages avant que les clés soient lues (la session n'est pas prête)", async () => {
        render(<PageModelesEtCles />);
        await screen.findByTestId("page-cles");
        // Le premier rendu n'a pas de clés : aucune lecture des usages n'est partie à ce moment-là.
        expect(m.lireUsages.mock.calls.length).toBeLessThanOrEqual(1);
    });
});
