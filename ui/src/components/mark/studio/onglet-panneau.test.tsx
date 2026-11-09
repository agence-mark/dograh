/**
 * Clôture D1 (É29/É30) : le builder et l'essai sont des onglets du panneau unique de droite, pas des panneaux flottants.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OngletDuPanneau } from "./onglet-panneau";
import { ContextePanneau, PanneauDroit, useEtatPanneau } from "./panneau-droit";

afterEach(() => cleanup());

function Cadre({ builder, essai }: { builder: boolean; essai: boolean }) {
    const etat = useEtatPanneau();
    return (
        <ContextePanneau.Provider value={etat}>
            <main>
                {builder && (
                    <OngletDuPanneau id="builder-ia" titre="Builder IA" fermer={() => {}}>
                        <p>chat du builder</p>
                    </OngletDuPanneau>
                )}
                {essai && (
                    <OngletDuPanneau id="essai-agent" titre="Essai" fermer={() => {}}>
                        <p>essai clavier</p>
                    </OngletDuPanneau>
                )}
            </main>
            <PanneauDroit etat={etat} dessus={false} largeurAffichee={etat.largeur} />
        </ContextePanneau.Provider>
    );
}

describe("onglets du builder et de l'essai", () => {
    it("deux onglets dans UN panneau, le dernier ouvert devant, l'autre gardé monté", () => {
        const { rerender } = render(<Cadre builder essai={false} />);
        rerender(<Cadre builder essai />);
        expect(screen.getAllByRole("tab").map((o) => o.textContent)).toEqual(["Builder IA", "Essai"]);
        expect(document.querySelectorAll("[data-panneau-droit]")).toHaveLength(1);
        expect((screen.getByText("essai clavier").closest("[data-onglet-panneau]") as HTMLElement).hidden).toBe(false);
        expect((screen.getByText("chat du builder").closest("[data-onglet-panneau]") as HTMLElement).hidden).toBe(true);
        fireEvent.click(screen.getByRole("tab", { name: /Builder IA/ }));
        expect((screen.getByText("chat du builder").closest("[data-onglet-panneau]") as HTMLElement).hidden).toBe(false);
    });
    it("l'onglet se retire quand le contenu est démonté", () => {
        const { rerender } = render(<Cadre builder essai />);
        rerender(<Cadre builder essai={false} />);
        expect(screen.getAllByRole("tab")).toHaveLength(1);
    });
});
