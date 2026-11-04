/**
 * [.mark] Partie 3, lot 15 (SE-25, L-2) : les phrases d'explication se disent dans un « ! », pas en ligne.
 *
 *   - `FenetreOnglets` : la prop `info` met la phrase dans le « ! » du titre ; `sous` reste pour une donnée
 *     (la fenêtre « Nouvel outil » et celle d'un logiciel s'en servent) ;
 *   - les notes sous les champs de l'éditeur du site : voir `site/EditeurWidget.test.tsx`.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { FenetreOnglets } from "./fenetre-onglets";

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

afterEach(cleanup);

const monter = (noeud: React.ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

describe("[.mark] lot 15 : les phrases dans un « ! » (L-2)", () => {
    it("`info` va dans le « ! » du titre, `sous` reste une ligne de donnée", () => {
        monter(
            <FenetreOnglets fermer={vi.fn()} titre="Brancher Agenda" info="Un compte de test de .mark." sous="google-agenda · Prêt" valider={null}>
                <p>corps</p>
            </FenetreOnglets>,
        );
        const titre = screen.getByRole("heading", { name: /Brancher Agenda/ });
        expect(titre.querySelector('[data-slot="tooltip-trigger"]')).toBeTruthy(); // le « ! » est dans le titre
        expect(screen.getByText("google-agenda · Prêt")).toBeTruthy();
        // La phrase n'est pas une ligne visible sous le titre : elle n'apparaît qu'au survol du « ! ».
        expect(screen.queryByText("Un compte de test de .mark.")).toBeNull();
    });

    it("sans `info`, pas de « ! » dans le titre", () => {
        monter(
            <FenetreOnglets fermer={vi.fn()} titre="Un titre" valider={null}>
                <p>corps</p>
            </FenetreOnglets>,
        );
        expect(screen.getByRole("heading", { name: "Un titre" }).querySelector('[data-slot="tooltip-trigger"]')).toBeNull();
    });
});
