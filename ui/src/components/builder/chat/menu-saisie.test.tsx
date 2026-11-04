/**
 * [.mark] Partie 3, sous-lot 11 (SE-17, E-7) : les menus « @ » et « / » du composeur et le bouton « Copier » sous une réponse.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const AUTH = vi.hoisted(() => ({ user: { id: "u" }, loading: false }));
vi.mock("@/lib/auth", () => ({ useAuth: () => AUTH }));
vi.mock("@/client", () => ({
    getWorkflowsSummaryApiV1WorkflowSummaryGet: async () => ({ data: [{ id: 1, name: "Standard Nuances" }, { id: 2, name: "Chauffage Durand" }] }),
    listerLesRecettesApiV1BuilderRecettesGet: async () => ({ data: { recettes: [{ slug: "facon-tala", nom: "Façon Tala" }] } }),
}));
const echec = vi.hoisted(() => vi.fn());
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: { echec } }));

import { CopierLaReponse } from "./copier-la-reponse";
import { motEnCours, useEntreesDeSaisie, useMenuSaisie } from "./menu-saisie";

afterEach(() => {
    cleanup();
    echec.mockReset();
});

function Composeur() {
    const [texte, setTexte] = useState("");
    const entrees = useEntreesDeSaisie();
    const { menu, clavier } = useMenuSaisie(texte, setTexte, entrees);
    return (
        <div style={{ position: "relative" }}>
            {menu}
            <textarea aria-label="saisie" value={texte} onChange={(e) => setTexte(e.target.value)} onKeyDown={(e) => void clavier(e)} />
        </div>
    );
}

describe("mot en cours", () => {
    it("« @ » n'importe où, « / » seulement au tout début du message", () => {
        expect(motEnCours("bonjour @Stand")).toMatchObject({ signe: "@", q: "Stand", debut: 8 });
        expect(motEnCours("/test")).toMatchObject({ signe: "/", q: "test", debut: 0 });
        expect(motEnCours("bonjour /test")).toBeNull();
        expect(motEnCours("un mail a@b.fr")).toBeNull();
        expect(motEnCours("fini ")).toBeNull();
    });
});

describe("composeur du fil", () => {
    it("« @ » propose les vrais agents et recettes, filtre à la frappe et écrit le nom choisi", async () => {
        render(<Composeur />);
        const zone = screen.getByLabelText("saisie") as HTMLTextAreaElement;
        fireEvent.change(zone, { target: { value: "Reprends @" } });
        await waitFor(() => expect(document.querySelector('[data-menu-saisie="@"]')).not.toBeNull());
        const menu = document.querySelector('[data-menu-saisie="@"]') as HTMLElement;
        expect(menu.textContent).toContain("Standard Nuances");
        expect(menu.textContent).toContain("Façon Tala");
        fireEvent.change(zone, { target: { value: "Reprends @chauff" } });
        await waitFor(() => expect(document.querySelector('[data-menu-saisie="@"]')?.textContent).not.toContain("Standard Nuances"));
        fireEvent.keyDown(zone, { key: "Enter" });
        expect(zone.value).toBe("Reprends @Chauffage Durand ");
        expect(document.querySelector("[data-menu-saisie]")).toBeNull();
    });

    it("« / » au début propose des demandes types écrites en phrase ; Échap ferme le menu", async () => {
        render(<Composeur />);
        const zone = screen.getByLabelText("saisie") as HTMLTextAreaElement;
        fireEvent.change(zone, { target: { value: "/" } });
        const menu = await waitFor(() => document.querySelector('[data-menu-saisie="/"]') as HTMLElement);
        expect(menu.textContent).toContain("/tester");
        fireEvent.keyDown(zone, { key: "Escape" });
        expect(document.querySelector("[data-menu-saisie]")).toBeNull();
        fireEvent.change(zone, { target: { value: "/ana" } });
        fireEvent.keyDown(zone, { key: "ArrowDown" });
        fireEvent.keyDown(zone, { key: "Enter" });
        expect(zone.value).toBe("Analyze the real calls of the last week and tell me the causes that come back.");
    });
});

describe("copier la réponse", () => {
    it("copie le texte tel quel puis le dit ; un presse-papiers refusé le dit par une notification", async () => {
        const ecrire = vi.fn(async () => undefined);
        Object.assign(navigator, { clipboard: { writeText: ecrire } });
        render(<CopierLaReponse texte="Bonjour **toi**" />);
        fireEvent.click(screen.getByRole("button", { name: "Copy" }));
        await waitFor(() => expect(ecrire).toHaveBeenCalledWith("Bonjour **toi**"));
        await screen.findByRole("button", { name: "Copied" });
        ecrire.mockRejectedValueOnce(new Error("non"));
        cleanup();
        render(<CopierLaReponse texte="x" />);
        fireEvent.click(screen.getByRole("button", { name: "Copy" }));
        await waitFor(() => expect(echec).toHaveBeenCalled());
    });
});
