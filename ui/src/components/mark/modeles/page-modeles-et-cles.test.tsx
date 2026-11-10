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
    basculer: vi.fn(),
    lue: null as unknown,
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
    { uuid: "c-mistral", nom: "Mistral (Labo)", fournisseur: "mistral", creee_le: "2026-10-07T10:00:00Z" },
    { uuid: "c-cartesia", nom: "Cartesia (Labo)", fournisseur: "cartesia", creee_le: "2026-10-08T10:00:00Z", adresse: "https://api.cartesia.example" },
    { uuid: "c-vieille", nom: "ElevenLabs (essai)", fournisseur: "elevenlabs" },
    { uuid: "c-sans", nom: "", fournisseur: "soniox", creee_le: "2026-10-09T10:00:00Z" },
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
        getWorkflowsSummaryApiV1WorkflowSummaryGet: async () => ({ data: [{ id: 7, name: "Accueil" }, { id: 8, name: "Rappel" }, { id: 9, name: "Doublon" }, { id: 10, name: "Doublon" }] }),
        getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: async () => ({ data: DEFAUTS }),
        getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: async () => ({
            data: { configuration: m.lue ?? CONFIGURATION, effective_configuration: {}, source: "organization" },
        }),
        getModelConfigurationV2RemplacementsApiV1OrganizationsModelConfigurationsV2RemplacementsGet: async () => ({
            data: { llm: 0, tts: 1, stt: 0, realtime: 0 },
        }),
        saveModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Put: m.enregistrer,
        switchModelConfigurationV2ModeApiV1OrganizationsModelConfigurationsV2ModePut: m.basculer,
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
    m.basculer.mockReset();
    m.lue = null;
    m.fenetre.mockReset();
    m.echec.mockReset();
    m.succes.mockReset();
    m.lireUsages.mockReset();
    m.lireUsages.mockResolvedValue({
        data: {
            "c-mistral": [{ ou: "modeles_organisation", nom: null }, { ou: "reglages_modele", nom: null }],
            "c-cartesia": [{ ou: "modeles_organisation", nom: null }],
            "c-vieille": [],
            "c-sans": [{ ou: "agent", nom: "Accueil" }, { ou: "modeles_agent", nom: "Rappel" }, { ou: "agent", nom: "Doublon" }, { ou: "outil", nom: "Agenda" }],
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

describe("la forme des cartes (point 13)", () => {
    it("tuile bordée, même hauteur, 2 colonnes quand le conteneur est étroit, nom de la clé dit", async () => {
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        await waitFor(() => expect(carte("llm").textContent).toContain("Mistral (Labo)"));
        const grille = screen.getByTestId("briques");
        expect(grille.className).toContain("grid-cols-2");
        expect(grille.className).toContain("@4xl:grid-cols-4");
        expect(grille.parentElement!.className).toContain("@container");
        for (const b of ["stt", "llm", "tts", "embeddings"]) {
            expect(carte(b).className).toContain("h-full");
            expect(carte(b).className).toContain("rounded-xl border bg-card");
        }
        expect(carte("llm").querySelector("[data-cle-de-la-brique]")!.textContent).toContain("Mistral (Labo)");
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
        expect(tableau.textContent).toContain("None");
        expect(m.lireUsages).toHaveBeenCalledTimes(1);
    });

    it("une ligne par clé : nom et fournisseur dessous, « Sans nom », utilisée par en compte, créée le, menu", async () => {
        render(<PageModelesEtCles />);
        const tableau = await screen.findByTestId("page-cles");
        await waitFor(() => expect(tableau.querySelectorAll("[data-cle-ligne]").length).toBe(4));
        const sans = tableau.querySelector("[data-cle-ligne=c-sans]") as HTMLElement;
        expect(sans.textContent).toContain("Unnamed");
        expect(sans.textContent).toContain("Soniox");
        const ligne = sans.closest("tr") as HTMLElement;
        await waitFor(() => expect(ligne.textContent).toContain("3 agents · 1 tool"));
        expect(ligne.textContent).toMatch(/Oct 9, 2026/);
        expect(within(ligne).getByRole("button", { name: /Key actions/ })).toBeTruthy();
        expect(within(tableau).getByText("Mistral (Labo)").closest("tr")!.textContent).toContain("Mistral");
    });

    it("le panneau d'une clé dit fournisseur, adresse, date, valeur jamais affichée, agents repliés puis en liens", async () => {
        render(<PageModelesEtCles />);
        const tableau = await screen.findByTestId("page-cles");
        await waitFor(() => expect(tableau.querySelector("[data-cle-ligne=c-cartesia]")).not.toBeNull());
        fireEvent.click(tableau.querySelector("[data-cle-ligne=c-cartesia]")!);
        const fenetre = await screen.findByRole("dialog");
        expect(fenetre.textContent).toContain("Provider");
        expect(fenetre.textContent).toContain("https://api.cartesia.example");
        expect(fenetre.textContent).toContain("Oct 8, 2026");
        expect(fenetre.textContent).toContain("Saved, never shown");
        cleanup();
        render(<PageModelesEtCles />);
        const t2 = await screen.findByTestId("page-cles");
        await waitFor(() => expect(t2.querySelector("[data-cle-ligne=c-sans]")).not.toBeNull());
        await waitFor(() => expect(t2.querySelector("[data-cle-ligne=c-sans]")!.closest("tr")!.textContent).toContain("3 agents"));
        fireEvent.click(t2.querySelector("[data-cle-ligne=c-sans]")!);
        const f2 = await screen.findByRole("dialog");
        expect(f2.textContent).toContain("Unnamed");
        expect(f2.querySelector("[data-lien-agent]")).toBeNull(); // repliés
        fireEvent.click(f2.querySelector("[data-usage-agents]")!);
        await waitFor(() => expect(f2.querySelector("[data-lien-agent='7']")).not.toBeNull());
        expect(f2.querySelector("[data-lien-agent='7']")!.getAttribute("href")).toContain("7");
        // Deux agents du même nom : pas de lien deviné.
        expect(within(f2).getByText("Doublon").closest("a")).toBeNull();
    });

    it("supprimer depuis le menu ouvre le panneau déjà en confirmation", async () => {
        render(<PageModelesEtCles />);
        const tableau = await screen.findByTestId("page-cles");
        await waitFor(() => expect(tableau.querySelector("[data-cle-ligne=c-vieille]")).not.toBeNull());
        const ligne = tableau.querySelector("[data-cle-ligne=c-vieille]")!.closest("tr") as HTMLElement;
        fireEvent.pointerDown(within(ligne).getByRole("button", { name: /Key actions/ }), { button: 0, ctrlKey: false });
        fireEvent.click(await screen.findByRole("menuitem", { name: /Delete the key/ }));
        const fenetre = await screen.findByRole("dialog");
        expect(fenetre.textContent).toContain("key deleted");
    });

    it("ne lit pas les usages avant que les clés soient lues (la session n'est pas prête)", async () => {
        render(<PageModelesEtCles />);
        await screen.findByTestId("page-cles");
        // Le premier rendu n'a pas de clés : aucune lecture des usages n'est partie à ce moment-là.
        expect(m.lireUsages.mock.calls.length).toBeLessThanOrEqual(1);
    });
});

describe("deux configurations gardées (lot 13, SE-24)", () => {
    const TEMPS_REEL = {
        realtime: { provider: "openai_realtime", api_key: "mark-cle:c-mistral", model: "gpt-realtime" },
        llm: { provider: "mistral", api_key: "mark-cle:c-mistral", model: "mistral-small-2603" },
    };
    const LES_DEUX = (actif: "pipeline" | "realtime") => ({
        ...CONFIGURATION,
        byok: { ...CONFIGURATION.byok, mode: actif, realtime: TEMPS_REEL },
    });

    it("dit laquelle est active, montre la configuration de l'autre et propose de l'activer", async () => {
        m.lue = LES_DEUX("pipeline");
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        expect(document.querySelector("[data-mode-actif=chaine]")).not.toBeNull();
        expect(document.querySelector("[data-activer-mode]")).toBeNull();
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        // le temps réel est gardé même s'il n'est pas actif : la carte le montre, un bouton l'active
        await waitFor(() => expect(carte("realtime").textContent).toContain("gpt-realtime"));
        expect(document.querySelector("[data-mode-actif]")).toBeNull();
        expect((document.querySelector("[data-activer-mode=temps-reel]") as HTMLButtonElement).disabled).toBe(false);
    });

    it("basculer écrit le mode, dit le résultat, et la page montre la nouvelle active", async () => {
        m.lue = LES_DEUX("pipeline");
        m.basculer.mockResolvedValue({ data: { configuration: LES_DEUX("realtime"), effective_configuration: {}, source: "organization" } });
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        fireEvent.click(await waitFor(() => document.querySelector("[data-activer-mode=temps-reel]") as HTMLElement));
        await waitFor(() => expect(m.basculer).toHaveBeenCalledWith({ body: { mode: "realtime" } }));
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
        await waitFor(() => expect(document.querySelector("[data-mode-actif=temps-reel]")).not.toBeNull());
        // la chaîne reste lisible, voix et transcription comprises
        fireEvent.click(screen.getByRole("tab", { name: "STT / LLM / TTS" }));
        expect(carte("tts").textContent).toContain("sonic-3.6");
        expect(carte("stt").textContent).toContain("Typed key");
    });

    it("un mode jamais réglé ne peut pas être activé, et un échec dit une phrase", async () => {
        render(<PageModelesEtCles />); // la configuration de base n'a que la chaîne
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        const bouton = document.querySelector("[data-activer-mode=temps-reel]") as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        expect(m.basculer).not.toHaveBeenCalled();
        // un échec du serveur
        m.lue = LES_DEUX("pipeline");
        cleanup();
        m.basculer.mockResolvedValue({ error: { detail: "boom interne" }, response: { status: 500 } });
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        fireEvent.click(await waitFor(() => document.querySelector("[data-activer-mode=temps-reel]") as HTMLElement));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(JSON.stringify(m.echec.mock.calls[0][0])).not.toContain("boom interne");
        expect(m.succes).not.toHaveBeenCalled();
    });

    it("enregistrer une brique du temps réel renvoie la chaîne et garde l'active", async () => {
        m.lue = LES_DEUX("pipeline");
        m.enregistrer.mockResolvedValue({ data: { configuration: m.lue, effective_configuration: {}, source: "organization" } });
        render(<PageModelesEtCles />);
        await waitFor(() => expect(carte("llm")).not.toBeNull());
        fireEvent.click(screen.getByRole("tab", { name: "Realtime" }));
        fireEvent.click(carte("llm"));
        fireEvent.click(within(screen.getByRole("dialog")).getByText("enregistrer"));
        await waitFor(() => expect(m.enregistrer).toHaveBeenCalled());
        const byok = m.enregistrer.mock.calls[0][0].body.byok;
        expect(byok.mode).toBe("pipeline"); // l'onglet affiché n'active rien
        expect(byok.pipeline.tts.provider).toBe("cartesia");
        expect(byok.pipeline.stt.api_key).toBe("****1234");
        expect(byok.realtime.llm.model).toBe("mistral-medium-2508");
    });
});
