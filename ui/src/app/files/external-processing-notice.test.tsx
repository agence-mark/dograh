/**
 * [.mark] V2b : l'avis « traité par un service externe » de la fenêtre « Déposer un document ».
 *
 * Questions de ce fichier :
 *
 *     En fenêtre, l'avis passe-t-il dans le « ! » (jamais une note visible, jamais l'icône orange) ? Hors d'un
 *     déploiement auto-hébergé, ne montre-t-il rien ? Sans `enInfo`, l'ancien avis reste tel qu'il était ?
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ mode: "oss" }));
vi.mock("@/context/AppConfigContext", () => ({ useAppConfig: () => ({ config: { deploymentMode: m.mode } }) }));

import ExternalProcessingNotice from "./ExternalProcessingNotice";

afterEach(() => {
    cleanup();
    m.mode = "oss";
});

describe("l'avis de traitement externe", () => {
    it("en fenêtre : un « ! », aucune phrase visible, aucune icône orange", () => {
        const { container } = render(<ExternalProcessingNotice enInfo />);
        expect(screen.getByRole("button", { name: /More information|Précision/ })).toBeTruthy();
        expect(container.textContent).not.toMatch(/external service|service externe/i);
        expect(container.querySelector("[class*=signal-warn]")).toBeNull();
    });

    it("hors d'un déploiement auto-hébergé : rien", () => {
        m.mode = "saas";
        const { container } = render(<ExternalProcessingNotice enInfo />);
        expect(container.innerHTML).toBe("");
    });

    it("sans `enInfo`, l'avis d'origine reste", () => {
        render(<ExternalProcessingNotice />);
        expect(screen.getByText("Processed by an external service")).toBeTruthy();
    });
});
