/**
 * [.mark] Partie 3, sous-lot 21 : la fenêtre de la transition (maquette `FenetreTransition`). Hors du fournisseur de langue,
 * l'écran parle anglais (convention des tests).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FlowEdgeData } from "@/components/flow/types";

import { FenetreTransition } from "./FenetreTransition";

afterEach(cleanup);

const DATA: FlowEdgeData = { label: "Urgence", condition: "Une urgence.", condition_sur_la_fiche: { champ: "motif", vaut: "urgence" } };

function monter(props: Partial<Parameters<typeof FenetreTransition>[0]> = {}) {
    const onSave = vi.fn().mockResolvedValue(undefined);
    const fermer = vi.fn();
    render(
        <FenetreTransition
            ouverte
            fermer={fermer}
            data={DATA}
            etape={{ nom: "Accueil", qui: "choix" }}
            autreSinon={false}
            enregistrements={[]}
            onSave={onSave}
            onDelete={vi.fn()}
            {...props}
        />,
    );
    return { onSave, fermer };
}

const genre = (id: string) => document.querySelector(`[data-genre="${id}"]`) as HTMLElement;
const enregistrer = () => fireEvent.click(screen.getByRole("button", { name: "Save" }));

describe("FenetreTransition", () => {
    it("montre qui décide, hérité de l'étape, et lit la condition d'avant comme une règle", () => {
        monter();
        expect(screen.getByText("inherited from step « Accueil »")).toBeTruthy();
        expect(screen.getByText("The record, then the arbiter")).toBeTruthy();
        expect(genre("regles").getAttribute("aria-checked")).toBe("true");
        const regle = document.querySelector('[data-regle="0"]') as HTMLElement;
        expect((within(regle).getByLabelText("Field") as HTMLInputElement).value).toBe("motif");
        expect((within(regle).getByLabelText("Value") as HTMLInputElement).value).toBe("urgence");
    });

    it("sans rien toucher, l'enregistrement rend la condition d'avant à l'identique (aucun champ perdu)", async () => {
        const { onSave, fermer } = monter({ data: { ...DATA, identifiant: "urgence", transition_speech: "Un instant.", transition_speech_type: "text" } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toEqual({
            label: "Urgence",
            condition: "Une urgence.",
            identifiant: "urgence",
            condition_sur_la_fiche: { champ: "motif", vaut: "urgence" },
            transition_speech: "Un instant.",
            transition_speech_type: "text",
            transition_speech_recording_id: undefined,
        });
        expect(onSave.mock.calls[0][1]).toBeUndefined();
        await waitFor(() => expect(fermer).toHaveBeenCalled());
    });

    it("ajoute une règle d'outil, « au moins une », et l'écrit dans la même condition", async () => {
        const { onSave } = monter();
        fireEvent.click(screen.getByRole("button", { name: /Add a rule/ }));
        fireEvent.click(screen.getByRole("button", { name: "At least one" }));
        // La nouvelle règle (fiche par défaut) : on la remplit.
        const regle = document.querySelector('[data-regle="1"]') as HTMLElement;
        fireEvent.change(within(regle).getByLabelText("Field"), { target: { value: "contrat" } });
        fireEvent.change(within(regle).getByLabelText("Value"), { target: { value: "souscrit" } });
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0].condition_sur_la_fiche).toEqual({
            regles: [
                { source: "fiche", champ: "motif", comparaison: "est", valeur: "urgence" },
                { source: "fiche", champ: "contrat", comparaison: "est", valeur: "souscrit" },
            ],
            combien: "au_moins_une",
        });
    });

    it("une règle incomplète : la faute s'écrit sous la règle, rien n'est enregistré", async () => {
        const { onSave } = monter();
        fireEvent.change(within(document.querySelector('[data-regle="0"]') as HTMLElement).getByLabelText("Value"), { target: { value: "" } });
        enregistrer();
        expect(await screen.findByText("Enter the value to compare.")).toBeTruthy();
        expect(onSave).not.toHaveBeenCalled();
    });

    it("sinon et toujours s'enregistrent ; une seconde « sinon » sur l'étape est refusée sous le champ", async () => {
        const premier = monter();
        fireEvent.click(genre("toujours"));
        enregistrer();
        await waitFor(() => expect(premier.onSave).toHaveBeenCalled());
        expect(premier.onSave.mock.calls[0][0].condition_sur_la_fiche).toEqual({ toujours: true });
        cleanup();

        const second = monter({ autreSinon: true });
        fireEvent.click(genre("sinon"));
        enregistrer();
        expect(await screen.findByText("This step already has an « Otherwise » link.")).toBeTruthy();
        expect(second.onSave).not.toHaveBeenCalled();
    });

    it("le modèle décide à l'étape : « sans effet », et la correction fait décider la fiche avec la liaison", async () => {
        const { onSave } = monter({ etape: { nom: "Accueil", qui: "agent" } });
        expect(document.querySelector('[data-section="sans-effet"]')).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Let the record decide on this step" }));
        expect(document.querySelector('[data-section="sans-effet"]')).toBeNull();
        expect(screen.getByText("The record, then the arbiter")).toBeTruthy();
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][1]).toBe("choix");
    });

    it("« une intention » retire la condition du code (le modèle juge seul, comme avant)", async () => {
        const { onSave } = monter();
        fireEvent.click(genre("modele"));
        expect(document.querySelector('[data-section="regles"]')).toBeNull();
        enregistrer();
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0].condition_sur_la_fiche).toBeUndefined();
    });

    it("des changements non enregistrés : on prévient avant de fermer", () => {
        const { fermer } = monter();
        fireEvent.click(genre("sinon"));
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(screen.getByText("Discard your changes?")).toBeTruthy();
        expect(fermer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Discard" }));
        expect(fermer).toHaveBeenCalled();
    });

    it("supprimer la liaison demande une confirmation en place", () => {
        const onDelete = vi.fn();
        const { fermer } = monter({ onDelete });
        fireEvent.click(screen.getByRole("button", { name: /Delete the link/ }));
        expect(onDelete).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
        expect(onDelete).toHaveBeenCalled();
        expect(fermer).toHaveBeenCalled();
    });

    it("le libellé et la condition du modèle restent exigés", async () => {
        const { onSave } = monter();
        fireEvent.change(screen.getByLabelText("Label of the transition"), { target: { value: " " } });
        fireEvent.change(screen.getByLabelText("Condition (for the model)"), { target: { value: "" } });
        enregistrer();
        expect(await screen.findByText("A link needs a label.")).toBeTruthy();
        expect(screen.getByText("Describe when the model takes this link.")).toBeTruthy();
        expect(onSave).not.toHaveBeenCalled();
    });
});
