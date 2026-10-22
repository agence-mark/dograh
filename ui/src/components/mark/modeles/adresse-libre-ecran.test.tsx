/**
 * [.mark] La case « saisie libre » des adresses, sur l'écran Modèles (chantier
 * voix-soniox, lot 0 bis, D17), rendue avec les VRAIS schémas du registre
 * (`schemas-fournisseurs.json`, tenu à jour par
 * `api/tests/mark/test_schemas_ecran_modeles_a_jour.py`).
 *
 * Ce que ce fichier prouve, parce qu'un réglage déclaré n'est pas un réglage à
 * l'écran :
 * - la case est dessinée à côté de CHAQUE champ d'adresse, chez tous les
 *   fournisseurs rendus (cerveau, voix, transcription), sans code par fournisseur ;
 * - elle n'est pas un réglage de plus dans les sous-menus (le décompte du
 *   sous-menu ne bouge pas) ;
 * - libellé en deux langues, nom technique en gris (E5) ;
 * - décochée, l'enregistrement envoie EXACTEMENT ce qu'il envoyait avant (zéro
 *   perte) ; cochée, la clé part et revient cochée à la relecture ;
 * - une surcharge d'agent n'écrit la case que si elle change ce que le client a.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";

import { FournisseurLangue } from "../langue/langue";

const etat = vi.hoisted(() => ({ userConfig: null as Record<string, unknown> | null }));

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: etat.userConfig, refreshConfig: vi.fn() }),
}));
vi.mock("@/components/ui/select", () => import("../reglages-agent/references/select-natif"));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => <input id="tts_voice" /> }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

type Schemas = Record<"llm" | "tts" | "stt", Record<string, { properties: Record<string, Record<string, unknown>> }>>;
const SCHEMAS = JSON.parse(
    readFileSync(join(process.cwd(), "src/components/mark/modeles/references/schemas-fournisseurs.json"), "utf8"),
) as Schemas;

const ADRESSE_LIBRE = "https://proxy.example.net/soniox";
const CONFIG_STT = { provider: "soniox", model: "stt-rt-v5", language: "fr", api_key: ["k"] };

afterEach(() => {
    cleanup();
    window.localStorage.clear();
    etat.userConfig = null;
});

const ouvrir = async (
    options: {
        service?: "llm" | "tts" | "stt";
        onglet?: RegExp;
        config?: Record<string, unknown>;
        mode?: "global" | "override";
        organisation?: Record<string, unknown>;
        surcharge?: Record<string, unknown>;
        enveloppe?: (n: ReactNode) => ReactNode;
    } = {},
) => {
    const service = options.service ?? "stt";
    const onSave = vi.fn().mockResolvedValue(undefined);
    const config = {
        llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] },
        tts: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["k"] },
        stt: CONFIG_STT,
        [service]: options.config ?? (service === "stt" ? CONFIG_STT : undefined),
    };
    if (options.organisation) etat.userConfig = { ...config, ...options.organisation };
    const formulaire = (
        <ServiceConfigurationForm
            mode={options.mode ?? "global"}
            onSave={onSave}
            currentOverrides={options.surcharge as never}
            configurationDefaults={
                {
                    llm: SCHEMAS.llm,
                    tts: SCHEMAS.tts,
                    stt: SCHEMAS.stt,
                    embeddings: {},
                    default_providers: { llm: "mistral", tts: "elevenlabs", stt: "deepgram" },
                } as unknown as ServiceConfigurationDefaults
            }
            initialConfig={config}
            forceRealtime={false}
        />
    );
    render(<>{options.enveloppe ? options.enveloppe(formulaire) : formulaire}</>);
    const onglet = await waitFor(() =>
        screen.getByRole("tab", { name: options.onglet ?? /transcri/i }),
    );
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
    await waitFor(() => expect(document.querySelectorAll("[data-champ]").length).toBeGreaterThan(0));
    return onSave;
};

const ouvrirLesSousMenus = () => {
    for (const bouton of document.querySelectorAll<HTMLButtonElement>('[data-sous-menu] > button[aria-expanded="false"]')) {
        fireEvent.click(bouton);
    }
};
const laCase = (service = "stt") =>
    document.querySelector(`[data-adresse-libre="${service}"] [role="checkbox"]`) as HTMLButtonElement | null;
const estCochee = (service = "stt") => laCase(service)?.getAttribute("aria-checked") === "true";
const enregistrer = () => fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
const charge = (onSave: ReturnType<typeof vi.fn>, service = "stt") =>
    (onSave.mock.calls[0][0] as Record<string, Record<string, unknown>>)[service];

describe("[.mark] la case « saisie libre » des adresses", () => {
    it.each([
        { id: "Soniox (transcription)", service: "stt", onglet: /transcri/i, config: CONFIG_STT },
        { id: "Deepgram (transcription)", service: "stt", onglet: /transcri/i, config: { provider: "deepgram", model: "nova-3-general", language: "fr", api_key: ["k"] } },
        { id: "ElevenLabs (voix)", service: "tts", onglet: /^voice$/i, config: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["k"] } },
        { id: "Mistral (cerveau)", service: "llm", onglet: /^llm$/i, config: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] } },
        { id: "OpenAI (cerveau)", service: "llm", onglet: /^llm$/i, config: { provider: "openai", model: "gpt-4.1", api_key: ["k"] } },
    ] as const)("est dessinée à côté de l'adresse de $id, décochée", async ({ service, onglet, config }) => {
        await ouvrir({ service, onglet, config });
        ouvrirLesSousMenus();
        const cases = document.querySelectorAll(`[data-adresse-libre="${service}"]`);
        expect(cases.length).toBe(1);
        // À côté du champ d'adresse, dans le même bloc, jamais comme un réglage de la liste.
        const champ = cases[0].closest("[data-champ]") as HTMLElement | null;
        expect(champ?.getAttribute("data-champ")).toBe("base_url");
        expect(document.querySelector('[data-champ="adresse_libre"]')).toBeNull();
        expect(laCase(service)).not.toBeNull();
        expect(estCochee(service)).toBe(false);
    });

    it("ne change pas le décompte des réglages du sous-menu Hébergement de Soniox", async () => {
        await ouvrir();
        const sousMenu = document.querySelector('[data-sous-menu="stt.hebergement"]') as HTMLElement;
        expect(sousMenu.textContent).toMatch(/2\s+(settings|réglages)/);
        ouvrirLesSousMenus();
        const champs = Array.from(sousMenu.querySelectorAll("[data-champ]")).map((c) => c.getAttribute("data-champ"));
        expect(champs).toEqual(["base_url", "region"]);
    });

    it("affiche le libellé dans les deux langues, avec le nom technique en gris", async () => {
        await ouvrir({ enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        ouvrirLesSousMenus();
        const bloc = document.querySelector('[data-adresse-libre="stt"]') as HTMLElement;
        expect(bloc.textContent).toMatch(/Saisie libre/);
        expect(bloc.querySelector("[data-cle-technique]")?.textContent).toBe("adresse_libre");
        const libelle = SCHEMAS.stt.soniox.properties.adresse_libre.mark_libelle as { en: string; fr: string };
        expect(libelle.en).toBeTruthy();
        expect(libelle.fr).toBeTruthy();
    });

    it("n'envoie rien de plus qu'avant quand elle reste décochée (zéro perte)", async () => {
        const onSave = await ouvrir();
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect("adresse_libre" in charge(onSave)).toBe(false);
    });

    it("envoie la clé cochée, avec l'adresse tapée, et l'enlève une fois décochée", async () => {
        // Une adresse hors de la liste proposée : le champ est déjà en saisie libre de valeur.
        const onSave = await ouvrir({ config: { ...CONFIG_STT, base_url: ADRESSE_LIBRE } });
        ouvrirLesSousMenus();
        expect(estCochee()).toBe(false);
        fireEvent.click(laCase() as HTMLButtonElement);
        await waitFor(() => expect(estCochee()).toBe(true));
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(charge(onSave).adresse_libre).toBe(true);
        expect(charge(onSave).base_url).toBe(ADRESSE_LIBRE);

        fireEvent.click(laCase() as HTMLButtonElement);
        await waitFor(() => expect(estCochee()).toBe(false));
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(2));
        expect("adresse_libre" in (onSave.mock.calls[1][0] as Record<string, Record<string, unknown>>).stt).toBe(false);
    });

    it("revient cochée d'une configuration enregistrée cochée, et se réenregistre cochée", async () => {
        const onSave = await ouvrir({
            config: { ...CONFIG_STT, base_url: ADRESSE_LIBRE, adresse_libre: true },
        });
        ouvrirLesSousMenus();
        expect(estCochee()).toBe(true);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(charge(onSave).adresse_libre).toBe(true);
        expect(charge(onSave).base_url).toBe(ADRESSE_LIBRE);
    });
});

describe("[.mark] la case dans la surcharge d'un agent", () => {
    const organisation = (adresse_libre: boolean) => ({
        stt: { ...CONFIG_STT, ...(adresse_libre ? { base_url: ADRESSE_LIBRE, adresse_libre: true } : {}) },
    });

    it("n'écrit pas la case quand l'agent ne la change pas", async () => {
        const onSave = await ouvrir({
            mode: "override",
            organisation: organisation(false),
            surcharge: { stt: { ...CONFIG_STT, endpoint_detection: false } },
            config: { ...CONFIG_STT, endpoint_detection: false },
        });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const surcharges = (onSave.mock.calls[0][0] as { model_overrides?: Record<string, Record<string, unknown>> }).model_overrides;
        expect(surcharges?.stt).toBeDefined();
        expect("adresse_libre" in (surcharges?.stt ?? {})).toBe(false);
    });

    it("écrit « décochée » quand l'agent retire ce que le client a coché", async () => {
        const onSave = await ouvrir({
            mode: "override",
            organisation: organisation(true),
            surcharge: { stt: { ...CONFIG_STT, base_url: ADRESSE_LIBRE, adresse_libre: true } },
            config: { ...CONFIG_STT, base_url: ADRESSE_LIBRE, adresse_libre: true },
        });
        ouvrirLesSousMenus();
        expect(estCochee()).toBe(true);
        fireEvent.click(laCase() as HTMLButtonElement);
        await waitFor(() => expect(estCochee()).toBe(false));
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const surcharges = (onSave.mock.calls[0][0] as { model_overrides?: Record<string, Record<string, unknown>> }).model_overrides;
        expect(surcharges?.stt?.adresse_libre).toBe(false);
    });
});
