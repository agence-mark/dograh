/**
 * [.mark] The shared pieces of the settings pages, rendered (chantier
 * reorganisation-ecran-reglages, step 2): a theme folds and shows its summary,
 * its dots, names a value that cannot be saved with « show », and its button
 * follows the rules of E6; the navigation carries the same dots; a setting
 * shows its technical name and its bounds (E5).
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Settings } from "lucide-react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ChampReglage, texteBornes } from "./ChampReglage";
import { Intertitre } from "./Intertitre";
import { NavigationThemes } from "./NavigationThemes";
import { type ErreurNommee, Theme } from "./Theme";

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const TITRE = { en: "Turn taking", fr: "Tour de parole" };

const ThemeTemoin = ({
    modifie = false,
    erreurs = [],
    onEnregistrer = vi.fn(),
    actifSansModification = false,
}: {
    modifie?: boolean;
    erreurs?: ErreurNommee[];
    onEnregistrer?: () => void;
    actifSansModification?: boolean;
}) => {
    const [ouvert, setOuvert] = useState(false);
    return (
        <Theme
            id="tour"
            icone={Settings}
            titre={TITRE}
            description={{ en: "When the agent decides the caller has finished.", fr: "Quand l'agent décide que l'appelant a fini." }}
            resume={["Fin de tour : Smart Turn", null, "Pause 0,6 s"]}
            ouvert={ouvert}
            onBasculer={() => setOuvert((o) => !o)}
            modifie={modifie}
            erreurs={erreurs}
            enregistrement={{ onEnregistrer, enCours: false, actifSansModification }}
        >
            <Intertitre titre={{ en: "End of turn", fr: "Fin de tour" }}>
                <p>contenu du thème</p>
            </Intertitre>
        </Theme>
    );
};

const enFrancais = (noeud: React.ReactNode) => render(<FournisseurLangue>{noeud}</FournisseurLangue>);

describe("[.mark] a theme", () => {
    it("folds: summary shown, content hidden, until the header is pressed", () => {
        enFrancais(<ThemeTemoin />);
        expect(screen.queryByText("contenu du thème")).toBeNull();
        expect(screen.getByText("Fin de tour : Smart Turn")).toBeTruthy();
        expect(screen.getByText("Pause 0,6 s")).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { expanded: false }));
        expect(screen.getByText("contenu du thème")).toBeTruthy();
        expect(screen.getByRole("heading", { name: "Fin de tour" })).toBeTruthy();
        // Open, the summary gives way to the settings themselves.
        expect(screen.queryByText("Pause 0,6 s")).toBeNull();
    });

    it("shows the orange dot for a change not saved, and enables its button only then", () => {
        const { rerender } = enFrancais(<ThemeTemoin />);
        fireEvent.click(screen.getByRole("button", { expanded: false }));
        const bouton = () => screen.getByRole("button", { name: "Enregistrer Tour de parole" }) as HTMLButtonElement;
        expect(bouton().disabled).toBe(true);
        expect(screen.queryByRole("img", { name: "Modifications non enregistrées" })).toBeNull();

        // Same element: the theme stays open across the new props.
        rerender(<FournisseurLangue><ThemeTemoin modifie /></FournisseurLangue>);
        expect(screen.getAllByRole("img", { name: "Modifications non enregistrées" }).length).toBe(1);
        expect(bouton().disabled).toBe(false);
    });

    it("keeps its button enabled untouched when asked to (the organization's themes)", () => {
        enFrancais(<ThemeTemoin actifSansModification />);
        fireEvent.click(screen.getByRole("button", { expanded: false }));
        expect((screen.getByRole("button", { name: "Enregistrer Tour de parole" }) as HTMLButtonElement).disabled).toBe(false);
    });

    it("names a value that cannot be saved, blocks the button, and « show » calls back", () => {
        const afficher = vi.fn();
        enFrancais(
            <ThemeTemoin
                modifie
                erreurs={[{ cle: "vad_confidence", libelle: "Confiance exigée", message: "Au plus 1.", afficher }]}
            />,
        );
        expect(screen.getByRole("img", { name: "Une valeur ne peut pas être enregistrée" })).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { expanded: false }));
        expect(screen.getByRole("alert").textContent).toContain("Confiance exigée");
        expect(screen.getByRole("alert").textContent).toContain("vad_confidence");
        expect((screen.getByRole("button", { name: "Enregistrer Tour de parole" }) as HTMLButtonElement).disabled).toBe(true);
        fireEvent.click(screen.getByRole("button", { name: "afficher" }));
        expect(afficher).toHaveBeenCalledOnce();
    });

    it("saves on its button", () => {
        const onEnregistrer = vi.fn();
        enFrancais(<ThemeTemoin modifie onEnregistrer={onEnregistrer} />);
        fireEvent.click(screen.getByRole("button", { expanded: false }));
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer Tour de parole" }));
        expect(onEnregistrer).toHaveBeenCalledOnce();
    });

    it("speaks English when the user chose it", () => {
        window.localStorage.setItem("mark.langue", "en");
        enFrancais(<ThemeTemoin modifie />);
        fireEvent.click(screen.getByRole("button", { expanded: false }));
        expect(screen.getByRole("button", { name: "Save Turn taking" })).toBeTruthy();
    });
});

describe("[.mark] the navigation of themes", () => {
    it("lists the themes with the same dots, and choosing one calls back", () => {
        const onChoisir = vi.fn();
        enFrancais(
            <NavigationThemes
                actif="tour"
                onChoisir={onChoisir}
                entrees={[
                    { id: "agent", titre: { en: "Agent", fr: "Agent" }, icone: Settings, modifie: false, enErreur: false },
                    { id: "tour", titre: TITRE, icone: Settings, modifie: true, enErreur: true },
                ]}
            />,
        );
        const tour = document.querySelector('[data-navigation="tour"]') as HTMLElement;
        expect(tour.textContent).toContain("Tour de parole");
        expect(tour.querySelector('[data-pastille="modifie"]')).toBeTruthy();
        expect(tour.querySelector('[data-pastille="erreur"]')).toBeTruthy();
        expect(document.querySelector('[data-navigation="agent"] [data-pastille]')).toBeNull();
        fireEvent.click(tour);
        expect(onChoisir).toHaveBeenCalledWith("tour");
    });
});

describe("[.mark] a setting", () => {
    it("shows its label, its technical name in grey, its help and its bounds (E5)", () => {
        enFrancais(
            <ChampReglage
                cle="vad_confidence"
                idControle="vad_confidence"
                libelle={{ en: "Confidence required", fr: "Confiance exigée" }}
                aides={[{ en: "Higher misses quiet speech.", fr: "Plus haut, la voix basse est ratée." }]}
                bornes={texteBornes("vad_confidence")}
            >
                <input id="vad_confidence" />
            </ChampReglage>,
        );
        const bloc = document.querySelector('[data-reglage="vad_confidence"]') as HTMLElement;
        expect(screen.getByLabelText("Confiance exigée")).toBeTruthy();
        expect(bloc.querySelector("[data-cle-technique]")?.textContent).toBe("vad_confidence");
        expect(bloc.textContent).toContain("Plus haut, la voix basse est ratée.");
        expect(bloc.textContent).toContain("≥ 0 · ≤ 1");
    });

    it("writes a strict lower bound and an optional field", () => {
        expect(texteBornes("user_speech_timeout")).toEqual({ en: "> 0 · ≤ 10", fr: "> 0 · ≤ 10" });
        expect(texteBornes("stt_ttfs_p99_latency", true)?.fr).toBe("> 0 · ≤ 10 · facultatif");
        expect(texteBornes("inconnu")).toBeNull();
    });
});
