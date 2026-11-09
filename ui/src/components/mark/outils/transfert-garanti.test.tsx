/**
 * [.mark] Clôture D2 (D14) : « Transfert garanti à l'arrivée » sur la fenêtre de l'outil de transfert d'appel.
 *
 *   - le bloc liste les agents qui utilisent l'outil, avec un interrupteur chacun (valeur lue de l'agent) ;
 *   - UN SEUL « Enregistrer » : le pied enregistre le réglage de l'agent (configuration complète de l'agent + la clé), une notification ;
 *   - le bloc n'existe que sur un outil de transfert d'appel ;
 *   - le thème « Données de l'appel » ne l'a plus (un seul endroit).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { FenetreOutil } from "./FenetreOutil";

const TRANSFERT = {
    id: 5, tool_uuid: "u-transfert", name: "Passer_a_l_accueil", description: "Passe l'appel.", category: "transfer_call", icon: null, icon_color: null, status: "active",
    created_at: "2026-11-01T10:00:00Z", updated_at: null,
    definition: { schema_version: 1, type: "transfer_call", config: { destination: "+33100000000", timeout: 30 } },
};
const FIN = { ...TRANSFERT, id: 6, tool_uuid: "u-fin", name: "Fin", category: "end_call", definition: { schema_version: 1, type: "end_call", config: {} } };

const m = vi.hoisted(() => ({ maj: vi.fn(), majAgent: vi.fn(), lireAgent: vi.fn(), stats: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        updateToolApiV1ToolsToolUuidPut: m.maj,
        updateWorkflowApiV1WorkflowWorkflowIdPut: m.majAgent,
        getWorkflowApiV1WorkflowFetchWorkflowIdGet: m.lireAgent,
        statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet: m.stats,
        getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: [] }),
        getConnexionsApiV1ConnecteursConnexionsGet: () => Promise.resolve({ data: { nango_configure: false, connexions: [] } }),
        listCredentialsApiV1CredentialsGet: () => Promise.resolve({ data: [] }),
    }),
);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
Element.prototype.scrollIntoView = vi.fn();
Element.prototype.hasPointerCapture = vi.fn(() => false);

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const STATS = { executions: 0, reussies: 0, echecs: 0, reussite: null, duree_mediane_ms: null, jours: 30, page: 0, par_page: 25, total_executions: 0, dernieres_executions: [], agents: [{ agent_id: 7, agent: "Accueil Tilleuls", etapes: ["Accueil", "Urgence"] }] };

const monter = (outil = TRANSFERT) => {
    m.stats.mockResolvedValue({ data: STATS });
    m.lireAgent.mockResolvedValue({ data: { id: 7, name: "Accueil Tilleuls", workflow_configurations: { fiche_au_fil_de_leau: true, fiche_champs: ["nom"] } } });
    m.maj.mockResolvedValue({ data: outil });
    m.majAgent.mockResolvedValue({ data: { id: 7 } });
    return render(
        <FournisseurLangue>
            <FenetreOutil outil={outil as never} fermer={vi.fn()} apresEcriture={vi.fn()} />
        </FournisseurLangue>,
    );
};

describe("[.mark] D14 : le transfert garanti sur la fenêtre de l'outil de transfert", () => {
    it("liste les agents de l'outil, enregistre le réglage de l'agent avec le même bouton, une seule notification", async () => {
        monter();
        fireEvent.click(screen.getByRole("tab", { name: /Destination/ }));
        const interrupteur = await screen.findByRole("switch", { name: /Transfert garanti à l'arrivée : Accueil Tilleuls/ });
        expect(interrupteur.getAttribute("aria-checked")).toBe("false");
        expect(screen.getAllByRole("button", { name: "Enregistrer" })).toHaveLength(1);
        const enregistrer = screen.getByRole("button", { name: "Enregistrer" }) as HTMLButtonElement;
        expect(enregistrer.disabled).toBe(true);

        fireEvent.click(interrupteur);
        expect(enregistrer.disabled).toBe(false);
        fireEvent.click(enregistrer);
        await waitFor(() => expect(m.majAgent).toHaveBeenCalledTimes(1));
        const appel = m.majAgent.mock.calls[0][0];
        expect(appel.path).toEqual({ workflow_id: 7 });
        // La configuration de l'agent est renvoyée en entier, avec la seule clé changée.
        expect(appel.body.workflow_configurations).toEqual({ fiche_au_fil_de_leau: true, fiche_champs: ["nom"], transfert_garanti: true });
        // L'outil n'a pas changé : il n'est pas réécrit.
        expect(m.maj).not.toHaveBeenCalled();
    });

    it("un outil de fin d'appel n'a pas ce bloc", async () => {
        monter(FIN);
        await screen.findByRole("tab", { name: /Fin d'appel/ });
        expect(document.querySelector('[data-bloc="transfert-garanti"]')).toBeNull();
        expect(m.stats).not.toHaveBeenCalledWith(expect.objectContaining({ path: { tool_uuid: "u-transfert" } }));
    });

    it("le thème « Données de l'appel » ne porte plus le réglage : un seul endroit", () => {
        const theme = readFileSync(join(process.cwd(), "src/components/mark/reglages-agent/ThemeDonnees.tsx"), "utf8");
        expect(theme).not.toContain('id="transfert_garanti"');
        expect(theme).not.toContain("transfert_garanti: transfert");
    });
});
