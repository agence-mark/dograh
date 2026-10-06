/**
 * [.mark] The key library in « Models » and in an agent's model settings (chantier
 * direct-et-passe-muette, lot 0 bis, P18 to P22), MOUNTED in Dograh's real model form.
 *
 * The questions this file answers:
 *
 *     Next to the API key field, does « Keys… » open the library on the provider chosen in the
 *     form, and does « Use » save a reference (`mark-cle:<uuid>`), never the key? Does a referenced
 *     key show by its name, a deleted one say so, and « Type a key » go back to typing? Does a key
 *     typed by hand still save as before? Does the « Keys » page show the whole library?
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PageCles from "@/app/cles/page";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "../ServiceConfigurationForm";

const BIBLIOTHEQUE = [
    { uuid: "c-openai", nom: "OpenAI labo", fournisseur: "openai_realtime" },
    { uuid: "c-mistral", nom: "Mistral org 2", fournisseur: "mistral" },
];

vi.mock("@/client", () => ({
    listerLesClesApiV1ClesGet: async (options?: { query?: { fournisseur?: string } }) => ({
        data: BIBLIOTHEQUE.filter((c) => !options?.query?.fournisseur || c.fournisseur === options.query.fournisseur),
    }),
    fournisseursDesClesApiV1ClesFournisseursGet: async () => ({ data: ["mistral", "openai_realtime", "elevenlabs"] }),
    ajouterUneCleApiV1ClesPost: vi.fn(),
    usagesDUneCleApiV1ClesUuidUsagesGet: vi.fn(),
    supprimerUneCleApiV1ClesUuidDelete: vi.fn(),
    identifiantDesigneApiV1ClesDesigneeUuidGet: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet: vi.fn(),
}));
vi.mock("@/context/UserConfigContext", () => ({ useUserConfig: () => ({ userConfig: null }) }));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => null }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: "u-1" }, loading: false }) }));
vi.mock("@/components/ui/select", () => ({
    Select: ({ value, onValueChange, children }: { value: string; onValueChange: (value: string) => void; children: ReactNode }) => (
        <select value={value} onChange={(event) => onValueChange(event.target.value)}>
            {children}
        </select>
    ),
    SelectContent: ({ children }: { children: ReactNode }) => <>{children}</>,
    SelectTrigger: () => null,
    SelectValue: () => null,
    SelectItem: ({ value, children }: { value: string; children: ReactNode }) => <option value={value}>{children}</option>,
}));

const defaults: ServiceConfigurationDefaults = {
    llm: {},
    tts: {},
    stt: {},
    embeddings: {},
    default_providers: { realtime: "openai_realtime" },
    realtime: {
        openai_realtime: {
            title: "OpenAI",
            properties: {
                provider: { default: "openai_realtime" },
                model: { default: "gpt-realtime-2", examples: ["gpt-realtime-2"] },
                voice: { default: "alloy", examples: ["alloy"] },
                api_key: { type: "string" },
            },
        },
    },
};

const configuration = (api_key: string) => ({
    is_realtime: true,
    realtime: { provider: "openai_realtime", api_key, model: "gpt-realtime-2", voice: "alloy" },
});

const formulaire = (api_key: string, onSave = vi.fn()) => {
    render(
        <ServiceConfigurationForm
            mode="global"
            forceRealtime
            configurationDefaults={defaults}
            initialConfig={configuration(api_key)}
            onSave={onSave}
        />,
    );
    return onSave;
};

const enregistrer = async (onSave: ReturnType<typeof vi.fn>) => {
    fireEvent.click(screen.getByRole("button", { name: "Save Configuration" }));
    await waitFor(() => expect(onSave).toHaveBeenCalledOnce());
    return onSave.mock.calls[0][0].realtime.api_key;
};

beforeEach(() => vi.clearAllMocks());

describe("[.mark] the key library in Dograh's model form", () => {
    it("picks a key of the provider chosen in the form and saves a reference, never the key", async () => {
        const onSave = formulaire("tapee-a-la-main");
        await screen.findByDisplayValue("tapee-a-la-main");
        fireEvent.click(screen.getByRole("button", { name: "Keys…" }));
        const fenetre = await screen.findByTestId("fenetre-cles");
        expect(fenetre.textContent).toContain("Keys · OpenAI Realtime");
        const ligne = await within(fenetre).findByTestId("cle-c-openai");
        expect(within(fenetre).queryByTestId("cle-c-mistral")).toBeNull();
        fireEvent.click(within(ligne).getByRole("button", { name: "Use" }));
        await waitFor(() => expect(screen.queryByTestId("fenetre-cles")).toBeNull());
        expect((await screen.findByTestId("cle-de-la-bibliotheque")).textContent).toContain("OpenAI labo · OpenAI Realtime · key library");
        expect(await enregistrer(onSave)).toEqual(["mark-cle:c-openai"]);
    });

    it("shows a referenced key by its name, and goes back to typing on « Type a key »", async () => {
        const onSave = formulaire("mark-cle:c-openai");
        expect((await screen.findByTestId("cle-de-la-bibliotheque")).textContent).toContain("OpenAI labo");
        expect(screen.queryByDisplayValue("mark-cle:c-openai")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Type a key" }));
        fireEvent.change(await screen.findByPlaceholderText("Enter API key"), { target: { value: "nouvelle-cle" } });
        expect(await enregistrer(onSave)).toEqual(["nouvelle-cle"]);
    });

    it("says when the referenced key was deleted from the library", async () => {
        formulaire("mark-cle:c-supprimee");
        expect(await screen.findByText(/This key was deleted from the library/)).toBeTruthy();
        expect(screen.getByTestId("cle-de-la-bibliotheque").textContent).toContain("Key deleted");
    });

    it("warns when the referenced key belongs to another provider", async () => {
        formulaire("mark-cle:c-mistral");
        expect(await screen.findByText(/This is a Mistral key, not a OpenAI Realtime one/)).toBeTruthy();
    });
});

describe("[.mark] the « Keys » page of the menu (P18)", () => {
    it("shows the whole library, every provider, with a key to add", async () => {
        render(<PageCles />);
        const page = await screen.findByTestId("page-cles");
        await within(page).findByTestId("cle-c-openai");
        expect(within(page).getByTestId("cle-c-mistral")).toBeTruthy();
        const fournisseur = within(page).getByLabelText("Provider") as HTMLSelectElement;
        await waitFor(() => expect(fournisseur.options.length).toBe(3));
        expect(fournisseur.disabled).toBe(false);
        expect(fournisseur.value).toBe("mistral");
    });
});
