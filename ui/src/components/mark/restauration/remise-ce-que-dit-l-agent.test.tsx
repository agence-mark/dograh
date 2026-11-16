/**
 * [.mark] Lot 26, M46 (F7) : le panneau d'une remise montre toujours le bloc « Ce que dit l'agent » (libellé au-dessus, phrase dans un encadré),
 * comme la maquette ; sans phrase écrite, il dit ce que l'agent dira vraiment (le nom de la remise), jamais un trou.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RemiseLue } from "./donnees-salle";
import { PanneauDetail } from "./remises";

vi.mock("../langue/langue", () => ({ useLangue: () => ({ langue: "fr", t: (x: { fr: string }) => x.fr }) }));

const remise = (phrase: string | null): RemiseLue => ({
    id: 1, nom: "Deuxième pizza à moitié prix", mecanisme: "deuxieme_moitie_prix", declencheur: {}, effet: {}, perimetre: {}, cumul: "exclusive", limite: null,
    phrase, moment: null, debut: null, fin: null, etat: "active", ref_caisse: null, source: "portail", maj_le: "2026-11-16T10:00:00Z",
    utilisations: 0, ca_centimes: 0, remise_centimes: 0, dite: 0, acceptee: 0,
});

const rendre = (r: RemiseLue) =>
    render(<PanneauDetail r={r} etab={1} lectureSeule={false} resume="-4,00 €" fermer={() => undefined} poser={() => undefined} modifier={() => undefined} />);

describe("M46 : « Ce que dit l'agent » dans le panneau d'une remise", () => {
    afterEach(cleanup);
    it("la phrase écrite est montrée entre guillemets", () => {
        rendre(remise("Ce soir, la deuxième pizza est à moitié prix."));
        expect(screen.getByText("Ce que dit l'agent")).toBeTruthy();
        expect(screen.getByText(/« Ce soir, la deuxième pizza est à moitié prix\. »/)).toBeTruthy();
    });
    it("sans phrase, le bloc reste et dit que l'agent dit le nom de la remise", () => {
        rendre(remise(null));
        expect(screen.getByText("Ce que dit l'agent")).toBeTruthy();
        expect(screen.getByText(/Aucune phrase écrite/)).toBeTruthy();
    });
});
