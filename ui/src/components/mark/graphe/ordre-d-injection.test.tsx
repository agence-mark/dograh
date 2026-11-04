/**
 * [.mark] RA-B (R4d) : la liste affichée dans la fiche de l'étape de départ est celle du serveur, dans le même ordre.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ORDRE_D_INJECTION, OrdreDInjection } from "./OrdreDInjection";

afterEach(cleanup);

describe("OrdreDInjection", () => {
    it("garde l'ordre écrit par le serveur", () => {
        expect(ORDRE_D_INJECTION.map((c) => c.id)).toEqual(["defaut", "organisation", "etablissement", "objets", "lecture", "appel"]);
    });
    it("affiche les six couches et la règle", () => {
        render(<OrdreDInjection />);
        const items = screen.getByTestId("ordre-d-injection").querySelectorAll("li");
        expect(items).toHaveLength(6);
        expect(items[4].getAttribute("data-couche")).toBe("lecture");
    });
});
