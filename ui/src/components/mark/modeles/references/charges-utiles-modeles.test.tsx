/**
 * [.mark] References of the Models screen: which fields it shows, and what
 * saving sends, for Mistral, ElevenLabs and Deepgram (Flux and nova).
 *
 * Chantier reorganisation-ecran-reglages, steps 1 and 6. Step 6 files the
 * fields of these three providers into sub-menus (groups declared in the
 * Python schema) and gives them readable labels. Nothing else may change: no
 * field lost, the same fields hidden for the same model, the same payload.
 * So, BEFORE step 6, this file rendered the form as it was, with the REAL
 * schemas (`schemas-fournisseurs.json`, exported from the Python registry),
 * and froze, per provider and per model:
 *
 *   - the fields the tab shows, in order;
 *   - what « Save Configuration » sends untouched;
 *   - what it sends after changing each field that can be typed or switched.
 *
 * Since step 6 the fields are in sub-menus: the untouched payload is taken
 * with every sub-menu CLOSED (a closed sub-menu keeps its values), then the
 * sub-menus are opened to list and change the fields. The fields are compared
 * as a set: putting them in groups is the change, their order is not frozen.
 * ⛔ The reference is never rewritten: it was written by `ECRIRE_REFERENCES=1`
 * on the form as it was (before step 6), and that flag now fails the run.
 *
 * Mocked: the voice picker (it calls the provider's API; a plain input with
 * the same callback) and the Radix Select (native, `select-natif.tsx`).
 */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";

import { commeEnvoye, difference } from "../../reglages-agent/references/jouer";

const DOSSIER = join(process.cwd(), "src/components/mark/modeles/references");
const FICHIER = join(DOSSIER, "charges-utiles-modeles.json");
const ECRIRE = process.env.ECRIRE_REFERENCES === "1";

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));
vi.mock("@/components/ui/select", () => import("../../reglages-agent/references/select-natif"));
vi.mock("@/components/VoiceSelector", () => ({
    VoiceSelector: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
        <input id="tts_voice" value={value} onChange={(e) => onChange(e.target.value)} />
    ),
}));
vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

type Schemas = Record<"llm" | "tts" | "stt", Record<string, { properties: Record<string, Record<string, unknown>> }>>;
export const SCHEMAS = JSON.parse(readFileSync(join(DOSSIER, "schemas-fournisseurs.json"), "utf8")) as Schemas;

const DEFAUTS = {
    llm: SCHEMAS.llm,
    tts: SCHEMAS.tts,
    stt: SCHEMAS.stt,
    embeddings: {},
    default_providers: { llm: "mistral", tts: "elevenlabs", stt: "deepgram" },
} as unknown as ServiceConfigurationDefaults;

type Service = "llm" | "tts" | "stt";

/** One configuration per model the screen treats differently. */
export const SITUATIONS: Array<{ id: string; service: Service; onglet: RegExp; config: Record<string, unknown> }> = [
    { id: "mistral", service: "llm", onglet: /^llm$/i, config: { provider: "mistral", model: "mistral-large-2512" } },
    { id: "elevenlabs", service: "tts", onglet: /^voice$/i, config: { provider: "elevenlabs", model: "eleven_flash_v2_5" } },
    { id: "deepgram-nova-3", service: "stt", onglet: /^transcriber$/i, config: { provider: "deepgram", model: "nova-3-general", language: "fr" } },
    { id: "deepgram-flux-multi", service: "stt", onglet: /^transcriber$/i, config: { provider: "deepgram", model: "flux-general-multi", language: "fr" } },
    { id: "deepgram-flux-en", service: "stt", onglet: /^transcriber$/i, config: { provider: "deepgram", model: "flux-general-en", language: "en" } },
    { id: "deepgram-nova-2", service: "stt", onglet: /^transcriber$/i, config: { provider: "deepgram", model: "nova-2-general", language: "fr" } },
];

const CONFIG_INITIALE = (situation: (typeof SITUATIONS)[number]) => ({
    llm: { provider: "mistral", model: "mistral-large-2512", api_key: ["cle-llm"] },
    tts: { provider: "elevenlabs", model: "eleven_flash_v2_5", api_key: ["cle-tts"] },
    stt: { provider: "deepgram", model: "nova-3-general", api_key: ["cle-stt"] },
    [situation.service]: { ...situation.config, api_key: [`cle-${situation.service}`] },
});

afterEach(cleanup);

export const ouvrir = async (situation: (typeof SITUATIONS)[number]) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
        <ServiceConfigurationForm
            mode="global"
            onSave={onSave}
            configurationDefaults={DEFAUTS}
            initialConfig={CONFIG_INITIALE(situation)}
            forceRealtime={false}
        />,
    );
    const onglet = await waitFor(() => screen.getByRole("tab", { name: situation.onglet }));
    fireEvent.mouseDown(onglet);
    fireEvent.click(onglet);
    await waitFor(() => expect(screen.getAllByText(/^model$/i).length).toBeGreaterThan(0));
    return onSave;
};

