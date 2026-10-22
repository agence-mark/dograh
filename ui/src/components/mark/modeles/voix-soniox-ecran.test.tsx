/**
 * [.mark] La voix Soniox et les réglages de la voix ElevenLabs sur l'écran Modèles (chantier voix-soniox, lots 7 et
 * 7 bis), rendus avec les VRAIS schémas du registre (`schemas-fournisseurs.json`, tenu à jour par
 * `api/tests/mark/test_schemas_ecran_modeles_a_jour.py`), à l'organisation ET dans la surcharge d'un agent.
 *
 * Ce que ce fichier prouve, parce qu'un réglage déclaré n'est pas un réglage à l'écran (condition de sortie 3) :
 * - la voix Soniox est dessinée, ses réglages rangés en sous-menus (voix, débit, hébergement) avec le mode d'envoi du
 *   texte à plat, libellés dans les deux langues, nom technique en gris ;
 * - la liste des voix est une CARTE qui ouvre une MODALE centrée : filtre « français », recherche, Mathieu, Celine,
 *   Julien en tête, saisie libre pour une voix absente ou clonée, Annuler qui ne change rien ;
 * - la modale ne promet pas ce qu'elle n'a pas : elle dit combien de voix elle porte, de quand, et que Soniox en a
 *   environ 200 ;
 * - enregistrer sans rien toucher renvoie chaque clé telle quelle (aller-retour, clé de l'API comprise) ;
 * - ElevenLabs : stabilité, ressemblance, style et renfort du locuteur sont des champs du bloc voix, vides par défaut
 *   (rien de nouveau n'est envoyé), et partent quand on les règle.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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

const VOIX_SONIOX = SCHEMAS.tts.soniox.properties.voice.mark_voix as Array<{ id: string; francais: boolean }>;
const CONFIG_SONIOX = { provider: "soniox", model: "tts-rt-v2", voice: "Mathieu", language: "fr", api_key: ["cle-voix"] };
const CONFIG_ELEVENLABS = { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["cle-eleven"] };

/** Les schémas avec une voix qui n'est pas française de plus : de quoi prouver le filtre. */
const schemasAvecUneVoixAnglaise = (): Schemas => {
    const copie = JSON.parse(JSON.stringify(SCHEMAS)) as Schemas;
    const voix = copie.tts.soniox.properties.voice;
    (voix.mark_voix as unknown[]).push({ id: "Bryce", francais: false, accent: "États-Unis", genre: null, description: "voix anglaise d'essai" });
    (voix.examples as string[]).push("Bryce");
    return copie;
};

afterEach(() => {
    cleanup();
    window.localStorage.clear();
    etat.userConfig = null;
});

