/**
 * [.mark] Clôture SA-5 (É8, É35) : la barre des listes d'appels : la saisie part après une pause (pas une requête par lettre), le motif
 * choisi part tel quel, « Effacer les filtres » n'apparaît que s'il y a quelque chose à effacer et vide tout.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

vi.mock("@/components/mark/studio/liste-deroulante", async () => await import("@/components/mark/studio/liste-deroulante-natif-test"));

import { dureeLisible, PAUSE_DE_SAISIE_MS, RechercheAppels } from "./recherche-appels";

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
    cleanup();
    vi.useRealTimers();
    window.localStorage.clear();
});

const monter = (props: Partial<Parameters<typeof RechercheAppels>[0]> = {}) => {
    const onRecherche = vi.fn();
    const onMotif = vi.fn();
    render(
        <FournisseurLangue>
            <RechercheAppels recherche="" onRecherche={onRecherche} motif="" onMotif={onMotif} motifs={["Devis", "Dépannage"]} {...props} />
        </FournisseurLangue>,
    );
    return { onRecherche, onMotif };
};

describe("[.mark] la barre de recherche des appels", () => {
    it("envoie la saisie après une pause, une seule fois", () => {
        const { onRecherche } = monter();
        const champ = screen.getByLabelText("Chercher un mot");
        fireEvent.change(champ, { target: { value: "dev" } });
        fireEvent.change(champ, { target: { value: "devis" } });
        expect(onRecherche).not.toHaveBeenCalled();
        act(() => void vi.advanceTimersByTime(PAUSE_DE_SAISIE_MS + 10));
        expect(onRecherche).toHaveBeenCalledTimes(1);
        expect(onRecherche).toHaveBeenCalledWith("devis");
    });

    it("propose « Tous les motifs » puis les motifs du serveur, et envoie le choix", () => {
        const { onMotif } = monter();
        const liste = screen.getByLabelText("Motif") as HTMLSelectElement;
        expect(Array.from(liste.options).map((o) => o.textContent)).toEqual(["Tous les motifs", "Devis", "Dépannage"]);
        fireEvent.change(liste, { target: { value: "Devis" } });
        expect(onMotif).toHaveBeenCalledWith("Devis");
    });

    it("« Effacer les filtres » n'apparaît que s'il y a un filtre, et vide la saisie et le motif", () => {
        const premier = monter();
        expect(screen.queryByText("Effacer les filtres")).toBeNull();
        cleanup();
        const { onRecherche, onMotif } = monter({ motif: "Devis" });
        fireEvent.click(screen.getByText("Effacer les filtres"));
        expect(onRecherche).toHaveBeenCalledWith("");
        expect(onMotif).toHaveBeenCalledWith("");
        expect(premier.onRecherche).not.toHaveBeenCalled();
    });

    it("dit une durée lisible", () => {
        expect(dureeLisible(42)).toBe("42s");
        expect(dureeLisible(192)).toBe("3m 12s");
        expect(dureeLisible(120)).toBe("2m");
    });
});
