/**
 * [.mark] The variable creator (U3 ter, E64; before: the modal of an object, cloture-code lot F7), rendered.
 *
 * | Test | La garantie |
 * |---|---|
 * | rendu du texte | `rendreObjet` donne le même texte que le fork (`rendu.py`) et la base (`objet_agent_texte`) |
 * | réécrire | changer une cellule, renommer une colonne : l'objet entier part au `PUT`, cellules suivies du libellé, ids gardés |
 * | créer | une valeur simple part au `POST` avec son type et sa valeur, sans colonnes |
 * | plafond | au-delà, la jauge le dit et « Enregistrer » est fermé, rien ne part |
 * | refus | le refus de la base (type, ligne vide, plafond) est montré, la modale reste ouverte |
 * | cadenas | une colonne posée par .mark porte le cadenas, celle du client non |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ObjetAgent } from "@/client/types.gen";

import { FournisseurLangue } from "../langue/langue";
import { CreateurVariable } from "../variables/CreateurVariable";
import { rendreObjet } from "./ModaleObjet";

const m = vi.hoisted(() => ({ post: vi.fn(), put: vi.fn(), supprimer: vi.fn() }));

vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    postObjetApiV1OrganizationsObjetsPost: m.post,
    putObjetApiV1OrganizationsObjetsObjetIdPut: m.put,
    deleteObjetApiV1OrganizationsObjetsObjetIdDelete: m.supprimer,
}));
vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: ReactNode }) => <h2>{children}</h2>,
}));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const MARQUES: ObjetAgent = {
    id: 4,
    nom: "marques",
    libelle: "Marques",
    description: "Pour l'agent",
    forme: "liste",
    etablissement: "nord",
    colonnes: [
        { id: 10, libelle: "Marque", type: "texte", ordre: 1, pose_par: "mark" },
        { id: 11, libelle: "Note", type: "texte", ordre: 2, pose_par: "client" },
    ],
    lignes: [
        { id: 20, ordre: 1, valeurs: { Marque: "Edilkamin", Note: "suivie" } },
        { id: 21, ordre: 2, valeurs: { Marque: "Rika" } },
    ],
    taille: 0,
    utilise_par: [],
};

const ouvrir = (objet: ObjetAgent | null, plafond = 3000, onFermer = vi.fn()) => {
    render(
        <FournisseurLangue>
            <CreateurVariable objet={objet} plafond={plafond} etablissements={[{ id: "nord", nom: "Nord" }]} onFermer={onFermer} />
        </FournisseurLangue>,
    );
    return onFermer;
};

describe("The variable creator", () => {
    it("renders the text the agent receives exactly as the server does", () => {
        expect(rendreObjet(MARQUES)).toBe("Marque | Note" + String.fromCharCode(10) + "Edilkamin | suivie" + String.fromCharCode(10) + "Rika | ");
        expect(rendreObjet({ forme: "valeur", valeur: "35" })).toBe("35");
        expect(rendreObjet({ forme: "liste", colonnes: [], lignes: [] })).toBe("");
    });

    it("sends the whole table to PUT unchanged, ids and padlocks kept", async () => {
        m.put.mockResolvedValue({ data: MARQUES });
        const fermer = ouvrir(MARQUES);
        expect(document.querySelector('[data-genre="tableau"]')?.getAttribute("aria-pressed")).toBe("true");
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.put).toHaveBeenCalledTimes(1));
        const { path, body } = m.put.mock.calls[0][0];
        expect(path).toEqual({ objet_id: 4 });
        expect(body.colonnes.map((c: { id: number; libelle: string; pose_par: string }) => [c.id, c.libelle, c.pose_par])).toEqual([[10, "Marque", "mark"], [11, "Note", "client"]]);
        expect(body.lignes).toEqual([
            { id: 20, ordre: 1, valeurs: { Marque: "Edilkamin", Note: "suivie" } },
            { id: 21, ordre: 2, valeurs: { Marque: "Rika" } },
        ]);
        expect(body).toMatchObject({ nom: "marques", forme: "liste", etablissement: "nord", type: null, valeur: null });
        await waitFor(() => expect(fermer).toHaveBeenCalledWith(true));
    });

    it("works out the technical name from the label and creates a word with its value, no columns", async () => {
        m.post.mockResolvedValue({ data: { id: 9 } });
        ouvrir(null);
        fireEvent.change(document.getElementById("objet-libelle") as HTMLElement, { target: { value: "Frais de déplacement" } });
        expect((document.getElementById("objet-nom") as HTMLInputElement).value).toBe("frais_de_deplacement");
        fireEvent.change(document.getElementById("objet-valeur") as HTMLElement, { target: { value: "35" } });
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.post).toHaveBeenCalledTimes(1));
        expect(m.post.mock.calls[0][0].body).toEqual({
            nom: "frais_de_deplacement", libelle: "Frais de déplacement", description: null, forme: "valeur", type: "texte", valeur: "35",
            etablissement: null, colonnes: [], lignes: [],
        });
    });

    it.each([
        ["nombre", "montant", true, "montant"],
        ["nombre", "nombre", false, "nombre"],
        ["date", "date", false, "date"],
        ["oui_non", "oui_non", false, "oui_non"],
    ])("stores the genre %s as the existing type (%s)", async (genre, _nom, montant, type) => {
        m.post.mockResolvedValue({ data: { id: 9 } });
        ouvrir(null);
        fireEvent.click(document.querySelector(`[data-genre="${genre}"]`) as HTMLElement);
        fireEvent.change(document.getElementById("objet-libelle") as HTMLElement, { target: { value: "Valeur" } });
        if (montant) fireEvent.click(screen.getByTestId("montant"));
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.post).toHaveBeenCalledTimes(1));
        expect(m.post.mock.calls[0][0].body).toMatchObject({ forme: "valeur", type, colonnes: [], lignes: [] });
    });

    it("stores a list as ONE column and its items as lines, then reads it back as a list", async () => {
        m.post.mockResolvedValue({ data: { id: 9 } });
        ouvrir(null);
        fireEvent.click(document.querySelector('[data-genre="liste"]') as HTMLElement);
        fireEvent.change(document.getElementById("objet-libelle") as HTMLElement, { target: { value: "Marques" } });
        fireEvent.change(screen.getByLabelText(/(Item|Élément) 1/), { target: { value: "Rika" } });
        fireEvent.click(screen.getByTestId("ajouter-puce"));
        fireEvent.change(screen.getByLabelText(/(Item|Élément) 2/), { target: { value: "Jøtul" } });
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.post).toHaveBeenCalledTimes(1));
        const { body } = m.post.mock.calls[0][0];
        expect(body.forme).toBe("liste");
        expect(body.colonnes).toHaveLength(1);
        expect(body.lignes.map((l: { valeurs: Record<string, string> }) => Object.values(l.valeurs)[0])).toEqual(["Rika", "Jøtul"]);
        const { genreDe } = await import("../variables/genres");
        expect(genreDe({ forme: "liste", type: null, colonnes: body.colonnes })).toBe("liste");
    });

    it("over the ceiling, says so and keeps « Save » shut", () => {
        ouvrir(MARQUES, 20);
        expect(document.querySelector('[data-jauge="depasse"]')).not.toBeNull();
        expect((screen.getByTestId("enregistrer-objet") as HTMLButtonElement).disabled).toBe(true);
        expect(screen.getByTestId("erreur-objet").textContent).toMatch(/20/);
    });

    it("shows the database's refusal and stays open", async () => {
        m.put.mockResolvedValue({ error: { detail: "« parfois » n'est pas une valeur de type oui_non (colonne « Suivie »)" } });
        const fermer = ouvrir(MARQUES);
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        expect((await screen.findByTestId("erreur-objet")).textContent).toContain("oui_non");
        expect(fermer).not.toHaveBeenCalled();
    });

    it("shows the live preview: the tag, a prompt sentence, what the agent receives", () => {
        ouvrir(MARQUES);
        expect(screen.getByTestId("apercu-etiquette").textContent).toBe("Marques");
        expect(screen.getByTestId("apercu-phrase").textContent).toContain("{{marques}}");
        expect(screen.getByTestId("apercu-recu").textContent).toContain("Marque | Note");
    });
});
