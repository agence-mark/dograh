/**
 * [.mark] Clôture D2 (É69) : « Tours 1 à N résumés » en tête du chat, dépliable sur le résumé ; rien quand rien n'est résumé.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

import { ToursResumes } from "./ToursResumes";

afterEach(() => {
    cleanup();
    window.localStorage.clear();
});

const monter = (fil: Parameters<typeof ToursResumes>[0]["fil"]) =>
    render(
        <FournisseurLangue>
            <ToursResumes fil={fil} />
        </FournisseurLangue>,
    );

describe("[.mark] les tours résumés d'un chat", () => {
    it("dit le nombre de tours résumés et déplie le résumé", () => {
        monter({ tours_resumes: 24, resume: "Dossiers lus ; 2 tests écrits.", resume_le: "2026-10-31T23:12:00+01:00" });
        const bouton = screen.getByRole("button", { name: /Tours 1 à 24 résumés \(contexte à 70 %, 31\/10/ });
        expect(bouton.getAttribute("aria-expanded")).toBe("false");
        expect(screen.queryByText(/Dossiers lus/)).toBeNull();
        fireEvent.click(bouton);
        expect(screen.getByText(/Résumé : Dossiers lus ; 2 tests écrits\./)).toBeTruthy();
    });

    it("ne montre rien quand aucun tour n'est résumé", () => {
        monter({ tours_resumes: 0 });
        expect(document.querySelector("[data-tours-resumes]")).toBeNull();
    });

    it("parle anglais quand l'écran est en anglais", () => {
        window.localStorage.setItem("mark.langue", "en");
        monter({ tours_resumes: 5 });
        expect(screen.getByRole("button", { name: "Turns 1 to 5 summarized" })).toBeTruthy();
    });
});
