/**
 * [.mark] Clôture, SA-3 (D18) : les limites du moteur du planificateur sur l'écran Rendez-vous (avancé).
 *
 * Questions : les valeurs d'avant se lisent-elles quand le serveur n'a rien posé ? Un nombre hors bornes est-il refusé sous
 * le champ, sans rien envoyer ? Ce qui est saisi est-il exactement ce qui part, et le résultat dit par une notification ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { SectionMoteurPlanificateur } from "./SectionMoteurPlanificateur";

const m = vi.hoisted(() => ({ lire: vi.fn(), ecrire: vi.fn(), succes: vi.fn(), echec: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurGet: m.lire,
        putPlanificateurMoteurApiV1OrganizationsPlanificateurMoteurPut: m.ecrire,
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("../notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));

const VALEURS = { max_lieux: 40, parallele_lieux: 8, temps_max_lieux_s: 2.5, geocodage_delai_s: 1.5, geocodage_score_min: 0.6, geocodage_memoire_s: 3600, pose_duree_s: 14400 };

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const ouvrir = async () => {
    render(
        <FournisseurLangue>
            <SectionMoteurPlanificateur />
        </FournisseurLangue>,
    );
    const section = (await screen.findByText(/Advanced: engine limits|Avancé : limites du moteur/)).closest("section") as HTMLElement;
    return section;
};

describe("limites du moteur du planificateur", () => {
    it("montre les valeurs d'avant et leurs libellés dans les deux langues", async () => {
        m.lire.mockResolvedValue({ data: {} });
        const section = await ouvrir();
        expect(within(section).getByText(/^40 (addresses|adresses)$/)).toBeTruthy();
        expect(within(section).getByText("2.5 s")).toBeTruthy();
        expect(within(section).getByText("14400 s")).toBeTruthy();
    });

    it("refuse un nombre hors bornes sous le champ, et envoie exactement ce qui est saisi", async () => {
        m.lire.mockResolvedValue({ data: VALEURS });
        m.ecrire.mockImplementation(async ({ body }) => ({ data: body }));
        const section = await ouvrir();
        fireEvent.click(within(section).getByRole("button", { name: /Edit|Modifier/ }));
        const champ = (nom: RegExp) => screen.getByLabelText(nom) as HTMLInputElement;
        fireEvent.change(champ(/Addresses placed per call|Adresses placées par appel/), { target: { value: "0" } });
        fireEvent.click(screen.getByRole("button", { name: /^(Save|Enregistrer)$/ }));
        await waitFor(() => expect(screen.getByText(/A number from 1 to 200|Un nombre de 1 à 200/)).toBeTruthy());
        expect(m.ecrire).not.toHaveBeenCalled();
        fireEvent.change(champ(/Addresses placed per call|Adresses placées par appel/), { target: { value: "12" } });
        fireEvent.change(champ(/Address service: lowest confidence|Service d'adresses : confiance minimale/), { target: { value: "0.8" } });
        fireEvent.click(screen.getByRole("button", { name: /^(Save|Enregistrer)$/ }));
        await waitFor(() => expect(m.ecrire).toHaveBeenCalledTimes(1));
        expect(m.ecrire.mock.calls[0][0].body).toEqual({ ...VALEURS, max_lieux: 12, geocodage_score_min: 0.8 });
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
    });

    it("dit l'échec par une notification et garde la saisie", async () => {
        m.lire.mockResolvedValue({ data: VALEURS });
        m.ecrire.mockResolvedValue({ error: { detail: "boom" } });
        const section = await ouvrir();
        fireEvent.click(within(section).getByRole("button", { name: /Edit|Modifier/ }));
        fireEvent.change(screen.getByLabelText(/Addresses placed at once|Adresses placées en même temps/), { target: { value: "5" } });
        fireEvent.click(screen.getByRole("button", { name: /^(Save|Enregistrer)$/ }));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect((screen.getByLabelText(/Addresses placed at once|Adresses placées en même temps/) as HTMLInputElement).value).toBe("5");
    });
});
