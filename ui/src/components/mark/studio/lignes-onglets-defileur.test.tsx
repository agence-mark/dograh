/**
 * [.mark] SA-V : toute rangée d'onglets passe par `Defileur` (règle de l'écran, Evan 04/11 : « jamais un onglet caché »).
 * Avant, la ligne d'onglets de la barre d'un agent et celle de la fenêtre d'un nœud défilaient sans flèche : « Appels » était
 * rogné et « Versions » disparaissait dès que « Non enregistré » et « Enregistrer » prenaient la place.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OngletsAgent } from "../agent/OngletsAgent";
import { FournisseurLangue } from "../langue/langue";
import { OngletsNoeud } from "../graphe/OngletsNoeud";

vi.mock("next/link", () => ({
    default: ({ href, children, ...reste }: { href: string; children: React.ReactNode }) => (
        <a href={href} {...reste}>
            {children}
        </a>
    ),
}));
vi.mock("../site/useAgentDeSite", () => ({ useAgentDeSite: () => false }));
afterEach(cleanup);

describe("les lignes d'onglets passent par Defileur", () => {
    it("la barre d'un agent", () => {
        render(
            <FournisseurLangue>
                <OngletsAgent agentId={7} actif="parcours" />
            </FournisseurLangue>,
        );
        for (const onglet of screen.getAllByRole("tab")) expect(onglet.closest("[data-defileur]")).not.toBeNull();
    });

    it("la fenêtre d'un nœud", () => {
        render(
            <FournisseurLangue>
                <OngletsNoeud
                    sections={[
                        { id: "conversation", contenu: <p>a</p> },
                        { id: "donnees", contenu: <p>b</p> },
                    ]}
                />
            </FournisseurLangue>,
        );
        for (const onglet of screen.getAllByRole("tab")) expect(onglet.closest("[data-defileur]")).not.toBeNull();
    });
});
