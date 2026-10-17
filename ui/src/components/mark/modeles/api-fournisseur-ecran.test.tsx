/**
 * [.mark] Le champ « API » du fournisseur compatible OpenAI, à l'écran Modèles
 * (chantier orchestrateur-trois-cerveaux, lot 1, D11 et D19).
 *
 * Rendu avec le VRAI schéma du registre (`references/schemas-fournisseurs.json`, que
 * `api/tests/mark/test_schemas_ecran_modeles_a_jour.py` compare à celui de l'API) :
 *
 *   - le champ apparaît dans le sous-menu Technique du fournisseur, par le formulaire généré,
 *     avec son libellé en anglais puis en français et son nom technique ;
 *   - les deux choix sont proposés, `chat_completions` d'abord (le défaut) ;
 *   - sans y toucher, l'enregistrement envoie `chat_completions` : un agent existant ne change pas ;
 *   - choisir `responses` l'envoie, et rien d'autre ne bouge dans la charge.
 *
 * Capture Playwright : voir `etat.md` (le serveur d'écran local ne se lance pas sans base).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";

import { FournisseurLangue } from "../langue/langue";
import { commeEnvoye } from "../reglages-agent/references/jouer";

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));
vi.mock("@/components/ui/select", () => import("../reglages-agent/references/select-natif"));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => <input id="tts_voice" /> }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

type Schemas = Record<"llm" | "tts" | "stt", Record<string, { properties: Record<string, Record<string, unknown>> }>>;
const SCHEMAS = JSON.parse(
    readFileSync(join(process.cwd(), "src/components/mark/modeles/references/schemas-fournisseurs.json"), "utf8"),
) as Schemas;

const DEFAUTS = {
    llm: SCHEMAS.llm,
    tts: SCHEMAS.tts,
    stt: SCHEMAS.stt,
    embeddings: {},
    default_providers: { llm: "openai", tts: "elevenlabs", stt: "deepgram" },
} as unknown as ServiceConfigurationDefaults;

const MODELE = "openai/gpt-oss-120b:fp4";

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const ouvrir = async (enveloppe = false, api?: string) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const formulaire = (
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={DEFAUTS}
            initialConfig={{
                llm: {
                    provider: "openai",
                    model: MODELE,
                    base_url: "https://api.scaleway.ai/v1",
                    api_key: ["cle-llm"],
                    ...(api ? { api } : {}),
                },
                tts: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["cle-tts"] },
                stt: { provider: "deepgram", model: "nova-3-general", api_key: ["cle-stt"] },
            }}
            forceRealtime={false}
        />
    );
    render(enveloppe ? <FournisseurLangue>{formulaire}</FournisseurLangue> : formulaire);
    const onglet = await waitFor(() => screen.getByRole("tab", { name: /^llm$/i }));
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
    await waitFor(() => expect(document.querySelector('[data-sous-menu="llm.technique"]')).not.toBeNull());
    fireEvent.click(document.querySelector('[data-sous-menu="llm.technique"] > button') as HTMLButtonElement);
    return onSave;
};

const enregistrer = async (onSave: ReturnType<typeof vi.fn>) => {
    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    return commeEnvoye(onSave.mock.calls[0][0]) as Record<string, Record<string, unknown>>;
};

describe("[.mark] champ « API » du fournisseur compatible OpenAI", () => {
    it("is in the Technical sub-menu of the provider, with its two choices", async () => {
        await ouvrir();
        const champ = document.querySelector('[data-sous-menu="llm.technique"] [data-champ="api"]');
        expect(champ).not.toBeNull();
        expect(champ?.querySelector("[data-cle-technique]")?.textContent).toBe("api");
        const choix = document.querySelector('[data-champ="api"] select') as HTMLSelectElement;
        expect(Array.from(choix.options).map((o) => o.value)).toEqual(["chat_completions", "responses"]);
        expect(choix.value).toBe("chat_completions");
    });

    it("reads « API » in English and « Type d'API » in French", async () => {
        await ouvrir();
        expect(document.querySelector('[data-champ="api"]')?.textContent).toContain("API");
        cleanup();
        await ouvrir(true);
        expect(document.querySelector('[data-champ="api"]')?.textContent).toContain("Type d'API");
    });

    it("offers gpt-oss-120b among the models of the provider", () => {
        expect(SCHEMAS.llm.openai.properties.model.examples).toContain(MODELE);
    });

    it("sends chat_completions untouched, so an existing agent does not change", async () => {
        const charge = await enregistrer(await ouvrir());
        expect(charge.llm.api).toBe("chat_completions");
        expect(charge.llm.base_url).toBe("https://api.scaleway.ai/v1");
        expect(charge.llm.model).toBe(MODELE);
    });

    it("sends responses once chosen, and nothing else moves", async () => {
        const sans = await enregistrer(await ouvrir());
        cleanup();
        const onSave = await ouvrir();
        fireEvent.change(document.querySelector('[data-champ="api"] select') as HTMLSelectElement, { target: { value: "responses" } });
        const avec = await enregistrer(onSave);
        expect(avec.llm.api).toBe("responses");
        expect({ ...avec.llm, api: "chat_completions" }).toEqual(sans.llm);
        expect(avec.tts).toEqual(sans.tts);
        expect(avec.stt).toEqual(sans.stt);
    });

    it("keeps a saved responses choice when the screen opens again", async () => {
        await ouvrir(false, "responses");
        expect((document.querySelector('[data-champ="api"] select') as HTMLSelectElement).value).toBe("responses");
    });
});
