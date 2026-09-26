/**
 * [.mark] Les deux interrupteurs de la rue et de l'épellation sont-ils ATTEIGNABLES ?
 *
 * La question, et elle seule :
 *
 *     Evan et Pierre peuvent-ils allumer ou éteindre la vérification des rues
 *     et la lecture des lettres épelées **en cliquant dans l'application** —
 *     pas « est-ce que le composant se rend quand un test le rend » ?
 *
 * Pourquoi ce fichier REND LA PAGE
 * --------------------------------
 * Défaut mesuré le 14/09 : 29 réglages étaient montés dans un fichier monté
 * dans AUCUN écran. Tous les tests étaient verts, personne ne pouvait toucher
 * un seul réglage. Rendre un composant prouve que le composant marche ; ça ne
 * prouve pas qu'on l'atteint. Même mise en scène que
 * `section-reglages-pipecat-montee.test.tsx`, dont les simulacres sont repris.
 *
 * Ce qui est simulé est étroit et assumé : ce qu'un test JSDOM ne peut pas
 * avoir (authentification, routage, client d'API, état du workflow). Rien de la
 * structure de la page.
 *
 * Ce que ce fichier NE prouve pas : que le réglage arrive jusqu'à l'appel
 * (`api/tests/mark/test_adresses_epellation_branchement.py`), ni que le lecteur
 * a raison (`test_recherche_voie.py`, `test_lecture_epellation.py`).
 */

import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DEFAUTS_PIPECAT, resolveWorkflowConfigurations } from "@/types/workflow-configurations";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

vi.mock("next/navigation", () => ({
    useParams: () => ({ workflowId: "1" }),
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

vi.mock("@/lib/auth", () => ({
    useAuth: () => ({
        user: { id: "u-1", email: "evan@example.test" },
        loading: false,
        redirectToLogin: vi.fn(),
    }),
}));

vi.mock("@/context/OrgConfigContext", () => ({
    useOrgConfig: () => ({ externalPbxIntegrationsEnabled: false, userConfig: null }),
}));

vi.mock("@/hooks/useAudioPlayback", () => ({
    useAudioPlayback: () => ({ playingId: null, toggle: vi.fn() }),
}));

vi.mock("@/lib/modelConfigurationPricing", () => ({
    fetchModelConfigurationPricing: () => Promise.resolve({ data: null, error: null }),
}));

const agent = {
    id: 1,
    name: "Agent de test",
    workflow_definition: { nodes: [], edges: [] },
    template_context_variables: {},
    workflow_configurations: {},
};

vi.mock("@/client/sdk.gen", () => ({
    getWorkflowApiV1WorkflowFetchWorkflowIdGet: () =>
        Promise.resolve({ data: agent, error: null }),
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get: () =>
        Promise.resolve({ data: null, error: null }),
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet: () =>
        Promise.resolve({ data: null, error: null }),
    downloadWorkflowReportApiV1WorkflowWorkflowIdReportGet: () =>
        Promise.resolve({ data: null, error: null }),
    getAmbientNoiseUploadUrlApiV1WorkflowAmbientNoiseUploadUrlPost: () =>
        Promise.resolve({ data: null, error: null }),
}));

vi.mock("@/app/workflow/[workflowId]/hooks/useWorkflowState", () => ({
    useWorkflowState: () => ({
        workflowName: "Agent de test",
        workflowConfigurations: resolveWorkflowConfigurations(null),
        defaultCallDispositions: [],
        textChatInactivityTimeoutConstraints: null,
        widgetTextDefaults: {},
        templateContextVariables: {},
        dictionary: "",
        saveWorkflowConfigurations: vi.fn().mockResolvedValue(undefined),
        saveTemplateContextVariables: vi.fn().mockResolvedValue(undefined),
        saveDictionary: vi.fn().mockResolvedValue(undefined),
    }),
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

vi.stubGlobal(
    "IntersectionObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

const { default: WorkflowSettingsPage } = await import(
    "@/app/workflow/[workflowId]/settings/page"
);

// Depuis le chantier reorganisation-ecran-reglages (26/09), la page est faite de
// thèmes repliés : la rue et l'épellation se trouvent en ouvrant « Écoute ».
const rendreLaPage = async () => {
    const rendu = render(<WorkflowSettingsPage />);
    const entete = await waitFor(
        () => {
            const trouve = document.querySelector('[data-theme="ecoute"] > button[aria-expanded]');
            if (!trouve) throw new Error("La page n'est pas encore chargée.");
            return trouve as HTMLButtonElement;
        },
        { timeout: 3000 },
    );
    fireEvent.click(entete);
    return rendu;
};

describe("[.mark] la rue et l'épellation se règlent depuis l'écran", () => {
    it("les deux interrupteurs sont réellement sur la page", async () => {
        await rendreLaPage();
        expect(document.getElementById("verification_voies")).not.toBeNull();
        expect(document.getElementById("lecture_epellation")).not.toBeNull();
    });

    it("ils sortent allumés, comme le schéma du serveur (Q11)", async () => {
        await rendreLaPage();
        expect(document.getElementById("verification_voies")?.getAttribute("data-state")).toBe(
            "checked",
        );
        expect(document.getElementById("lecture_epellation")?.getAttribute("data-state")).toBe(
            "checked",
        );
    });

    it("les libellés disent ce que fait chaque réglage", async () => {
        await rendreLaPage();
        expect(screen.getByRole("switch", { name: /check street names/i })).toBeTruthy();
        expect(screen.getByRole("switch", { name: /read spelled letters/i })).toBeTruthy();
    });

    it("l'interrupteur de la rue se manipule vraiment", async () => {
        // ⛔ Un interrupteur affiché mais figé serait pire que pas d'interrupteur :
        // l'écran mentirait sur l'état de l'agent.
        await rendreLaPage();
        const interrupteur = document.getElementById("verification_voies")!;
        await act(async () => { fireEvent.click(interrupteur); });
        expect(interrupteur.getAttribute("data-state")).toBe("unchecked");
    });

    it("la rue disparaît si la reconnaissance des villes est éteinte, et sa valeur est gardée", async () => {
        // Q11 : sans commune il n'y a pas de liste de rues à fouiller, donc le
        // réglage n'a plus de sens à l'écran — mais rien n'est effacé.
        await rendreLaPage();
        const villes = document.getElementById("verification_communes")!;
        expect(document.getElementById("verification_voies")).not.toBeNull();

        await act(async () => { fireEvent.click(villes); });
        expect(document.getElementById("verification_voies")).toBeNull();
        // L'épellation, elle, ne dépend de rien : elle reste.
        expect(document.getElementById("lecture_epellation")).not.toBeNull();

        await act(async () => { fireEvent.click(villes); });
        const revenu = document.getElementById("verification_voies");
        expect(revenu).not.toBeNull();
        expect(revenu?.getAttribute("data-state")).toBe("checked");
    });

    it("les défauts de l'écran sont ceux du schéma du serveur", () => {
        // 🔑 L'écran porte forcément sa propre copie des défauts. Cette garde est
        // le seul endroit où les deux se regardent ; le pendant côté serveur est
        // dans `test_adresses_epellation_branchement.py`.
        expect(DEFAUTS_PIPECAT.verification_voies).toBe(true);
        expect(DEFAUTS_PIPECAT.lecture_epellation).toBe(true);
    });
});
