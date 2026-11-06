/**
 * [.mark] Partie 3, sous-lot 20 : la barre d'outils du graphe (annuler, rétablir, réorganiser, aimant, carte, statistiques,
 * recherche, empêcher les boucles) et la petite barre au survol d'une étape (suppression confirmée).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BarreAuSurvol } from "./BarreAuSurvol";
import { BarreOutilsGraphe, chercherLesEtapes, type EtapeCherchable } from "./BarreOutilsGraphe";

vi.mock("@xyflow/react", () => ({
    NodeToolbar: ({ children, isVisible }: { children: React.ReactNode; isVisible?: boolean }) => (isVisible ? <div data-testid="barre-survol">{children}</div> : null),
    Position: { Right: "right" },
}));

afterEach(() => cleanup());

const etapes: EtapeCherchable[] = [
    { id: "1", nom: "Accueil", type: "startCall" },
    { id: "2", nom: "Prise de rendez-vous", type: "agentNode" },
    { id: "3", nom: "Étape de clôture", type: "endCall" },
];

const base = () => ({
    lectureSeule: false,
    peutAnnuler: true,
    peutRetablir: false,
    onAnnuler: vi.fn(),
    onRetablir: vi.fn(),
    onReorganiser: vi.fn(),
    aimant: false,
    onAimant: vi.fn(),
    carte: true,
    onCarte: vi.fn(),
    stats: false,
    onStats: vi.fn(),
    appelsLus: null,
    boucles: false,
    onBoucles: vi.fn(),
    enBoucle: 0,
    etapes,
    onChoisirEtape: vi.fn(),
});

describe("recherche d'une étape", () => {
    it("trouve par le nom ou le type, sans accent ni casse", () => {
        expect(chercherLesEtapes(etapes, "cloture").map((e) => e.id)).toEqual(["3"]);
        expect(chercherLesEtapes(etapes, "RENDEZ").map((e) => e.id)).toEqual(["2"]);
        expect(chercherLesEtapes(etapes, "agentnode").map((e) => e.id)).toEqual(["2"]);
        expect(chercherLesEtapes(etapes, "  ")).toEqual([]);
    });
});

describe("barre d'outils du graphe", () => {
    it("annuler et rétablir suivent l'historique du brouillon", () => {
        const p = base();
        render(<BarreOutilsGraphe {...p} />);
        const annuler = screen.getByLabelText("Undo") as HTMLButtonElement;
        const retablir = screen.getByLabelText("Redo") as HTMLButtonElement;
        expect(annuler.disabled).toBe(false);
        expect(retablir.disabled).toBe(true);
        fireEvent.click(annuler);
        expect(p.onAnnuler).toHaveBeenCalledTimes(1);
    });

    it("réorganiser, aimant, carte, statistiques et boucles appellent leur geste et disent leur état", () => {
        const p = { ...base(), aimant: true, boucles: true, enBoucle: 2 };
        render(<BarreOutilsGraphe {...p} />);
        fireEvent.click(screen.getByLabelText("Tidy up the steps"));
        fireEvent.click(screen.getByLabelText("Snap to the grid"));
        fireEvent.click(screen.getByLabelText("Mini map"));
        fireEvent.click(screen.getByLabelText("Statistics of the real calls"));
        fireEvent.click(screen.getByLabelText("Forbid loops between steps"));
        expect(p.onReorganiser).toHaveBeenCalled();
        expect(p.onAimant).toHaveBeenCalled();
        expect(p.onCarte).toHaveBeenCalled();
        expect(p.onStats).toHaveBeenCalled();
        expect(p.onBoucles).toHaveBeenCalled();
        expect(screen.getByLabelText("Snap to the grid").getAttribute("aria-pressed")).toBe("true");
        expect(screen.getByLabelText("Forbid loops between steps").getAttribute("title")).toMatch(/2 transitions close a loop/);
    });

    it("les statistiques disent combien d'appels ont été lus", () => {
        render(<BarreOutilsGraphe {...base()} stats appelsLus={37} />);
        expect(screen.getByLabelText("Statistics of the real calls").getAttribute("title")).toMatch(/last 37 calls/);
    });

    it("la recherche liste les étapes et en montre une au clic", () => {
        const p = base();
        render(<BarreOutilsGraphe {...p} />);
        fireEvent.click(screen.getByLabelText("Search a step"));
        fireEvent.change(screen.getByPlaceholderText("Search a step"), { target: { value: "rendez" } });
        fireEvent.click(screen.getByText("Prise de rendez-vous"));
        expect(p.onChoisirEtape).toHaveBeenCalledWith("2");
        expect(screen.queryByPlaceholderText("Search a step")).toBeNull();
    });

    it("Entrée montre le premier résultat ; Échap ferme la recherche ; une recherche vide le dit", () => {
        const p = base();
        render(<BarreOutilsGraphe {...p} />);
        fireEvent.click(screen.getByLabelText("Search a step"));
        const champ = screen.getByPlaceholderText("Search a step");
        fireEvent.change(champ, { target: { value: "zzz" } });
        expect(screen.getByText("No step found")).toBeTruthy();
        fireEvent.change(champ, { target: { value: "accueil" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        expect(p.onChoisirEtape).toHaveBeenCalledWith("1");
        fireEvent.click(screen.getByLabelText("Search a step"));
        fireEvent.keyDown(window, { key: "Escape" });
        expect(screen.queryByPlaceholderText("Search a step")).toBeNull();
    });

    it("en lecture seule (version passée), seuls la carte, les statistiques et la recherche restent", () => {
        render(<BarreOutilsGraphe {...base()} lectureSeule />);
        expect(screen.queryByLabelText("Undo")).toBeNull();
        expect(screen.queryByLabelText("Tidy up the steps")).toBeNull();
        expect(screen.queryByLabelText("Forbid loops between steps")).toBeNull();
        expect(screen.getByLabelText("Mini map")).toBeTruthy();
        expect(screen.getByLabelText("Search a step")).toBeTruthy();
    });
});

describe("barre au survol d'une étape", () => {
    const props = () => ({
        visible: true,
        nom: "Motif",
        peutDupliquer: true,
        peutSupprimer: true,
        onModifier: vi.fn(),
        onDupliquer: vi.fn(),
        onRelier: vi.fn(),
        onSupprimer: vi.fn(),
        onEntrer: vi.fn(),
        onSortir: vi.fn(),
    });

    it("modifier, dupliquer et relier agissent tout de suite", () => {
        const p = props();
        render(<BarreAuSurvol {...p} />);
        fireEvent.click(screen.getByLabelText("Edit the step"));
        fireEvent.click(screen.getByLabelText("Duplicate the step"));
        fireEvent.click(screen.getByLabelText("Link to another step"));
        expect(p.onModifier).toHaveBeenCalled();
        expect(p.onDupliquer).toHaveBeenCalled();
        expect(p.onRelier).toHaveBeenCalled();
    });

    it("supprimer demande confirmation : rien n'est supprimé avant « Supprimer », « Annuler » laisse l'étape", () => {
        const p = props();
        render(<BarreAuSurvol {...p} />);
        fireEvent.click(screen.getByLabelText("Delete the step"));
        expect(p.onSupprimer).not.toHaveBeenCalled();
        expect(screen.getByText("Delete \"Motif\"?")).toBeTruthy();
        fireEvent.click(screen.getByText("Cancel"));
        expect(p.onSupprimer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByLabelText("Delete the step"));
        fireEvent.click(screen.getAllByRole("button", { name: "Delete" }).at(-1)!);
        expect(p.onSupprimer).toHaveBeenCalledTimes(1);
    });

    it("l'étape de début ne se supprime ni ne se duplique ; en lecture seule, on ne peut que l'ouvrir", () => {
        const { rerender } = render(<BarreAuSurvol {...props()} peutDupliquer={false} peutSupprimer={false} />);
        expect(screen.queryByLabelText("Delete the step")).toBeNull();
        expect(screen.queryByLabelText("Duplicate the step")).toBeNull();
        rerender(<BarreAuSurvol {...props()} lectureSeule />);
        expect(screen.queryByLabelText("Delete the step")).toBeNull();
        expect(screen.queryByLabelText("Link to another step")).toBeNull();
        expect(screen.getByLabelText("Edit the step")).toBeTruthy();
    });

    it("n'apparaît que sur l'étape survolée ou choisie", () => {
        render(<BarreAuSurvol {...props()} visible={false} />);
        expect(screen.queryByTestId("barre-survol")).toBeNull();
    });
});
