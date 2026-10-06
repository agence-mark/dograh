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
import { ChoixEtablissementEssai } from "../etablissements/ChoixEtablissementEssai";
import { charge_utile_etablissements, identifiantPour, ModaleEtablissements } from "./ModaleEtablissements";
import { ModalePhrases } from "./ModalePhrases";

const m = vi.hoisted(() => ({
    get: vi.fn(),
    numeros: vi.fn(),
    save: vi.fn(),
    agent: vi.fn(),
    phrases: vi.fn(),
    savePhrases: vi.fn(),
}));

vi.mock("@/client/sdk.gen", () => ({
    getEtablissementsApiV1OrganizationsEtablissementsGet: m.get,
    getNumerosApiV1OrganizationsEtablissementsNumerosGet: m.numeros,
    saveEtablissementsApiV1OrganizationsEtablissementsPut: m.save,
    postEtablissementsDeLagentApiV1OrganizationsEtablissementsAgentPost: m.agent,
    getPhrasesApiV1OrganizationsPhrasesGet: m.phrases,
    savePhrasesApiV1OrganizationsPhrasesPut: m.savePhrases,
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
    phrases: {},
    termes_lexique: [],
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
    m.phrases.mockReset().mockResolvedValue({
        data: {
            format: "phrases-mark",
            version: 1,
            phrases: [
                { variable: "phrase_rgpd", description: "Mention", contenu: "Vos données restent chez nous.", niveau: "organisation" },
                { variable: "phrase_acces", description: "Access", contenu: "En centre-ville.", niveau: "etablissement" },
            ],
        },
    });
    m.savePhrases.mockReset().mockImplementation(async ({ body }) => ({ data: body }));
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
            phrases: {},
            termes_lexique: [],
        });
    });

    it("gives an establishment its own content for a sentence of its level, and its terms", async () => {
        await ouvrir();
        // Only the sentence placed at the establishment's level is offered, inherited first.
        expect(screen.queryByTestId("champ-phrase_rgpd")).toBeNull();
        expect(screen.getByTestId("herite-phrase_acces").textContent).toContain("En centre-ville.");
        fireEvent.click(screen.getByTestId("personnaliser-phrase_acces"));
        fireEvent.change(document.getElementById("etablissement-phrase-phrase_acces")!, { target: { value: "Derrière la gare." } });
        fireEvent.change(document.getElementById("etablissement-termes")!, { target: { value: "Jøtul\nJøtul\n  Invicta " } });
        fireEvent.click(screen.getByTestId("enregistrer-etablissements"));
        await waitFor(() => expect(m.save).toHaveBeenCalledTimes(1));
        const [creil] = m.save.mock.calls[0][0].body.etablissements;
        expect(creil.phrases).toEqual({ phrase_acces: "Derrière la gare." });
        expect(creil.termes_lexique.map((x: { terme: string }) => x.terme)).toEqual(["Jøtul", "Invicta"]);
        expect(creil.termes_lexique[0]).toMatchObject({ type: "nom", a_ecouter: false, propose: false });
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

describe("[.mark] the sentences modal (E5)", () => {
    const ouvrirPhrases = async (onFermer = vi.fn()) => {
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <ModalePhrases ouverte onFermer={onFermer} annonceOrganisation={ANNONCE} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("liste-phrases")).toBeTruthy());
        return onFermer;
    };

    it("shows the two pick-up announcements as fixed fiches, read-only", async () => {
        await ouvrirPhrases();
        const fixes = screen.getByTestId("phrases-fixes").textContent ?? "";
        expect(fixes).toContain("{{annonce_fermeture}}");
        expect(fixes).toContain("Nous sommes fermés.");
        expect(fixes).toContain("{{annonce_pause}}");
    });

    it("saves untouched exactly what it read, adds one, refuses a bad variable", async () => {
        const onFermer = await ouvrirPhrases();
        fireEvent.click(screen.getByTestId("ajouter-phrase"));
        const variables = screen.getAllByLabelText("Variable");
        fireEvent.change(variables[2], { target: { value: "Mauvaise-Variable" } });
        expect(screen.getByTestId("fautes-phrases")).toBeTruthy();
        expect((screen.getByTestId("enregistrer-phrases") as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(variables[2], { target: { value: "phrase_ete" } });
        fireEvent.change(screen.getAllByLabelText("Content")[2], { target: { value: " Ouvert tout l'été. " } });
        fireEvent.click(screen.getByTestId("enregistrer-phrases"));
        await waitFor(() => expect(m.savePhrases).toHaveBeenCalledTimes(1));
        expect(m.savePhrases.mock.calls[0][0].body).toEqual({
            format: "phrases-mark",
            version: 1,
            phrases: [
                { variable: "phrase_rgpd", description: "Mention", contenu: "Vos données restent chez nous.", niveau: "organisation" },
                { variable: "phrase_acces", description: "Access", contenu: "En centre-ville.", niveau: "etablissement" },
                { variable: "phrase_ete", description: "", contenu: "Ouvert tout l'été.", niveau: "organisation" },
            ],
        });
        await waitFor(() => expect(onFermer).toHaveBeenCalledWith(true));
    });
});

describe("[.mark] the establishment a test plays (E3)", () => {
    it("is hidden without establishments, and offers them otherwise", async () => {
        m.get.mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: [] } });
        const { unmount } = render(
            <FournisseurLangue>
                <ChoixEtablissementEssai valeur="" onChange={vi.fn()} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(m.get).toHaveBeenCalled());
        expect(screen.queryByTestId("choix-etablissement-essai")).toBeNull();
        unmount();
        m.get.mockResolvedValue({ data: { format: "etablissements-mark", version: 1, etablissements: [CREIL] } });
        const onChange = vi.fn();
        render(
            <FournisseurLangue>
                <ChoixEtablissementEssai valeur="" onChange={onChange} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(screen.getByTestId("choix-etablissement-essai")).toBeTruthy());
        fireEvent.change(screen.getByTestId("choix-etablissement-essai").querySelector("select")!, { target: { value: "creil" } });
        expect(onChange).toHaveBeenCalledWith("creil");
    });
});
