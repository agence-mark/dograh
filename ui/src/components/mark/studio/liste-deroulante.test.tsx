/**
 * [.mark] V1b : la liste déroulante du design system à la place du `<select>` du navigateur.
 *
 * Questions de ce fichier :
 *
 *     Les `<option>` enfants deviennent-ils les lignes de la liste (fragments, options sans `value`, options cachées) ?
 *     Choisir une ligne appelle-t-il `onChange` comme le navigateur (`e.target.value`), la ligne vide rendant « » ?
 *     Ce qui était écrit pour le `<select>` du navigateur (bordure, fond, hauteur) ne se retrouve-t-il pas sur le
 *     déclencheur du design system, seul le placement étant gardé ? Plus aucun `<select>` du navigateur dans les écrans ?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/ui/select", async () => await import("./select-natif-test"));

const { ListeDeroulante, classesDePlacement, optionsDe } = await import("./liste-deroulante");

afterEach(cleanup);

describe("les lignes de la liste", () => {
    it("viennent des <option> enfants, fragments traversés, sans les options cachées", () => {
        const lignes = optionsDe(
            <>
                <option value="">Aucune</option>
                <>
                    <option value="a">Alpha</option>
                    <option value="b" disabled>
                        Bravo
                    </option>
                </>
                <option hidden value="x">
                    Caché
                </option>
                <option>Sans valeur</option>
            </>,
        );
        expect(lignes.map((l) => [l.valeur, l.desactivee])).toEqual([
            ["", false],
            ["a", false],
            ["b", true],
            ["Sans valeur", false],
        ]);
    });
});

describe("le placement", () => {
    it("ne garde que les classes de placement de ce qui était écrit pour le <select> du navigateur", () => {
        expect(classesDePlacement("h-9 w-full rounded-md border bg-background px-2 py-1.5 mt-2")).toBe("w-full mt-2");
        expect(classesDePlacement(undefined)).toBe("");
        expect(classesDePlacement("border text-sm")).toBe("");
    });
});

describe("le choix d'une ligne", () => {
    it("appelle onChange avec la valeur choisie, comme le navigateur ; la ligne vide rend la chaîne vide", () => {
        const onChange = vi.fn();
        render(
            <ListeDeroulante aria-label="Choix" value="a" onChange={(e) => onChange(e.target.value)}>
                <option value="">Aucune</option>
                <option value="a">Alpha</option>
                <option value="b">Bravo</option>
            </ListeDeroulante>,
        );
        const liste = screen.getByLabelText("Choix") as HTMLSelectElement;
        expect(liste.value).toBe("a");
        fireEvent.change(liste, { target: { value: "b" } });
        expect(onChange).toHaveBeenLastCalledWith("b");
        fireEvent.change(liste, { target: { value: "__vide__" } });
        expect(onChange).toHaveBeenLastCalledWith("");
    });

    it("une valeur vide montre la ligne vide quand elle existe", () => {
        render(
            <ListeDeroulante aria-label="Choix" value="" onChange={() => undefined}>
                <option value="">Aucune</option>
                <option value="a">Alpha</option>
            </ListeDeroulante>,
        );
        expect((screen.getByLabelText("Choix") as HTMLSelectElement).value).toBe("__vide__");
    });
});

describe("plus aucun <select> du navigateur dans les écrans", () => {
    const fichiers = (dossier: string): string[] =>
        readdirSync(dossier).flatMap((nom) => {
            const chemin = join(dossier, nom);
            if (statSync(chemin).isDirectory()) return nom === "node_modules" ? [] : fichiers(chemin);
            return /\.tsx$/.test(nom) && !/\.test\.tsx$/.test(nom) ? [chemin] : [];
        });

    it("seuls le composant lui-même, la liste d'options et le module de test portent la balise", () => {
        const racine = join(process.cwd(), "src");
        const fautifs = fichiers(racine).filter((f) => {
            if (/(select-natif|liste-deroulante)/.test(f)) return false;
            // Une balise écrite dans un commentaire entre apostrophes inversées (`<select>`) ne compte pas.
            return /(?<!`)<select[\s>]/.test(readFileSync(f, "utf8"));
        });
        expect(fautifs).toEqual([]);
    });
});
