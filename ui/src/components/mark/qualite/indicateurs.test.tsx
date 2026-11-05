/**
 * [.mark] V4 : l'onglet « Indicateurs » de Qualité dit ses colonnes dans la langue de l'écran.
 *
 * Question : la colonne « Appels 7 j » du tableau « Par agent » se lit-elle « Calls 7 d » en anglais (jamais le « j » français) et suit-elle
 * la période choisie ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const qualite = vi.hoisted(() => vi.fn());
vi.mock("@/client", () => ({ lireLaQualiteApiV1QualiteGet: (...a: unknown[]) => qualite(...a) }));
// Un objet stable : le vrai `useAuth` ne rend pas un nouvel utilisateur à chaque rendu (l'effet de lecture en dépend).
const session = vi.hoisted(() => ({ user: { id: 1 }, loading: false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => session }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/clients/12/qualite" }));  // un client : la route de l espace (le Labo lit la vue tous clients, voir a-ameliorer.test.tsx)

import { OngletIndicateurs } from "./OngletIndicateurs";

const RESUME = {
    appels: 6, appels_mesures: 6, juges: 2, note: 4.3, issues: 5, part_issue: 0.81, transferts: 3, part_transferts: 0.5,
    raccroches: 1, part_raccroches: 0.17, part_impasse: 0.1, reponse_mediane: 0.9, cout: 0.2,
};
const DONNEES = {
    jours: 7,
    global: RESUME,
    motifs: [],
    versions: [],
    agents: [{ ...RESUME, workflow_id: 4, workflow_nom: "Accueil", version: 3 }],
};

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("Qualité › Indicateurs : colonnes dans la langue de l'écran", () => {
    it("anglais : « Calls 7 d », puis « Calls 30 d » quand on passe à 30 jours", async () => {
        qualite.mockResolvedValue({ data: DONNEES, error: undefined });
        render(<OngletIndicateurs />);
        expect(await screen.findByText("Calls 7 d")).toBeTruthy();
        expect(screen.queryByText(/\d j$/)).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "30 days" }));
        await waitFor(() => expect(screen.getByText("Calls 30 d")).toBeTruthy());
        expect(qualite).toHaveBeenLastCalledWith({ query: { jours: 30 } });
    });

    it("français : « Appels 7 j »", async () => {
        qualite.mockResolvedValue({ data: DONNEES, error: undefined });
        render(
            <FournisseurLangue>
                <OngletIndicateurs />
            </FournisseurLangue>,
        );
        expect(await screen.findByText("Appels 7 j")).toBeTruthy();
    });
});
