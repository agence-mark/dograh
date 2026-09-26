/**
 * [.mark] Dograh's screens translated over the top (chantier
 * reorganisation-ecran-reglages, step 8, convention T3 and T4).
 *
 *   - the translator swaps Dograh's texts, and undoes it back to English;
 *   - ⛔ a prompt, a name and a transcription holding a dictionary text are
 *     NEVER translated (T4), nor code, nor the workflow editor;
 *   - React keeps working on a translated page;
 *   - the dictionary covers every English text of Dograh's screens, and holds
 *     nothing that is no longer on them (blocking: the upgrade tool lists both).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import dictionnaire from "./dictionnaire-dograh.json";
import { FournisseurLangue } from "./langue";
import { textesDograh } from "./textes-dograh";
import { textesUneLangue } from "./textes-une-langue";
import { creerTraducteur } from "./TraductionDograh";

const DICO = { Save: "Enregistrer", Cancel: "Annuler", "Search agents...": "Rechercher des agents...", Settings: "Paramètres" };

afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
    window.localStorage.clear();
});

const attendre = () => act(() => new Promise((fin) => setTimeout(fin, 0)));

describe("[.mark] the translator", () => {
    it("swaps Dograh's texts and the attributes a person reads, and undoes it", () => {
        document.body.innerHTML = `
            <main id="racine">
                <button> Save </button>
                <input placeholder="Search agents..." />
                <span title="Settings">Settings</span>
                <p>Save the file</p>
            </main>`;
        const racine = document.getElementById("racine")!;
        const traducteur = creerTraducteur(racine, DICO);
        traducteur.demarrer();
        expect(racine.querySelector("button")!.textContent).toBe(" Enregistrer ");
        expect(racine.querySelector("input")!.getAttribute("placeholder")).toBe("Rechercher des agents...");
        expect(racine.querySelector("span")!.getAttribute("title")).toBe("Paramètres");
        expect(racine.querySelector("span")!.textContent).toBe("Paramètres");
        // Only a WHOLE text is a text of Dograh's.
        expect(racine.querySelector("p")!.textContent).toBe("Save the file");

        traducteur.arreter();
        expect(racine.querySelector("button")!.textContent).toBe(" Save ");
        expect(racine.querySelector("input")!.getAttribute("placeholder")).toBe("Search agents...");
        expect(racine.querySelector("span")!.textContent).toBe("Settings");
    });

    it("⛔ never translates a prompt, a name, a transcription, code or the workflow editor", () => {
        document.body.innerHTML = `
            <main id="racine">
                <textarea>Save</textarea>
                <input value="Cancel" />
                <div contenteditable="true">Save</div>
                <div class="whitespace-pre-wrap break-words rounded-2xl"><div>Cancel</div></div>
                <p class="text-sm text-muted-foreground line-clamp-1 mb-1">Save</p>
                <code>Save</code>
                <pre>Cancel</pre>
                <div class="react-flow"><div class="react-flow__node">Settings</div></div>
                <h1 data-mark-pas-traduire>Settings</h1>
            </main>`;
        const racine = document.getElementById("racine")!;
        const avant = racine.innerHTML;
        const traducteur = creerTraducteur(racine, DICO);
        traducteur.demarrer();
        expect(racine.innerHTML).toBe(avant);
        expect((racine.querySelector("input") as HTMLInputElement).value).toBe("Cancel");
        expect((racine.querySelector("textarea") as HTMLTextAreaElement).value).toBe("Save");
        traducteur.arreter();
    });

    it("forgets the nodes the page has removed (review of 26/09, m2)", async () => {
        document.body.innerHTML = `<main id="racine"></main>`;
        const racine = document.getElementById("racine")!;
        const traducteur = creerTraducteur(racine, DICO);
        traducteur.demarrer();
        racine.innerHTML = Array.from({ length: 1500 }, () => "<button>Save</button>").join("");
        await attendre();
        expect(traducteur.suivis()).toBe(1500);
        racine.innerHTML = "<button>Cancel</button>";
        await attendre();
        expect(traducteur.suivis()).toBe(1);
        expect(racine.textContent).toBe("Annuler");
        traducteur.arreter();
    });

    it("translates what React draws later, and React keeps working on the translated page", async () => {
        const Compteur = () => {
            const [ouvert, setOuvert] = useState(false);
            const [n, setN] = useState(0);
            return (
                <div>
                    <button onClick={() => setN((x) => x + 1)}>Save</button>
                    <span data-testid="n">{n}</span>
                    <button onClick={() => setOuvert((x) => !x)}>Settings</button>
                    {ouvert && <p>Cancel</p>}
                </div>
            );
        };
        render(<Compteur />);
        const traducteur = creerTraducteur(document.body, DICO);
        traducteur.demarrer();
        fireEvent.click(screen.getByText("Enregistrer"));
        fireEvent.click(screen.getByText("Enregistrer"));
        expect(screen.getByTestId("n").textContent).toBe("2");
        fireEvent.click(screen.getByText("Paramètres"));
        await attendre();
        expect(screen.getByText("Annuler")).toBeTruthy();
        fireEvent.click(screen.getByText("Paramètres"));
        await attendre();
        expect(screen.queryByText("Annuler")).toBeNull();
        traducteur.arreter();
        expect(screen.getByText("Save")).toBeTruthy();
    });

    it("follows the language chosen: French translates, English does not", async () => {
        window.localStorage.setItem("mark.langue", "en");
        render(
            <FournisseurLangue>
                <button>{Object.keys(dictionnaire)[0]}</button>
            </FournisseurLangue>,
        );
        await attendre();
        const cle = Object.keys(dictionnaire)[0];
        expect(screen.getByRole("button").textContent).toBe(cle);
        cleanup();
        window.localStorage.setItem("mark.langue", "fr");
        render(
            <FournisseurLangue>
                <button>{cle}</button>
            </FournisseurLangue>,
        );
        await attendre();
        expect(screen.getByRole("button").textContent).toBe((dictionnaire as Record<string, string>)[cle]);
    });
});

describe("[.mark] the dictionary of Dograh's screens", () => {
    const racineUi = process.cwd();
    const textes = textesDograh(racineUi, textesUneLangue).map(({ texte }) => texte);
    const dico = JSON.parse(readFileSync(join(racineUi, "src/components/mark/langue/dictionnaire-dograh.json"), "utf8")) as Record<
        string,
        string
    >;

    it("has a French for every English text of Dograh's screens", () => {
        expect(textes.filter((texte) => !dico[texte]?.trim())).toEqual([]);
    });

    it("holds nothing that is no longer on Dograh's screens", () => {
        const presents = new Set(textes);
        expect(Object.keys(dico).filter((cle) => !presents.has(cle))).toEqual([]);
    });
});
