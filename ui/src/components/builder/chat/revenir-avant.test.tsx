/**
 * [.mark] Partie 3, sous-lot 7 (SE-15) : la fenêtre « Revenir avant », une case par famille.
 *
 * Questions de ce fichier :
 *
 *     Toutes les familles gardées sont-elles cochées au départ, une famille non gardée grisée et dite ? Le vocabulaire et les objets
 *     disent qu'ils sont partagés par l'organisation, et les objets qu'aucun n'est supprimé ? La confirmation envoie-t-elle
 *     exactement les familles cochées, et se refuse-t-elle sans aucune case ? Un nom de ce qui change est montré, jamais une valeur ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FenetreRestauration } from "./FenetreRestauration";

const apercu = vi.hoisted(() => vi.fn());
vi.mock("@/client", () => ({
    apercuAvantDeRevenirApiV1BuilderAgentsWorkflowIdVersionsNumeroApercuGet: (o: unknown) => apercu(o),
}));

const FAMILLES = [
    { famille: "schema", disponible: true, partagee: false, change: true, details: [] },
    { famille: "phrases", disponible: true, partagee: false, change: true, details: ["outil_echoue"] },
    { famille: "reglages", disponible: true, partagee: false, change: true, details: ["relecture_des_numeros", "stt"] },
    { famille: "vocabulaire", disponible: true, partagee: true, change: false, details: [] },
    { famille: "objets", disponible: false, partagee: true, change: null, details: [] },
];
const APERCU = { numero: 4, cause: "publication", sera_perdu: [], sera_retrouve: [], total_perdu: 0, total_retrouve: 0, inchanges: 2, familles: FAMILLES };

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const ouvrir = async (confirmer = vi.fn(async () => undefined)) => {
    apercu.mockResolvedValue({ data: APERCU });
    render(<FenetreRestauration workflowId={9} numero={4} confirmer={confirmer} fermer={vi.fn()} />);
    const bloc = await screen.findByTestId("familles-a-restaurer");
    return { bloc, confirmer };
};

describe("la fenêtre Revenir avant", () => {
    it("coche au départ les familles gardées, grise et dit celle qui ne l'est pas, et montre des noms jamais des valeurs", async () => {
        const { bloc } = await ouvrir();
        for (const nom of ["Flow (steps and links)", "Code phrases", "Agent settings", "Trade vocabulary"]) {
            expect(within(bloc).getByRole("checkbox", { name: nom }).getAttribute("aria-checked")).toBe("true");
        }
        const objets = within(bloc).getByRole("checkbox", { name: "Agent objects" });
        expect(objets.hasAttribute("disabled") || objets.getAttribute("data-disabled") !== null).toBe(true);
        expect(bloc.textContent).toContain("not kept in this version");
        expect(bloc.textContent).toContain("relecture_des_numeros, stt");
        expect(bloc.textContent).toContain("outil_echoue");
        expect(bloc.textContent).toContain("no change"); // le vocabulaire est identique
        expect(bloc.textContent).toContain("shared by the whole organization");
    });

    it("envoie exactement les familles cochées", async () => {
        const { bloc, confirmer } = await ouvrir();
        fireEvent.click(within(bloc).getByRole("checkbox", { name: "Agent settings" }));
        fireEvent.click(within(bloc).getByRole("checkbox", { name: "Trade vocabulary" }));
        fireEvent.click(screen.getByText("Confirm and go back"));
        await waitFor(() => expect(confirmer).toHaveBeenCalledWith(["schema", "phrases"]));
    });

    it("se refuse sans aucune case cochée", async () => {
        const { bloc, confirmer } = await ouvrir();
        for (const nom of ["Flow (steps and links)", "Code phrases", "Agent settings", "Trade vocabulary"]) fireEvent.click(within(bloc).getByRole("checkbox", { name: nom }));
        const bouton = screen.getByText("Confirm and go back") as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.click(bouton);
        expect(confirmer).not.toHaveBeenCalled();
    });

    it("dit pour les objets qu'aucun n'est supprimé et nomme ceux ajoutés depuis", async () => {
        apercu.mockResolvedValue({
            data: { ...APERCU, familles: [...FAMILLES.slice(0, 4), { famille: "objets", disponible: true, partagee: true, change: true, details: ["horaires"], ajoutes_depuis: ["zone"] }] },
        });
        render(<FenetreRestauration workflowId={9} numero={4} confirmer={vi.fn()} fermer={vi.fn()} />);
        const bloc = await screen.findByTestId("familles-a-restaurer");
        expect(bloc.textContent).toContain("never deletes one added since");
        expect(bloc.textContent).toContain("added since, kept: zone");
    });
});
