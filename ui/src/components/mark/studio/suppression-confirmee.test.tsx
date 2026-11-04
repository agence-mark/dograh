/**
 * [.mark] R3 M3 : la suppression se fait en deux temps. Le premier clic ne supprime rien ; « Non » referme ; « Oui, supprimer »
 * supprime une seule fois. La fenêtre centrée suit la même règle.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmerSuppression, SuppressionConfirmee } from "./suppression-confirmee";

afterEach(() => cleanup());

describe("SuppressionConfirmee", () => {
    it("le premier clic demande, « Non » referme sans supprimer, « Oui » supprime une fois", () => {
        const supprimer = vi.fn();
        render(<SuppressionConfirmee onConfirmer={supprimer}>Delete the role</SuppressionConfirmee>);
        fireEvent.click(screen.getByText("Delete the role"));
        expect(supprimer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("No"));
        expect(supprimer).not.toHaveBeenCalled();
        expect(screen.getByText("Delete the role")).toBeTruthy();
        fireEvent.click(screen.getByText("Delete the role"));
        fireEvent.click(screen.getByText("Yes, delete"));
        expect(supprimer).toHaveBeenCalledTimes(1);
    });
});

describe("ConfirmerSuppression", () => {
    it("ne supprime qu'au bouton « Supprimer » ; « Annuler » ferme", () => {
        const supprimer = vi.fn();
        const fermer = vi.fn();
        render(<ConfirmerSuppression ouvert titre="Delete?" onConfirmer={supprimer} onFermer={fermer} />);
        fireEvent.click(screen.getByText("Cancel"));
        expect(fermer).toHaveBeenCalled();
        expect(supprimer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByText("Delete"));
        expect(supprimer).toHaveBeenCalledTimes(1);
    });
});
