/**
 * [.mark] The modal of an object of the agent (cloture-code-avant-migration, lot F7), rendered.
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
import { ModaleObjet, rendreObjet } from "./ModaleObjet";

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
            <ModaleObjet objet={objet} plafond={plafond} etablissements={[{ id: "nord", nom: "Nord" }]} onFermer={onFermer} />
        </FournisseurLangue>,
    );
    return onFermer;
};

describe("The modal of an object", () => {
    it("renders the text the agent receives exactly as the server does", () => {
        expect(rendreObjet(MARQUES)).toBe("Marque | Note\nEdilkamin | suivie\nRika | ");
        expect(rendreObjet({ forme: "valeur", valeur: "35" })).toBe("35");
        expect(rendreObjet({ forme: "liste", colonnes: [], lignes: [] })).toBe("");
    });

    it("sends the whole object to PUT, cells following a renamed column, ids kept", async () => {
        m.put.mockResolvedValue({ data: MARQUES });
        const fermer = ouvrir(MARQUES);
        fireEvent.change(screen.getByLabelText(/^(Marque|Marque) 2$/), { target: { value: "Jøtul" } });
        fireEvent.change(screen.getByLabelText(/^(Column|Colonne) 2$/), { target: { value: "Remarque" } });
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.put).toHaveBeenCalledTimes(1));
        const { path, body } = m.put.mock.calls[0][0];
        expect(path).toEqual({ objet_id: 4 });
        expect(body.colonnes.map((c: { id: number; libelle: string }) => [c.id, c.libelle])).toEqual([[10, "Marque"], [11, "Remarque"]]);
        expect(body.lignes).toEqual([
            { id: 20, ordre: 1, valeurs: { Marque: "Edilkamin", Remarque: "suivie" } },
            { id: 21, ordre: 2, valeurs: { Marque: "Jøtul" } },
        ]);
        expect(body).toMatchObject({ nom: "marques", forme: "liste", etablissement: "nord", type: null, valeur: null });
        await waitFor(() => expect(fermer).toHaveBeenCalledWith(true));
    });

    it("creates a single value with its type and value, no columns", async () => {
        m.post.mockResolvedValue({ data: { id: 9 } });
        ouvrir(null);
        fireEvent.change(document.getElementById("objet-nom") as HTMLElement, { target: { value: "frais" } });
        fireEvent.change(document.getElementById("objet-libelle") as HTMLElement, { target: { value: "Frais" } });
        fireEvent.change(document.getElementById("objet-valeur") as HTMLElement, { target: { value: "35" } });
        fireEvent.click(screen.getByTestId("enregistrer-objet"));
        await waitFor(() => expect(m.post).toHaveBeenCalledTimes(1));
        expect(m.post.mock.calls[0][0].body).toEqual({
            nom: "frais", libelle: "Frais", description: null, forme: "valeur", type: "texte", valeur: "35",
            etablissement: null, colonnes: [], lignes: [],
        });
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

    it("puts the padlock on .mark's columns only", () => {
        ouvrir(MARQUES);
        expect(document.querySelector('[data-colonne="Marque"] svg[aria-label]')).not.toBeNull();
        expect(document.querySelector('[data-colonne="Note"] svg[aria-label]')).toBeNull();
    });
});
