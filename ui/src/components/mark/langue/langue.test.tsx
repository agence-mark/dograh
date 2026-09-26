/**
 * [.mark] The FR / EN switch: French until the user chooses, the choice kept
 * by the browser and found again after a reload (decisions D10, D12).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { BoutonLangue } from "./BoutonLangue";
import { CLE_LANGUE, FournisseurLangue, useLangue } from "./langue";

const Temoin = () => {
    const { t } = useLangue();
    return <p data-testid="temoin">{t({ en: "Save", fr: "Enregistrer" })}</p>;
};

const ouvrir = () =>
    render(
        <FournisseurLangue>
            <BoutonLangue />
            <Temoin />
        </FournisseurLangue>,
    );

beforeEach(() => window.localStorage.clear());
afterEach(cleanup);

describe("[.mark] language of the screen", () => {
    it("opens in French when the user never chose (D12)", () => {
        ouvrir();
        expect(screen.getByTestId("temoin").textContent).toBe("Enregistrer");
        expect(document.documentElement.lang).toBe("fr");
        expect(screen.getByRole("button", { name: "Français" }).getAttribute("aria-pressed")).toBe("true");
    });

    it("switches to English and back", () => {
        ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "English" }));
        expect(screen.getByTestId("temoin").textContent).toBe("Save");
        expect(document.documentElement.lang).toBe("en");
        fireEvent.click(screen.getByRole("button", { name: "Français" }));
        expect(screen.getByTestId("temoin").textContent).toBe("Enregistrer");
    });

    it("finds the choice again after a reload", () => {
        ouvrir();
        fireEvent.click(screen.getByRole("button", { name: "English" }));
        expect(window.localStorage.getItem(CLE_LANGUE)).toBe("en");
        cleanup();
        // A new provider is a reloaded page: it reads the browser again.
        ouvrir();
        expect(screen.getByTestId("temoin").textContent).toBe("Save");
    });

    it("ignores a stored value that is not a language", () => {
        window.localStorage.setItem(CLE_LANGUE, "de");
        ouvrir();
        expect(screen.getByTestId("temoin").textContent).toBe("Enregistrer");
    });

    it("stays in English outside the provider, where the components' own tests render them", () => {
        render(<Temoin />);
        expect(screen.getByTestId("temoin").textContent).toBe("Save");
    });
});