const ouvrir = async (
    config: Record<string, unknown>,
    options: {
        mode?: "global" | "override";
        surcharge?: Record<string, unknown>;
        schemas?: Schemas;
        enveloppe?: (n: ReactNode) => ReactNode;
    } = {},
) => {
    const schemas = options.schemas ?? SCHEMAS;
    const onSave = vi.fn().mockResolvedValue(undefined);
    const toutes = {
        llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["k"] },
        tts: config,
        stt: { provider: "deepgram", model: "nova-3-general", language: "fr", api_key: ["k"] },
    };
    if (options.mode === "override") etat.userConfig = { ...toutes, tts: { ...CONFIG_ELEVENLABS } };
    const formulaire = (
        <ServiceConfigurationForm
            mode={options.mode ?? "global"}
            onSave={onSave}
            currentOverrides={options.surcharge as never}
            configurationDefaults={
                {
                    llm: schemas.llm,
                    tts: schemas.tts,
                    stt: schemas.stt,
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

const sousMenus = () => Array.from(document.querySelectorAll("[data-sous-menu]")).map((m) => m.getAttribute("data-sous-menu"));
const ouvrirSousMenu = (id: string) =>
    fireEvent.click(document.querySelector(`[data-sous-menu="${id}"] > button`) as HTMLButtonElement);
const ouvrirLesSousMenus = () => {
    for (const bouton of document.querySelectorAll<HTMLButtonElement>('[data-sous-menu] > button[aria-expanded="false"]')) {
        fireEvent.click(bouton);
    }
};
const champsDe = (id: string) =>
    Array.from(document.querySelectorAll(`[data-sous-menu="${id}"] [data-champ]`)).map((c) => c.getAttribute("data-champ"));
const enregistrer = () => fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
const chargeTts = (onSave: ReturnType<typeof vi.fn>, appel = 0) =>
    (onSave.mock.calls[appel][0] as Record<string, Record<string, unknown>>).tts;
const chargeSurcharge = (onSave: ReturnType<typeof vi.fn>) =>
    (onSave.mock.calls[0][0] as { model_overrides?: Record<string, Record<string, unknown>> }).model_overrides?.tts;

const carte = () => document.querySelector("[data-carte-voix]") as HTMLElement;
const voixDeLaModale = () => Array.from(document.querySelectorAll("[data-liste-voix] [data-voix]")).map((v) => v.getAttribute("data-voix"));
const ouvrirLaModale = () => {
    fireEvent.click(carte());
    return screen.getByRole("dialog");
};

describe("[.mark] la voix Soniox sur l'écran Modèles (organisation)", () => {
    it("range ses réglages en sous-menus, le mode d'envoi du texte à plat", async () => {
        await ouvrir(CONFIG_SONIOX);
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["tts.voix", "tts.debit", "tts.hebergement"]);
        ouvrirLesSousMenus();
        expect(champsDe("tts.voix")).toEqual(["voice", "language"]);
        expect(champsDe("tts.debit")).toEqual(["speed", "reduce_silence"]);
        expect(champsDe("tts.hebergement")).toEqual(["base_url", "region"]);
        const envoi = document.querySelector('[data-champ="text_aggregation_mode"]');
        expect(envoi).not.toBeNull();
        expect(envoi?.closest("[data-sous-menu]")).toBeNull();
        // Le modèle en tête, hors sous-menu.
        expect(document.querySelector('[data-champ="model"]')?.closest("[data-sous-menu]")).toBeNull();
    });

    it("titre les groupes dans les deux langues, avec le nom technique en gris", async () => {
        await ouvrir(CONFIG_SONIOX, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus()).toContain("tts.debit"));
        expect(document.querySelector('[data-sous-menu="tts.debit"]')?.textContent).toMatch(/D(é|e)bit/);
        ouvrirLesSousMenus();
        const vitesse = document.querySelector('[data-champ="speed"]') as HTMLElement;
        expect(vitesse.textContent).toMatch(/Vitesse/);
        expect(vitesse.querySelector("[data-cle-technique]")?.textContent).toBe("speed");
        const envoi = document.querySelector('[data-champ="text_aggregation_mode"]') as HTMLElement;
        expect(envoi.textContent).toMatch(/Envoi du texte/);
        expect(envoi.querySelector("[data-cle-technique]")?.textContent).toBe("text_aggregation_mode");
    });

    it("dessine la voix en carte (pas en liste déroulante), avec la voix retenue", async () => {
        await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        expect(carte()).not.toBeNull();
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("Mathieu");
        expect(carte().textContent).toMatch(/French|Français/);
        // Ni la liste déroulante des exemples, ni la case « saisie libre » de valeur : la modale s'en charge.
        expect(document.querySelector('[data-champ="voice"] [role="combobox"]')).toBeNull();
        expect(document.querySelector("#custom-input-tts_voice-dropdown")).toBeNull();
    });

    it("ouvre une modale centrée, Mathieu, Celine et Julien en tête", async () => {
        await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        const modale = ouvrirLaModale();
        expect(modale.getAttribute("data-modale-phrase")).toBe("voix");
        expect(voixDeLaModale().slice(0, 3)).toEqual(["Mathieu", "Celine", "Julien"]);
        expect(voixDeLaModale()).toHaveLength(VOIX_SONIOX.length);
        // Les 11 françaises connues du produit, pas plus.
        expect(VOIX_SONIOX.every((v) => v.francais)).toBe(true);
        expect(VOIX_SONIOX).toHaveLength(11);
    });

    it("dit combien de voix elle porte et de quand, sans promettre les 200 de Soniox", async () => {
        await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        const notice = (document.querySelector("[data-notice-voix]") as HTMLElement).textContent ?? "";
        expect(notice).toContain(`${VOIX_SONIOX.length}`);
        expect(notice).toContain(SCHEMAS.tts.soniox.properties.voice.mark_voix_releve as string);
        expect(notice).toMatch(/about 200|environ 200/);
        // La liste affichée est bien celle annoncée : pas une de plus.
        expect(voixDeLaModale().length).toBe(VOIX_SONIOX.length);
    });

    it("filtre « français », cherche, et dit quand rien ne correspond", async () => {
        await ouvrir(CONFIG_SONIOX, { schemas: schemasAvecUneVoixAnglaise() });
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        // Filtre allumé d'office : la voix anglaise n'y est pas.
        expect(voixDeLaModale()).not.toContain("Bryce");
        const filtre = document.getElementById("tts_voice-francais") as HTMLElement;
        expect(filtre.getAttribute("aria-checked")).toBe("true");
        fireEvent.click(filtre);
        await waitFor(() => expect(voixDeLaModale()).toContain("Bryce"));
        fireEvent.click(filtre);
        await waitFor(() => expect(voixDeLaModale()).not.toContain("Bryce"));

        const recherche = document.getElementById("tts_voice-recherche") as HTMLInputElement;
        fireEvent.change(recherche, { target: { value: "celine" } });
        await waitFor(() => expect(voixDeLaModale()).toEqual(["Celine"]));
        // Sans accent ni casse.
        fireEvent.change(recherche, { target: { value: "ÉLODIE" } });
        await waitFor(() => expect(voixDeLaModale()).toEqual(["Elodie"]));
        fireEvent.change(recherche, { target: { value: "zzz" } });
        await waitFor(() => expect(voixDeLaModale()).toEqual([]));
        expect(document.querySelector("[data-liste-voix]")?.textContent).toMatch(/No known voice|Aucune voix connue/);
    });

    it("choisit une voix de la liste et l'enregistre", async () => {
        const onSave = await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        fireEvent.click(document.querySelector('[data-voix="Julien"]') as HTMLElement);
        expect(document.querySelector('[data-voix="Julien"]')?.getAttribute("aria-selected")).toBe("true");
        fireEvent.click(screen.getByRole("button", { name: /use this voice/i }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("Julien");
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).voice).toBe("Julien");
    });

    it("Annuler ne change rien", async () => {
        const onSave = await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        fireEvent.click(document.querySelector('[data-voix="Olivier"]') as HTMLElement);
        fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("Mathieu");
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).voice).toBe("Mathieu");
    });

    it("accepte une voix absente de la liste (ou clonée) par la saisie libre", async () => {
        const onSave = await ouvrir(CONFIG_SONIOX);
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        fireEvent.change(document.getElementById("tts_voice-saisie-libre") as HTMLInputElement, { target: { value: "voix-clonee-42" } });
        // Aucune voix de la liste n'est plus marquée choisie.
        expect(document.querySelector('[data-liste-voix] [aria-selected="true"]')).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: /use this voice/i }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("voix-clonee-42");
        expect(carte().textContent).toMatch(/Typed by hand|Saisie à la main/);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).voice).toBe("voix-clonee-42");
    });

    it("rouvre une voix saisie à la main dans la saisie libre, sans la perdre", async () => {
        const onSave = await ouvrir({ ...CONFIG_SONIOX, voice: "voix-clonee-42" });
        ouvrirSousMenu("tts.voix");
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("voix-clonee-42");
        ouvrirLaModale();
        expect((document.getElementById("tts_voice-saisie-libre") as HTMLInputElement).value).toBe("voix-clonee-42");
        fireEvent.click(screen.getByRole("button", { name: /use this voice/i }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).voice).toBe("voix-clonee-42");
    });

    it("la modale a ses textes en français quand l'écran est en français", async () => {
        await ouvrir(CONFIG_SONIOX, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        ouvrirSousMenu("tts.voix");
        const modale = ouvrirLaModale();
        expect(within(modale).getByText("Choisir la voix")).toBeTruthy();
        expect(modale.textContent).toMatch(/Français seulement/);
        expect(modale.textContent).toMatch(/Voix absente de la liste, ou voix clonée/);
    });

    it("renvoie chaque clé telle quelle quand on enregistre sans rien toucher (aller-retour)", async () => {
        const complete = {
            ...CONFIG_SONIOX,
            voice: "Celine",
            speed: 1.1,
            reduce_silence: true,
            text_aggregation_mode: "token",
            base_url: "wss://tts-rt.eu.soniox.com/tts-websocket",
        };
        const onSave = await ouvrir(complete);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        const tts = chargeTts(onSave);
        for (const [cle, valeur] of Object.entries(complete)) {
            expect(tts[cle], cle).toEqual(valeur);
        }
    });

    it("n'envoie ni vitesse ni silences quand rien n'est réglé (défaut Soniox)", async () => {
        const onSave = await ouvrir(CONFIG_SONIOX);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        expect("speed" in tts).toBe(false);
        expect("reduce_silence" in tts).toBe(false);
        expect("adresse_libre" in tts).toBe(false);
    });
});

