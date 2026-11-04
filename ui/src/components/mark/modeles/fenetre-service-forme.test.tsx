/**
 * [.mark] V2b (E51) : le formulaire des fournisseurs MONTÉ dans la fenêtre d'un service.
 *
 * Questions de ce fichier :
 *
 *     Dans la fenêtre, le formulaire est-il un corps nu (aucune carte, aucun bandeau d'onglet pour un seul service) ?
 *     Les fournisseurs sont-ils une colonne cherchable, et choisir l'un d'eux change-t-il le fournisseur envoyé ?
 *     Les noms usuels des champs (modèle, voix, vitesse) sont-ils écrits dans la langue de l'écran ? Le bouton
 *     d'enregistrement est-il celui du pied de la fenêtre (le formulaire n'en dessine pas) ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "@/components/ServiceConfigurationForm";

import { FournisseurLangue } from "../langue/langue";

vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {}),
);
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ userConfig: null }) }));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => null }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));
vi.mock("@/client", () => ({
    listerLesClesApiV1ClesGet: async () => ({ data: [] }),
    fournisseursDesClesApiV1ClesFournisseursGet: async () => ({ data: [] }),
}));

const champ = (defaut: string) => ({ default: defaut, examples: [defaut], type: "string" });
const fournisseur = (titre: string, modele: string) => ({
    title: titre,
    properties: { provider: { default: titre.toLowerCase() }, model: champ(modele), speed: { default: 1, type: "number" }, api_key: { type: "string" } },
});
const defauts = {
    llm: {},
    stt: {},
    embeddings: {},
    tts: { cartesia: fournisseur("Cartesia", "sonic-3.6"), rime: fournisseur("Rime", "mist") },
    default_providers: { tts: "cartesia" },
    realtime: {},
} as unknown as ServiceConfigurationDefaults;

const monter = (surcharge: Partial<React.ComponentProps<typeof ServiceConfigurationForm>> = {}) =>
    render(
        <FournisseurLangue>
            <ServiceConfigurationForm
                mode="global"
                forceRealtime={false}
                segments={["tts"]}
                idFormulaire="formulaire-test"
                sansBoutonEnregistrer
                configurationDefaults={defauts}
                initialConfig={{ tts: { provider: "cartesia", model: "sonic-3.6", api_key: "mark-cle:c-1" } }}
                onSave={vi.fn()}
                {...surcharge}
            />
        </FournisseurLangue>,
    );

beforeEach(() => window.localStorage.setItem("mark.langue", "fr"));
afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

describe("le formulaire dans la fenêtre d'un service", () => {
    it("est un corps nu : pas de carte, pas de bandeau d'onglet pour un seul service, pas de bouton propre", async () => {
        const { container } = monter();
        await screen.findByRole("listbox");
        expect(container.querySelector("[data-slot=card]")).toBeNull();
        expect(container.querySelector("[role=tablist]")?.className ?? "hidden").toContain("hidden");
        expect(screen.queryByRole("button", { name: /Save Configuration|Enregistrer/ })).toBeNull();
        expect(container.querySelector("form#formulaire-test")).not.toBeNull();
    });

    it("liste les fournisseurs du schéma dans une colonne qu'on cherche, et choisir l'un change le fournisseur", async () => {
        const onSave = vi.fn(async () => undefined);
        const { container } = monter({ onSave });
        const liste = await screen.findByRole("listbox");
        expect(within(liste).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cartesia", "Rime"]);
        expect(screen.getByPlaceholderText("2 fournisseurs")).toBeTruthy();
        fireEvent.change(screen.getByPlaceholderText("2 fournisseurs"), { target: { value: "rim" } });
        expect(within(liste).getAllByRole("option").map((o) => o.textContent)).toEqual(["Rime"]);
        fireEvent.click(within(liste).getByRole("option", { name: "Rime" }));
        await waitFor(() => expect(within(liste).getByRole("option", { name: "Rime" }).getAttribute("aria-selected")).toBe("true"));
        fireEvent.submit(container.querySelector("form")!);
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const [envoye] = onSave.mock.calls[0] as unknown as [{ tts: { provider: string } }];
        expect(envoye.tts.provider).toBe("rime");
    });

    it("écrit les noms usuels des champs dans la langue de l'écran", async () => {
        const { container } = monter();
        await screen.findByRole("listbox");
        const noms = Array.from(container.querySelectorAll("label")).map((l) => l.textContent);
        expect(noms).toContain("Vitesse");
        expect(noms.join(" ")).not.toMatch(/\bspeed\b|\bmodel\b/i);
    });

    it("sans fenêtre (sans `idFormulaire`), l'ancien formulaire reste : carte, menu déroulant, bouton d'enregistrement", async () => {
        const { container } = monter({ idFormulaire: undefined, sansBoutonEnregistrer: false, segments: undefined });
        await screen.findByText(/^(Provider|Fournisseur)$/);
        expect(container.querySelector("[role=listbox]")).toBeNull();
        expect(screen.getByRole("button", { name: /Save Configuration|Enregistrer la configuration/ })).toBeTruthy();
    });
});
