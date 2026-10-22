/**
 * [.mark] Lot 3 d'orchestrateur-trois-cerveaux (D7) : la voix de l'appel, vue de l'écran.
 *
 * La question que ce fichier pose, et elle seule :
 *
 *     L'onglet « Voice » d'un agent d'un groupe est-il en lecture seule, avec sa note, même quand
 *     l'agent a détaché son cerveau, et celui d'un agent seul est-il EXACTEMENT celui d'avant ?
 *
 * Le fichier RENDRE le formulaire : un attribut lu dans le code n'est pas un champ verrouillé à
 * l'écran. (La page complète des réglages ne se rend pas ici : le thème des modèles exige la base.)
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { type ServiceConfigurationDefaults, ServiceConfigurationForm } from "../ServiceConfigurationForm";
import { CLE_LANGUE, FournisseurLangue } from "./langue/langue";
import { NoteVoixDeLAppel } from "./reglages-agent/ThemeBriques";

vi.mock("@/context/UserConfigContext", () => ({
    useUserConfig: () => ({ userConfig: null, refreshConfig: vi.fn() }),
}));
vi.mock("@/components/VoiceSelector", () => ({ VoiceSelector: () => null }));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() { }
        unobserve() { }
        disconnect() { }
    },
);

const schemaLlm = {
    title: "Témoin LLM",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: { type: "string", default: "modele-temoin" },
    },
} as unknown as ServiceConfigurationDefaults["llm"][string];

const schemaVoix = {
    title: "Témoin voix",
    properties: {
        provider: { type: "string", default: "temoin" },
        api_key: { type: "string" },
        model: { type: "string", default: "voix-temoin" },
        speed: { type: "number", default: 1, minimum: 0.5, maximum: 2, description: "Speed of the voice." },
    },
} as unknown as ServiceConfigurationDefaults["tts"][string];

const defauts: ServiceConfigurationDefaults = {
    llm: { temoin: schemaLlm },
    tts: { temoin: schemaVoix },
    stt: {},
    embeddings: {},
    default_providers: { llm: "temoin", tts: "temoin" },
};

async function ouvrirLOngletVoix(voixVerrouillee?: React.ReactNode) {
    const { container } = render(
        <FournisseurLangue>
            <ServiceConfigurationForm
                mode="global"
                onSave={vi.fn()}
                configurationDefaults={defauts}
                forceRealtime={false}
                voixVerrouillee={voixVerrouillee}
            />
        </FournisseurLangue>,
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: /voice|voix/i }), { button: 0 });
    await waitFor(() => expect(screen.getByRole("tab", { name: /voice|voix/i }).getAttribute("data-state")).toBe("active"));
    return container;
}

describe("[.mark] la voix de l'appel à l'écran", () => {
    it("verrouille l'onglet Voice d'un agent d'un groupe et dit pourquoi", async () => {
        const conteneur = await ouvrirLOngletVoix(<NoteVoixDeLAppel />);
        // La note, dans les deux langues du code (le français par défaut).
        await waitFor(() => expect(conteneur.querySelector('[data-bandeau="voix-de-l-appel"]')).not.toBeNull());
        expect(conteneur.querySelector('[data-bandeau="voix-de-l-appel"]')?.textContent).toContain("L'appel n'a qu'une voix");
        // Les champs de la voix sont dans un ensemble désactivé : aucun ne s'écrit.
        const lecture = conteneur.querySelector('fieldset[data-lecture="voix"]') as HTMLFieldSetElement;
        expect(lecture).not.toBeNull();
        expect(lecture.disabled).toBe(true);
        expect(lecture.querySelector("input, select, [role='combobox']")).not.toBeNull();
    });

    it("laisse l'onglet Voice d'un agent seul tel qu'il était : aucun verrou, aucune note", async () => {
        const conteneur = await ouvrirLOngletVoix(undefined);
        expect(conteneur.querySelector('fieldset[data-lecture="voix"]')).toBeNull();
        expect(conteneur.querySelector('[data-bandeau="voix-de-l-appel"]')).toBeNull();
        expect(conteneur.querySelector("input")).not.toBeNull();
    });

    it("écrit la note en anglais ET en français", () => {
        const lire = (langue: string) => {
            window.localStorage.setItem(CLE_LANGUE, langue);
            const { container, unmount } = render(
                <FournisseurLangue>
                    <NoteVoixDeLAppel />
                </FournisseurLangue>,
            );
            const texte = container.textContent ?? "";
            unmount();
            return texte;
        };
        const fr = lire("fr");
        const en = lire("en");
        window.localStorage.removeItem(CLE_LANGUE);
        expect(fr).toContain("L'appel n'a qu'une voix");
        expect(en).toContain("The call has one voice");
    });
});