describe("[.mark] la voix Soniox dans la surcharge d'un agent", () => {
    const surcharge = { tts: { ...CONFIG_SONIOX, voice: "Celine" } };

    it("dessine les mêmes sous-menus et la même carte", async () => {
        await ouvrir(CONFIG_SONIOX, { mode: "override", surcharge });
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["tts.voix", "tts.debit", "tts.hebergement"]);
        ouvrirSousMenu("tts.voix");
        expect(carte().querySelector("[data-voix-retenue]")?.textContent).toBe("Celine");
    });

    it("écrit la voix choisie dans la surcharge de l'agent, saisie libre comprise", async () => {
        const onSave = await ouvrir(CONFIG_SONIOX, { mode: "override", surcharge });
        ouvrirSousMenu("tts.voix");
        ouvrirLaModale();
        fireEvent.change(document.getElementById("tts_voice-saisie-libre") as HTMLInputElement, { target: { value: "voix-agent" } });
        fireEvent.click(screen.getByRole("button", { name: /use this voice/i }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeSurcharge(onSave)?.voice).toBe("voix-agent");
        expect(chargeSurcharge(onSave)?.provider).toBe("soniox");
    });

    it("aller-retour : la surcharge enregistrée sans rien toucher garde ses clés", async () => {
        const complete = { ...CONFIG_SONIOX, voice: "Julien", speed: 0.9, reduce_silence: false };
        const onSave = await ouvrir(complete, { mode: "override", surcharge: { tts: complete } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeSurcharge(onSave) ?? {};
        // La clé de l'API : une surcharge d'agent écrit UNE clé en chaîne (la première), pour tous les fournisseurs
        // (`buildServiceConfig`, mode « override ») ; ce n'est pas une perte propre à la voix.
        expect(tts.api_key).toBe("cle-voix");
        for (const [cle, valeur] of Object.entries(complete)) {
            if (cle === "api_key") continue;
            expect(tts[cle], cle).toEqual(valeur);
        }
    });
});

describe("[.mark] les réglages de la voix ElevenLabs (lot 7 bis)", () => {
    const CHAMPS = ["stability", "similarity_boost", "style", "use_speaker_boost"];

    it("range stabilité, ressemblance, style et renfort dans un sous-menu « Caractère de la voix »", async () => {
        await ouvrir(CONFIG_ELEVENLABS);
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        expect(sousMenus()).toEqual(["tts.voix", "tts.caractere_de_la_voix"]);
        ouvrirLesSousMenus();
        expect(champsDe("tts.caractere_de_la_voix")).toEqual(CHAMPS);
        expect(champsDe("tts.voix")).toEqual(["voice", "speed"]);
    });

    it("les libellés sont dans les deux langues, avec le nom technique en gris", async () => {
        await ouvrir(CONFIG_ELEVENLABS, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus()).toContain("tts.caractere_de_la_voix"));
        expect(document.querySelector('[data-sous-menu="tts.caractere_de_la_voix"]')?.textContent).toMatch(/Caractère de la voix/);
        ouvrirLesSousMenus();
        const stabilite = document.querySelector('[data-champ="stability"]') as HTMLElement;
        expect(stabilite.textContent).toMatch(/Stabilité/);
        expect(stabilite.querySelector("[data-cle-technique]")?.textContent).toBe("stability");
        for (const champ of CHAMPS) {
            const libelle = SCHEMAS.tts.elevenlabs.properties[champ].mark_libelle as { en: string; fr: string };
            expect(libelle.en && libelle.fr, champ).toBeTruthy();
        }
    });

    it("n'envoie rien de plus qu'avant quand les quatre restent vides (zéro perte)", async () => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        for (const champ of CHAMPS) expect(champ in tts, champ).toBe(false);
    });

    it.each([
        ["stability", "0.3", 0.3],
        ["similarity_boost", "0.9", 0.9],
        ["style", "0.4", 0.4],
    ])("envoie %s réglée à l'écran", async (champ, saisie, attendu) => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS);
        ouvrirLesSousMenus();
        fireEvent.change(screen.getByPlaceholderText(`Enter ${champ}`), { target: { value: saisie } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        expect(tts[champ]).toBe(attendu);
        for (const autre of CHAMPS.filter((c) => c !== champ)) expect(autre in tts, autre).toBe(false);
    });

    it("envoie le renfort du locuteur quand on l'allume", async () => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS);
        ouvrirLesSousMenus();
        fireEvent.click(document.getElementById("tts_use_speaker_boost") as HTMLElement);
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).use_speaker_boost).toBe(true);
    });

    it("zéro est une valeur : 0 part, il n'est pas lu comme un champ vide", async () => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS);
        ouvrirLesSousMenus();
        fireEvent.change(screen.getByPlaceholderText("Enter style"), { target: { value: "0" } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).style).toBe(0);
    });

    it("aller-retour : une configuration réglée revient identique", async () => {
        const reglee = { ...CONFIG_ELEVENLABS, stability: 0.5, similarity_boost: 0.6, style: 0.2, use_speaker_boost: true };
        const onSave = await ouvrir(reglee);
        ouvrirLesSousMenus();
        expect((screen.getByPlaceholderText("Enter stability") as HTMLInputElement).value).toBe("0.5");
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const tts = chargeTts(onSave);
        for (const champ of CHAMPS) expect(tts[champ], champ).toEqual((reglee as Record<string, unknown>)[champ]);
    });

    it("dans la surcharge d'un agent, les quatre champs sont là et partent", async () => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS, { mode: "override", surcharge: { tts: CONFIG_ELEVENLABS } });
        await waitFor(() => expect(sousMenus()).toContain("tts.caractere_de_la_voix"));
        ouvrirLesSousMenus();
        expect(champsDe("tts.caractere_de_la_voix")).toEqual(CHAMPS);
        fireEvent.change(screen.getByPlaceholderText("Enter stability"), { target: { value: "0.35" } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeSurcharge(onSave)?.stability).toBe(0.35);
    });
});

