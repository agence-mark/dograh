/**
 * [.mark] Clôture, SA-3 (D18) : les délais de la panne côté organisation (Twilio, rattrapage) se règlent à l'écran, avancé.
 *
 * Questions : les valeurs d'avant sont-elles lues ? Une faute de frappe bloque-t-elle l'enregistrement ? Ce qui est saisi
 * part-il avec le reste des réglages de la panne, sans toucher aux adresses de secours ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { BlocSecoursPanne } from "./BlocSecoursPanne";

const m = vi.hoisted(() => ({ lire: vi.fn(), ecrire: vi.fn(), succes: vi.fn(), echec: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getPanneApiV1OrganizationsPanneGet: m.lire,
        putPanneApiV1OrganizationsPannePut: m.ecrire,
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec, information: vi.fn() } }));

const REGLAGES = { format: "panne-mark", version: 1, url_secours: "https://handler.twilio.com/twiml/EH1", url_secours_promesse: null, delai_twilio_s: 6, rattrapage_fenetre_h: 24, rattrapage_attente_run_min: 10 };
const ECRAN = { reglages: REGLAGES, texte_du_bin: "<Response/>", texte_du_bin_promesse: "<Response/>" };

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const rendre = () =>
    render(
        <FournisseurLangue>
            <BlocSecoursPanne />
        </FournisseurLangue>,
    );

describe("délais de la panne (organisation)", () => {
    it("lit les valeurs d'avant, refuse une faute de frappe, et envoie les délais avec les réglages de la panne", async () => {
        m.lire.mockResolvedValue({ data: structuredClone(ECRAN) });
        m.ecrire.mockImplementation(async ({ body }) => ({ data: { ...ECRAN, reglages: body } }));
        rendre();
        const delai = (await screen.findByLabelText(/Twilio: time to answer|Twilio : délai de réponse/)) as HTMLInputElement;
        expect(delai.value).toBe("6");
        const bouton = screen.getByTestId("enregistrer-panne-avance") as HTMLButtonElement;
        expect(bouton.disabled).toBe(true); // rien n'a changé
        fireEvent.change(delai, { target: { value: "99" } });
        expect(bouton.disabled).toBe(true); // hors bornes : refusé
        fireEvent.change(delai, { target: { value: "12" } });
        fireEvent.change(screen.getByLabelText(/Catch-up: hours read back|Rattrapage : heures relues/), { target: { value: "48" } });
        fireEvent.click(bouton);
        await waitFor(() => expect(m.ecrire).toHaveBeenCalledTimes(1));
        expect(m.ecrire.mock.calls[0][0].body).toEqual({ ...REGLAGES, delai_twilio_s: 12, rattrapage_fenetre_h: 48 });
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
    });
});
