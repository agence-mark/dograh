/**
 * [.mark] The establishments on screen (chantier l-agent-travaille, L1), rendered.
 *
 *   - the Establishments theme shows the saved ones and opens the modal (E4);
 *   - in the modal: add one, choose its numbers (a number taken elsewhere is disabled),
 *     an inherited value is greyed with « Customize », clearing goes back to inherited (E2);
 *   - « Save » sends exactly the catalogue, empty fields as null (inherited);
 *   - a refusal of the server (422) is shown and the modal stays open;
 *   - an unreadable catalogue leaves nothing to save;
 *   - the agent's theme shows the establishments it serves and where each value comes from.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { EtablissementsServis } from "../reglages-agent/EtablissementsServis";
import { charge_utile_etablissements, identifiantPour, ModaleEtablissements } from "./ModaleEtablissements";

const m = vi.hoisted(() => ({
    get: vi.fn(),
    numeros: vi.fn(),
    save: vi.fn(),
    agent: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.get,
    getNumerosApiV1OrganizationsEtablissementsNumerosGet: m.numeros,
    saveEtablissementsApiV1OrganizationsEtablissementsPut: m.save,
    postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost: m.agent,
    getCommunesDuCodePostalApiV1OrganizationsCommunesGet: () => Promise.resolve({ data: [{ code_insee: "60612", nom: "Senlis" }] }),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));

const CREIL = {
    id: "creil",
    nom: "Magasin de Creil",
    numeros: ["+33344000001"],
    second_numero: null,
    numero_transfert: null,
    adresse: null,
    horaires_ouverture: null,
    annonce_fermeture: null,
    annonce_pause: null,
};
const ANNONCE = { annonce_fermeture: "Nous sommes fermés.", annonce_pause: "En pause.", etat_force: null, etat_force_jusqu_a: null };

const reinitialiser = () => {
    m.get.mockReset().mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: [CREIL] } });
    m.numeros.mockReset().mockResolvedValue({
        data: [
            { numero: "+33344000001", libelle: "Creil", agent: "Accueil" },
            { numero: "+33344000002", libelle: null, agent: null },
        ],
    });
    m.save.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
    m.agent.mockReset();
};
reinitialiser();
afterEach(() => {
    cleanup();
    reinitialiser();
    window.localStorage.clear();
});

const ouvrir = async (onFermer = vi.fn()) => {
    window.localStorage.setItem("mark.langue", "en");
    render(
        <FournisseurLangue>
            <ModaleEtablissements ouverte onFermer={onFermer} adresseOrganisation={null} annonceOrganisation={ANNONCE} />
        </FournisseurLangue>,
    );
    await waitFor(() => expect(screen.getByTestId("fiche-etablissement")).toBeTruthy());
    return onFermer;
};

describe("[.mark] the establishments modal", () => {
    it("derives a unique identifier from the name", () => {
        expect(identifiantPour("Magasin de Créteil", [])).toBe("magasin-de-creteil");
        expect(identifiantPour("Magasin", ["magasin"])).toBe("magasin-2");
    });

    it("keeps a saved identifier when the name changes", async () => {
        await ouvrir();
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Creil centre" } });
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.save.mock.calls[0][0].body.etablissements[0]).toMatchObject({ id: "creil", nom: "Creil centre" });
    });

    it("saves untouched exactly what it read, empty fields as inherited", async () => {
        const onFermer = await ouvrir();
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        expect(m.save.mock.calls[0][0].body).toEqual(charge_utile_etablissements([CREIL]));
        expect(m.save.mock.calls[0][0].body.etablissements[0]).toEqual(CREIL);
        await waitFor(() => expect(onFermer).toHaveBeenCalledWith(true));
    });

    it("adds an establishment, takes a free number, refuses a taken one, customizes then inherits", async () => {
        await ouvrir();
        fireEvent.click(screen.getByTestId("ajouter-etablissement"));
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Magasin de Senlis" } });
        const pris = screen.getByText("+33344000001").closest("label")!.querySelector("input")!;
        const libre = screen.getByText("+33344000002").closest("label")!.querySelector("input")!;
        expect(pris.disabled).toBe(true);
        fireEvent.click(libre);
        // Inherited, greyed, with the organization's sentence
        expect(screen.getByTestId("herite-annonce_fermeture").textContent).toContain("Nous sommes fermés.");
        fireEvent.click(screen.getByTestId("personnaliser-annonce_fermeture"));
        fireEvent.change(document.getElementById("etablissement-annonce_fermeture")!, { target: { value: "Senlis est fermé." } });
        fireEvent.click(screen.getByTestId("personnaliser-horaires_ouverture"));
        fireEvent.change(document.getElementById("etablissement-horaires")!, { target: { value: "lundi : fermé" } });
        fireEvent.click(screen.getByTestId("heriter-horaires_ouverture"));
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        const [, nouveau] = m.save.mock.calls[0][0].body.etablissements;
        expect(nouveau).toEqual({
            id: "magasin-de-senlis",
            nom: "Magasin de Senlis",
            numeros: ["+33344000002"],
            second_numero: null,
            numero_transfert: null,
            adresse: null,
            horaires_ouverture: null,
            annonce_fermeture: "Senlis est fermé.",
            annonce_pause: null,
        });
    });

    it("shows a refusal of the server and stays open", async () => {
        m.save.mockResolvedValue({ error: { detail: [{ msg: "Magasin de Creil: ligne 1 : heure illisible", loc: [] }] } });
        const onFermer = await ouvrir();
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(screen.getByTestId("erreur-etablissements").textContent).toContain("heure illisible"));
        expect(onFermer).not.toHaveBeenCalled();
    });

    it("an unreadable catalogue leaves nothing to save", async () => {
        m.get.mockResolvedValue({ error: { detail: "cannot be read" } });
        render(
            <FournisseurLangue>
                <ModaleEtablissements ouverte onFermer={vi.fn()} adresseOrganisation={null} annonceOrganisation={ANNONCE} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("erreur-etablissements")).toBeTruthy());
        expect((screen.getByTestId("enregistrer-etablissements") as HTMLButtonElement).disabled).toBe(true);
    });
});

describe("[.mark] the establishments an agent serves", () => {
    it("shows each value and where it comes from, with the agent's draft sent to the server", async () => {
        m.agent.mockResolvedValue({
            data: {
                etablissements: [
                    {
                        id: "creil",
                        nom: "Magasin de Creil",
                        numeros: ["+33344000001"],
                        horaires_ouverture: { valeur: "lundi : fermé", origine: "etablissement" },
                        adresse: { valeur: "60740 Saint-Maximin", origine: "organisation" },
                        annonce_fermeture: { valeur: "Fermé.", origine: "organisation" },
                        annonce_pause: { valeur: null, origine: "aucune" },
                        numero_transfert: { valeur: null, origine: "aucune" },
                    },
                ],
                numeros_sans_etablissement: [],
            },
        });
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <EtablissementsServis workflowId={34} horaires={null} adresse={null} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("etablissements-servis")).toBeTruthy());
        expect(m.agent.mock.calls[0][0].body).toEqual({ workflow_id: 34, horaires_ouverture: null, adresse_etablissement: null });
        const texte = screen.getByTestId("etablissements-servis").textContent ?? "";
        expect(texte).toContain("Magasin de Creil");
        expect(texte).toContain("(the establishment)");
        expect(texte).toContain("(inherited from the organization)");
    });

    it("says so when the agent serves none", async () => {
        m.agent.mockResolvedValue({ data: { etablissements: [], numeros_sans_etablissement: [] } });
        render(
            <FournisseurLangue>
                <EtablissementsServis workflowId={34} horaires={null} adresse={null} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("aucun-etablissement-servi")).toBeTruthy());
    });
});