describe("[.mark] les textes des champs de la voix, en français comme en anglais (D-52)", () => {
    const aide = (champ: string) => (document.querySelector(`[data-champ="${champ}"]`) as HTMLElement).textContent ?? "";

    it("en français, la voix Soniox n'a plus d'aide, d'indication ni de valeur de menu en anglais", async () => {
        await ouvrir(CONFIG_SONIOX, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        ouvrirLesSousMenus();
        expect(aide("speed")).toMatch(/Multiplicateur de débit/);
        expect(aide("speed")).not.toMatch(/Speech rate multiplier/);
        expect(aide("reduce_silence")).toMatch(/Raccourcit les pauses/);
        expect(aide("text_aggregation_mode")).toMatch(/phrase par phrase/);
        expect(aide("base_url")).toMatch(/juridiction/);
        expect(aide("region")).toMatch(/Déduite de l'adresse/);
        expect(screen.getByPlaceholderText("Saisissez : vitesse")).toBeTruthy();
        const options = Array.from(document.querySelectorAll('[data-champ="text_aggregation_mode"] option')).map((o) => o.textContent);
        expect(options).toEqual(["Phrase par phrase", "Mot par mot"]);
    });

    it("en anglais, l'aide est la description de l'api et les valeurs du menu sont nommées", async () => {
        await ouvrir(CONFIG_SONIOX);
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        ouvrirLesSousMenus();
        expect(aide("speed")).toContain(SCHEMAS.tts.soniox.properties.speed.description as string);
        const options = Array.from(document.querySelectorAll('[data-champ="text_aggregation_mode"] option')).map((o) => o.textContent);
        expect(options).toEqual(["Sentence by sentence", "Word by word"]);
        expect(screen.getByPlaceholderText("Enter speed")).toBeTruthy();
    });

    it("en français, les aides d'ElevenLabs aussi, anciennes et nouvelles", async () => {
        await ouvrir(CONFIG_ELEVENLABS, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        await waitFor(() => expect(sousMenus().length).toBeGreaterThan(0));
        ouvrirLesSousMenus();
        expect(aide("speed")).toMatch(/Vitesse de la voix/);
        expect(aide("stability")).toMatch(/Stabilité de la voix/);
        expect(aide("use_speaker_boost")).toMatch(/Renforce la ressemblance/);
        expect(aide("stability")).not.toMatch(/Voice stability/);
    });
});

describe("[.mark] la case « saisie libre » se distingue de « valeur personnalisée » (D-53)", () => {
    it("dit en deux langues qu'elle accepte tout schéma d'adresse, sous la case, sans case de plus", async () => {
        await ouvrir(CONFIG_SONIOX, { enveloppe: (n) => <FournisseurLangue>{n}</FournisseurLangue> });
        ouvrirSousMenu("tts.hebergement");
        const bloc = document.querySelector('[data-adresse-libre="tts"]') as HTMLElement;
        expect(bloc.textContent).toMatch(/Saisie libre \(tout schéma d'adresse\)/);
        const aideCase = document.querySelector('[data-aide-adresse-libre="tts"]') as HTMLElement;
        expect(aideCase.textContent).toMatch(/wss:\/\//);
        expect(aideCase.textContent).toMatch(/Saisir une valeur personnalisée/);
        // Toujours une seule case « saisie libre » par service, et la case de l'amont n'est pas touchée.
        expect(document.querySelectorAll('[data-adresse-libre="tts"]').length).toBe(1);
    });
});

describe("[.mark] revenir à « vide » sur un interrupteur facultatif (D-54)", () => {
    it("dit « vide » tant qu'il n'est pas réglé, puis propose de revenir à la valeur par défaut", async () => {
        const onSave = await ouvrir(CONFIG_ELEVENLABS);
        ouvrirLesSousMenus();
        expect(document.querySelector('[data-valeur-vide="tts_use_speaker_boost"]')).not.toBeNull();
        expect(document.querySelector('[data-valeur-par-defaut="tts_use_speaker_boost"]')).toBeNull();

        fireEvent.click(document.getElementById("tts_use_speaker_boost") as HTMLElement);
        await waitFor(() => expect(document.querySelector('[data-valeur-par-defaut="tts_use_speaker_boost"]')).not.toBeNull());
        expect(document.querySelector('[data-valeur-vide="tts_use_speaker_boost"]')).toBeNull();

        fireEvent.click(document.querySelector('[data-valeur-par-defaut="tts_use_speaker_boost"]') as HTMLElement);
        await waitFor(() => expect(document.querySelector('[data-valeur-vide="tts_use_speaker_boost"]')).not.toBeNull());
        expect(document.getElementById("tts_use_speaker_boost")?.getAttribute("aria-checked")).toBe("false");
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        // Revenu à vide : la clé n'est pas écrite, exactement comme avant d'y toucher.
        expect("use_speaker_boost" in chargeTts(onSave)).toBe(false);
    });

    it("éteint à la main reste une valeur : `false` part", async () => {
        const onSave = await ouvrir({ ...CONFIG_ELEVENLABS, use_speaker_boost: false });
        ouvrirLesSousMenus();
        expect(document.querySelector('[data-valeur-par-defaut="tts_use_speaker_boost"]')).not.toBeNull();
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(chargeTts(onSave).use_speaker_boost).toBe(false);
    });

    it("`reduce_silence` de la voix Soniox a le même moyen de revenir à vide", async () => {
        await ouvrir(CONFIG_SONIOX);
        ouvrirLesSousMenus();
        // `reduce_silence` est facultatif (bool | None) : il a le même moyen de revenir.
        expect(document.querySelector('[data-valeur-vide="tts_reduce_silence"]')).not.toBeNull();
    });
});
