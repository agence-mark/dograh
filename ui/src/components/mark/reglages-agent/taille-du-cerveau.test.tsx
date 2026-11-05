/**
 * [.mark] Lot « façon Tala par motif » (T3) : Réglages › Briques › « Taille supportée par le cerveau ».
 *
 * Questions de ce fichier :
 *
 *     Les deux seuils sont-ils en saisie libre et VIDES par défaut (aucun seuil) ? Une valeur s'enregistre en nombre, un champ vidé
 *     s'enregistre à `null` (aucun seuil), et une valeur hors bornes ou décimale n'est pas envoyée ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { TailleDuCerveau } from "./TailleDuCerveau";

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
afterEach(cleanup);

const rendre = (resolue: Partial<WorkflowConfigurations> = {}) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<TailleDuCerveau resolue={resolue as WorkflowConfigurations} workflowName="Agent" onSave={onSave} />);
    return onSave;
};

describe("la taille supportée par le cerveau", () => {
    it("deux champs libres, vides par défaut : aucun seuil", () => {
        rendre();
        for (const id of ["cerveau_plafond_prompt", "cerveau_poids_max"]) {
            const champ = document.getElementById(id) as HTMLInputElement;
            expect(champ.value).toBe("");
            expect(champ.placeholder).toBe("No threshold");
        }
        expect(screen.getAllByRole("button", { name: /Save the/ }).every((b) => b.hasAttribute("disabled"))).toBe(true);
    });

    it("une valeur s'enregistre en nombre, avec le reste des réglages", async () => {
        const onSave = rendre({ delai_garde_modele_s: 5 });
        fireEvent.change(document.getElementById("cerveau_poids_max")!, { target: { value: "9000" } });
        fireEvent.click(screen.getByRole("button", { name: "Save the heaviest reply" }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0]).toMatchObject({ cerveau_poids_max: 9000, delai_garde_modele_s: 5 });
    });

    it("vider un seuil l'enregistre à null : aucun seuil", async () => {
        const onSave = rendre({ cerveau_plafond_prompt: 6000 });
        const champ = document.getElementById("cerveau_plafond_prompt") as HTMLInputElement;
        expect(champ.value).toBe("6000");
        fireEvent.change(champ, { target: { value: "" } });
        fireEvent.click(screen.getByRole("button", { name: "Save the longest prompt" }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        expect(onSave.mock.calls[0][0].cerveau_plafond_prompt).toBeNull();
    });

    it("une valeur hors bornes ou décimale n'est pas envoyée", () => {
        rendre();
        const champ = document.getElementById("cerveau_plafond_prompt")!;
        fireEvent.change(champ, { target: { value: "0" } });
        expect(screen.getByRole("button", { name: "Save the longest prompt" }).hasAttribute("disabled")).toBe(true);
        fireEvent.change(champ, { target: { value: "12.5" } });
        expect(screen.getByRole("button", { name: "Save the longest prompt" }).hasAttribute("disabled")).toBe(true);
        expect(screen.getByText("Enter a whole number.")).toBeTruthy();
    });
});