/** Opens every sub-menu of the tab (step 6). */
export const ouvrirLesSousMenus = () => {
    for (const bouton of document.querySelectorAll<HTMLButtonElement>('[data-sous-menu] > button[aria-expanded="false"]')) {
        fireEvent.click(bouton);
    }
};

/** The fields the tab shows, every sub-menu open. */
const champsAffiches = (): string[] => {
    ouvrirLesSousMenus();
    return Array.from(document.querySelectorAll("[data-champ]")).map((champ) => champ.getAttribute("data-champ") ?? "");
};

/** A value inside the field's bounds that differs from its default. */
const valeurNumerique = (schema: Record<string, unknown>): string => {
    const brut = (schema.anyOf as Array<Record<string, unknown>> | undefined)?.find((o) => o.type === "number" || o.type === "integer") ?? schema;
    const min = typeof brut.minimum === "number" ? brut.minimum : 0;
    const max = typeof brut.maximum === "number" ? brut.maximum : min + 10;
    const milieu = brut.type === "integer" ? Math.round((min + max) / 2) : Math.round(((min + max) / 2) * 100) / 100;
    return String(milieu === schema.default ? (brut.type === "integer" ? milieu + 1 : milieu + 0.01) : milieu);
};

/** Changes one field the way a person would, or says it cannot be typed. */
export const modifierChamp = (service: Service, champ: string, schema: Record<string, unknown>): string | null => {
    const parId = document.getElementById(`${service}_${champ}`);
    if (parId?.getAttribute("role") === "switch") {
        if ((parId as HTMLButtonElement).disabled) return null;
        fireEvent.click(parId);
        return "interrupteur";
    }
    if (parId?.tagName === "INPUT" && service === "tts" && champ === "voice") {
        fireEvent.change(parId, { target: { value: "voix-essai" } });
        return "voix";
    }
    if (parId?.tagName === "INPUT") {
        fireEvent.change(parId, { target: { value: "essai" } });
        fireEvent.keyDown(parId, { key: "Enter" });
        return "etiquette";
    }
    const champTexte = screen.queryByPlaceholderText(`Enter ${champ}`) as HTMLInputElement | null;
    if (!champTexte || champTexte.disabled) return null;
    if (champTexte.type === "number") {
        fireEvent.change(champTexte, { target: { value: valeurNumerique(schema) } });
        return "nombre";
    }
    fireEvent.change(champTexte, { target: { value: "https://essai.example" } });
    return "texte";
};

export const enregistrer = async (onSave: ReturnType<typeof vi.fn>) => {
    fireEvent.click(screen.getByRole("button", { name: /save configuration/i }));
    await waitFor(() => expect(onSave).toHaveBeenCalled());
    return commeEnvoye(onSave.mock.calls[0][0]) as Record<string, Record<string, unknown>>;
};

const references: {
    situations: Record<string, { champs: string[]; sansModification: unknown; modifications: Record<string, unknown> }>;
} = existsSync(FICHIER) && !ECRIRE ? JSON.parse(readFileSync(FICHIER, "utf8")) : { situations: {} };

describe("references of the Models screen", () => {
    it.each(SITUATIONS.map((s) => [s.id, s] as const))("%s: fields shown, untouched payload, each field's payload", async (_id, situation) => {
        if (ECRIRE) throw new Error("⛔ The references are only ever written on the form as it was (before step 6).");
        // Untouched, every sub-menu closed.
        const onSave = await ouvrir(situation);
        expect(document.querySelectorAll('[data-sous-menu] > button[aria-expanded="true"]').length).toBe(0);
        const sansModification = await enregistrer(onSave);
        cleanup();
        const champs = await (async () => {
            await ouvrir(situation);
            const liste = champsAffiches();
            cleanup();
            return liste;
        })();

        const modifications: Record<string, unknown> = {};
        const proprietes = SCHEMAS[situation.service][situation.config.provider as string].properties;
        for (const champ of champs) {
            if (champ === "model" || champ === "language") continue;
            const envoi = await ouvrir(situation);
            ouvrirLesSousMenus();
            const geste = modifierChamp(situation.service, champ, proprietes[champ] ?? {});
            if (geste === null) {
                modifications[champ] = "not typed (list or read-only)";
                cleanup();
                continue;
            }
            const charge = await enregistrer(envoi);
            modifications[champ] = {
                geste,
                ...difference(sansModification[situation.service], charge[situation.service]),
                autresServicesInchanges: (["llm", "tts", "stt"] as const)
                    .filter((s) => s !== situation.service)
                    .every((s) => JSON.stringify(charge[s]) === JSON.stringify(sansModification[s])),
            };
            cleanup();
        }

        const reference = references.situations[situation.id];
        expect([...champs].sort(), "the same fields, none lost").toEqual([...reference.champs].sort());
        expect(sansModification).toEqual(reference.sansModification);
        expect(modifications).toEqual(reference.modifications);
    }, 120000);

    it("wrote or matched every situation", () => {
        if (ECRIRE) writeFileSync(FICHIER, `${JSON.stringify(references, null, 2)}\n`, "utf8");
        expect(Object.keys(references.situations).sort()).toEqual(SITUATIONS.map((s) => s.id).sort());
    });
});
