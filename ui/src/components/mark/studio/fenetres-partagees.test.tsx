/**
 * [.mark] R3 M4 : les deux fenêtres partagées ne jettent jamais une saisie sans demander, et ne se ferment au « Enregistrer »
 * qu'au succès. Mineurs 6 et 7 : la lecture est une propriété, le champ secret n'est pas rempli par le navigateur.
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FenetreChamps } from "./fenetre-champs";
import { FenetreOnglets } from "./fenetre-onglets";

afterEach(() => cleanup());

const sections = [{ champs: [{ id: "nom", t: "texte" as const, l: "Name", v: "" }] }];
const saisir = (valeur: string) => fireEvent.change(screen.getByLabelText("Name"), { target: { value: valeur } });

describe("FenetreChamps", () => {
    it("sans saisie, « Annuler » ferme tout de suite", () => {
        const fermer = vi.fn();
        render(<FenetreChamps ouverte fermer={fermer} titre="T" sections={sections} valider="Save" />);
        fireEvent.click(screen.getByText("Cancel"));
        expect(fermer).toHaveBeenCalledTimes(1);
    });

    it("avec une saisie, « Annuler » et Échap demandent avant de jeter ; « Continuer » garde, « Abandonner » ferme", async () => {
        const fermer = vi.fn();
        render(<FenetreChamps ouverte fermer={fermer} titre="T" sections={sections} valider="Save" />);
        saisir("abc");
        fireEvent.click(screen.getByText("Cancel"));
        expect(fermer).not.toHaveBeenCalled();
        expect(screen.getByRole("alert").textContent).toMatch(/Discard your changes/);
        fireEvent.click(screen.getByText("Keep editing"));
        expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("abc");
        fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
        await waitFor(() => expect(screen.queryByText("Discard")).toBeTruthy());
        expect(fermer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("Discard"));
        expect(fermer).toHaveBeenCalledTimes(1);
    });

    it("l'enregistrement qui échoue garde la fenêtre et la saisie ; celui qui réussit ferme", async () => {
        const fermer = vi.fn();
        let reponse: boolean | Promise<boolean> = Promise.resolve(false);
        render(<FenetreChamps ouverte fermer={fermer} titre="T" sections={sections} valider="Save" onValider={() => reponse} />);
        saisir("abc");
        await act(async () => fireEvent.click(screen.getByText("Save")));
        expect(fermer).not.toHaveBeenCalled();
        expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("abc");
        reponse = Promise.resolve(true);
        await act(async () => fireEvent.click(screen.getByText("Save")));
        expect(fermer).toHaveBeenCalledTimes(1);
    });

    it("une promesse rejetée garde aussi la fenêtre", async () => {
        const fermer = vi.fn();
        render(<FenetreChamps ouverte fermer={fermer} titre="T" sections={sections} valider="Save" onValider={() => Promise.reject(new Error("panne"))} />);
        saisir("abc");
        await act(async () => fireEvent.click(screen.getByText("Save")));
        expect(fermer).not.toHaveBeenCalled();
    });

    it("la lecture est une propriété : un bouton « Close » sans elle reste une fenêtre à enregistrer", () => {
        const { unmount } = render(<FenetreChamps ouverte fermer={vi.fn()} titre="T" sections={sections} valider="Close" />);
        expect(screen.queryByText("Cancel")).toBeTruthy();
        unmount();
        render(<FenetreChamps ouverte lecture fermer={vi.fn()} titre="T" sections={sections} valider="Open" />);
        expect(screen.queryByText("Cancel")).toBeNull();
    });

    it("le champ secret n'est jamais rempli par le navigateur", () => {
        render(<FenetreChamps ouverte fermer={vi.fn()} titre="T" sections={[{ champs: [{ id: "cle", t: "secret", l: "Key" }] }]} valider="Save" />);
        expect(screen.getByLabelText("Key").getAttribute("autocomplete")).toBe("new-password");
    });
});

describe("FenetreOnglets", () => {
    it("modifiée, « Annuler » demande avant de fermer", () => {
        const fermer = vi.fn();
        render(
            <FenetreOnglets fermer={fermer} titre="T" modifie>
                x
            </FenetreOnglets>,
        );
        fireEvent.click(screen.getByText("Cancel"));
        expect(fermer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("Discard"));
        expect(fermer).toHaveBeenCalledTimes(1);
    });

    it("non modifiée, elle ferme tout de suite", () => {
        const fermer = vi.fn();
        render(
            <FenetreOnglets fermer={fermer} titre="T">
                x
            </FenetreOnglets>,
        );
        fireEvent.click(screen.getByText("Cancel"));
        expect(fermer).toHaveBeenCalledTimes(1);
    });
});
