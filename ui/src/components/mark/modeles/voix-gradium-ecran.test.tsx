/**
 * [.mark] Lot GT (builder partie 3) : la voix Gradium sur l'écran Modèles, rendue avec le VRAI schéma du registre
 * (`schemas-fournisseurs.json`, tenu à jour par `api/tests/mark/test_schemas_ecran_modeles_a_jour.py`).
 *
 * Un réglage déclaré n'est pas un réglage à l'écran (18-ajout-fournisseur, 7 (3)) : ce fichier rend le composant et
 * prouve que chacun des huit réglages de la voix est dessiné, nommé en français, borné, et part dans l'enregistrement.
 * - le menu des voix dit Romane et Gaspard par leur nom, l'identifiant reste saisissable ;
 * - la vitesse s'écrit en facteur (« × ») et ne part que renseignée ; la température part avec son défaut documenté ;
 * - la région suit l'adresse et ne se tape pas ; la bulle du choix dit les conditions du fournisseur en deux langues ;
 * - une voix existante (ElevenLabs) n'a ni « × » ni nom de valeur de plus : rien ne change pour elle.
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

type Schema = { properties: Record<string, Record<string, unknown>> };
type Schemas = Record<"llm" | "tts" | "stt", Record<string, Schema>>;
const SCHEMAS = JSON.parse(
    readFileSync(join(process.cwd(), "src/components/mark/modeles/references/schemas-fournisseurs.json"), "utf8"),
) as Schemas;

const ROMANE = "jBULVCDhf05tOJN5";
const CONFIG_GRADIUM = { provider: "gradium", model: "default", voice: ROMANE, api_key: ["cle-gradium"] };
const CONFIG_ELEVENLABS = { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["cle-eleven"] };
const CHAMPS = ["voice", "speed", "temp", "rewrite_rules", "pronunciation_id", "output_format", "base_url", "region"];

afterEach(() => {
    cleanup();
    window.localStorage.clear();
    etat.userConfig = null;
});

const ouvrir = async (config: Record<string, unknown>, options: { enveloppe?: (n: ReactNode) => ReactNode } = {}) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const toutes = {
        llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] },
        tts: config,
        stt: { provider: "deepgram", model: "nova-3-general", language: "fr", api_key: ["k"] },
    };
    const formulaire = (
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={
                {
                    llm: SCHEMAS.llm,
                    tts: SCHEMAS.tts,
                    stt: SCHEMAS.stt,
                    embeddings: {},
                    default_providers: { llm: "mistral", tts: "elevenlabs", stt: "deepgram" },
                } as unknown as ServiceConfigurationDefaults
            }
            initialConfig={toutes}
            forceRealtime={false}
        />
    );
    render(<>{options.enveloppe ? options.enveloppe(formulaire) : formulaire}</>);
    const onglet = await waitFor(() => screen.getByRole("tab", { name: /^(voice|voix)$/i }));
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
const enregistrer = () => fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
const chargeTts = (onSave: ReturnType<typeof vi.fn>) =>
    (onSave.mock.calls[0][0] as Record<string, Record<string, unknown>>).tts;
const texte = (champ: string) => (document.querySelector(`[data-champ="${champ}"]`) as HTMLElement | null)?.textContent ?? "";

describe("[.mark] la voix Gradium à l'écran (lot GT)", () => {
    it("dessine ses huit réglages, chacun avec son libellé français et son nom technique", async () => {
        await ouvrir(CONFIG_GRADIUM, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        ouvrirLesSousMenus();
        for (const champ of CHAMPS) {
            const bloc = document.querySelector(`[data-champ="${champ}"]`);
            expect(bloc, champ).not.toBeNull();
            expect(bloc?.querySelector("[data-cle-technique]")?.textContent, champ).toBe(champ);
        }
        expect(texte("speed")).toMatch(/Vitesse \(facteur\)/);
        expect(texte("temp")).toMatch(/Température/);
        expect(texte("rewrite_rules")).toMatch(/Réécriture du texte/);
        expect(texte("pronunciation_id")).toMatch(/Dictionnaire de prononciation/);
        expect(texte("output_format")).toMatch(/Format du son/);
        expect(texte("region")).toMatch(/Région/);
    });

    it("le menu des voix nomme Romane et Gaspard, l'identifiant reste saisissable", async () => {
        await ouvrir(CONFIG_GRADIUM, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        ouvrirLesSousMenus();
        const options = Array.from(document.querySelectorAll('[data-champ="voice"] option')).map((o) => o.textContent ?? "");
        expect(options.some((o) => /Romane \(voix féminine\)/.test(o))).toBe(true);
        expect(options.some((o) => /Gaspard \(voix masculine\)/.test(o))).toBe(true);
        expect(screen.getAllByText(/Enter Custom Value/i).length).toBeGreaterThan(0);
    });

    it("la vitesse est écrite en facteur : le signe × précède la case, bornée de 0,5 à 2", async () => {
        await ouvrir(CONFIG_GRADIUM);
        ouvrirLesSousMenus();
        const facteur = document.querySelector('[data-facteur="tts_speed"]') as HTMLElement;
        expect(facteur.textContent).toContain("×");
        const saisie = facteur.querySelector("input") as HTMLInputElement;
        expect(saisie.min).toBe("0.5");
        expect(saisie.max).toBe("2");
        expect(document.querySelector('[data-facteur="tts_temp"]')).toBeNull();
    });

    it("enregistrer sans rien toucher n'envoie ni vitesse ni dictionnaire, et envoie les défauts documentés", async () => {
        const onSave = await ouvrir(CONFIG_GRADIUM);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        expect(tts.provider).toBe("gradium");
        expect(tts.voice).toBe(ROMANE);
        expect(tts.temp).toBe(0.7);
        expect(tts.rewrite_rules).toBe("fr");
        expect("speed" in tts).toBe(false);
        expect("pronunciation_id" in tts).toBe(false);
    });

    it("envoie la vitesse, la température et le dictionnaire réglés à l'écran", async () => {
        const onSave = await ouvrir(CONFIG_GRADIUM);
        ouvrirLesSousMenus();
        fireEvent.change(screen.getByPlaceholderText("Enter speed"), { target: { value: "1.2" } });
        fireEvent.change(screen.getByPlaceholderText("Enter temp"), { target: { value: "0.4" } });
        fireEvent.change(document.querySelector('[data-champ="pronunciation_id"] input') as HTMLInputElement, { target: { value: "bb1ckYhNHCcIJjdK" } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        expect(tts.speed).toBe(1.2);
        expect(tts.temp).toBe(0.4);
        expect(tts.pronunciation_id).toBe("bb1ckYhNHCcIJjdK");
    });

    it("la région est montrée sans pouvoir être tapée (Europe par défaut)", async () => {
        await ouvrir(CONFIG_GRADIUM);
        ouvrirLesSousMenus();
        const region = document.querySelector('[data-champ="region"] input') as HTMLInputElement;
        expect(region.value).toBe("eu");
        expect(region.readOnly || region.disabled).toBe(true);
    });

    it("la bulle du choix dit les conditions du fournisseur, en français", async () => {
        await ouvrir(CONFIG_GRADIUM, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        const bulle = Array.from(document.querySelectorAll("p")).find((p) => /conservation/i.test(p.textContent ?? ""));
        expect(bulle?.textContent).toMatch(/Résidence UE/);
        expect(bulle?.textContent).toMatch(/zéro conservation/);
        expect(bulle?.textContent).toMatch(/300 secondes/);
    });

    it("une voix existante n'a ni facteur ni réglage Gradium de plus", async () => {
        await ouvrir(CONFIG_ELEVENLABS);
        ouvrirLesSousMenus();
        expect(document.querySelector("[data-facteur]")).toBeNull();
        expect(document.querySelector('[data-champ="rewrite_rules"]')).toBeNull();
    });
});
