/**
 * [.mark] Builder partie 3, lots 8 et 22 (§ 3 bis) : les étiquettes d'objets dans le champ des prompts.
 *
 * | Test | La garantie |
 * |---|---|
 * | résolution | une clé d'objet est connue, archivée, introuvable, non rattachée à l'étape ; un bloc épinglé sur une version disparue |
 * | pastille | « Famille › nom » à la couleur de la famille (jeton), rouge avec ⚠ si en erreur ; le texte relu reste `{{famille:clé}}` |
 * | sélecteur | `@` l'ouvre, le filtre par famille, l'insertion écrit `{{outil:<uuid>}}`, « pas dans l'étape », Échap et clic dehors le ferment |
 * | correction | une étiquette non rattachée propose « Rattacher l'outil à l'étape » ; un bloc épinglé propose « Suivre la dernière version » |
 * | carte au survol | résumé de l'objet et « Retirer », qui ôte l'étiquette du texte |
 * | variables | une étiquette d'objet n'est jamais comptée comme variable inconnue ; l'aperçu montre le nom de la fonction |
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ChampVariables, lireDom } from "./ChampVariables";
import { figerBloc, type ObjetCitable, resoudre } from "./etiquettes-objets";
import { apercu, clesInconnues } from "./texte-etiquettes";

afterEach(cleanup);

const OBJETS: ObjetCitable[] = [
    { cle: "outil:u1", famille: "outil", libelle: "reserver", statut: "actif", rendu: "reserver", resume: "Réserve un créneau.", lignes: [["Nom vu par le modèle", "reserver"]] },
    { cle: "outil:u2", famille: "outil", libelle: "vieux", statut: "archive", rendu: "vieux" },
    { cle: "etape:n2", famille: "etape", libelle: "Tri du motif", statut: "actif", rendu: "Tri du motif" },
    {
        cle: "bloc:politesse",
        famille: "bloc",
        libelle: "Règles de politesse",
        statut: "actif",
        rendu: "Vouvoie.",
        version: 3,
        versions: [{ numero: 2, statut: "recette" }, { numero: 3, statut: "recette" }],
    },
];

describe("la résolution d'une clé d'objet", () => {
    it.each([
        ["outil:u1", ["u1"], undefined],
        ["outil:u1", [], "non_rattache"],
        ["outil:u2", ["u2"], "archive"],
        ["outil:zz", [], "introuvable"],
        ["bloc:politesse@v2", null, undefined],
        ["bloc:politesse@v9", null, "version_disparue"],
    ])("%s", (cle, outils, motif) => {
        expect(resoudre(cle, OBJETS, outils as string[] | null).motif).toBe(motif);
    });

    it("ne déclare rien en erreur tant que le catalogue n'est pas lu", () => {
        expect(resoudre("outil:zz", [], null, false).motif).toBeUndefined();
    });

    it("suit ou fige un bloc dans le texte", () => {
        expect(figerBloc("A {{bloc:politesse}} B", "bloc:politesse", 2)).toBe("A {{bloc:politesse@v2}} B");
        expect(figerBloc("{{bloc:politesse@v2}}", "bloc:politesse@v2", null)).toBe("{{bloc:politesse}}");
    });

    it("n'est jamais une variable inconnue ; l'aperçu montre ce que le modèle reçoit", () => {
        expect(clesInconnues("{{outil:u1}} {{bloc:x@v2}} {{fantome}}", [])).toEqual(["fantome"]);
        expect(apercu("Appelle {{outil:u1}}.", [], OBJETS)).toBe("Appelle reserver.");
    });
});

const Champ = ({ initial, suivi, outils = ["u1"], rattacher, ouvrir }: { initial: string; suivi?: (t: string) => void; outils?: string[] | null; rattacher?: (u: string) => void; ouvrir?: (c: string) => void }) => {
    const [v, setV] = useState(initial);
    return (
        <FournisseurLangue>
            <ChampVariables
                value={v}
                onChange={(t) => {
                    setV(t);
                    suivi?.(t);
                }}
                catalogue={[]}
                objets={OBJETS}
                objetsLus
                outilsDeLEtape={outils}
                rattacher={rattacher}
                ouvrirObjet={ouvrir}
                ariaLabel="Prompt"
            />
            <button type="button">dehors</button>
        </FournisseurLangue>
    );
};

const placerLeCurseurALaFin = (champ: HTMLElement) => {
    const noeud = champ.firstChild as Text;
    const range = document.createRange();
    range.setStart(noeud, noeud.length);
    range.collapse(true);
    window.getSelection()?.removeAllRanges();
    window.getSelection()?.addRange(range);
};

describe("ChampVariables avec des objets", () => {
    it("montre « Famille › nom » à la couleur de la famille, rouge si en erreur, et relit le même texte", () => {
        render(<Champ initial="Appelle {{outil:u1}} puis {{outil:zz}}." />);
        const champ = screen.getByTestId("champ-variables");
        const [bon, casse] = [...champ.querySelectorAll<HTMLElement>("[data-cle]")];
        expect(bon.textContent).toBe("Outil › reserver");
        expect(bon.style.background).toContain("var(--famille-outil)");
        expect(casse.dataset.erreur).toBe("introuvable");
        expect(casse.style.background).toContain("var(--source-inconnue)");
        expect(lireDom(champ)).toBe("Appelle {{outil:u1}} puis {{outil:zz}}.");
        expect(screen.getByTestId("compteur-inconnues").textContent).toMatch(/1/);
    });

    it("s'ouvre par @, filtre par famille, signale « pas dans l'étape » et insère la clé", async () => {
        const suivi = vi.fn();
        render(<Champ initial="" suivi={suivi} outils={[]} />);
        const champ = screen.getByTestId("champ-variables");
        champ.textContent = "Appelle @";
        placerLeCurseurALaFin(champ);
        fireEvent.input(champ);
        expect(await screen.findByTestId("menu-variables")).not.toBeNull();
        fireEvent.click(screen.getByRole("button", { name: /^Outils$/ }));
        expect([...document.querySelectorAll("[data-objet]")].map((b) => b.getAttribute("data-objet"))).toEqual(["outil:u1"]);
        expect(document.querySelector('[data-objet="outil:u1"]')?.textContent).toMatch(/pas dans l'étape/);
        fireEvent.click(document.querySelector('[data-objet="outil:u1"]') as HTMLElement);
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("Appelle {{outil:u1}}"));
        expect(screen.queryByTestId("menu-variables")).toBeNull();
    });

    it("se ferme par Échap et par un clic dehors", async () => {
        render(<Champ initial="Texte" />);
        fireEvent.doubleClick(screen.getByTestId("champ-variables"));
        const menu = await screen.findByTestId("menu-variables");
        fireEvent.keyDown(menu, { key: "Escape" });
        expect(screen.queryByTestId("menu-variables")).toBeNull();
        fireEvent.doubleClick(screen.getByTestId("champ-variables"));
        await screen.findByTestId("menu-variables");
        fireEvent.mouseDown(screen.getByText("dehors"));
        expect(screen.queryByTestId("menu-variables")).toBeNull();
    });

    it("propose « Rattacher l'outil à l'étape » sur une étiquette non rattachée", () => {
        const rattacher = vi.fn();
        render(<Champ initial="{{outil:u1}}" outils={[]} rattacher={rattacher} />);
        fireEvent.click(document.querySelector('[data-cle="outil:u1"]') as HTMLElement);
        fireEvent.click(screen.getByText("Rattacher l'outil à l'étape"));
        expect(rattacher).toHaveBeenCalledWith("u1");
    });

    it("ouvre un objet sans erreur au clic", () => {
        const ouvrir = vi.fn();
        render(<Champ initial="{{etape:n2}}" ouvrir={ouvrir} />);
        fireEvent.click(document.querySelector('[data-cle="etape:n2"]') as HTMLElement);
        expect(ouvrir).toHaveBeenCalledWith("etape:n2");
    });

    it("fait passer un bloc épinglé à « suivre la dernière »", async () => {
        const suivi = vi.fn();
        render(<Champ initial="{{bloc:politesse@v2}}" suivi={suivi} />);
        const pastille = document.querySelector('[data-cle="bloc:politesse@v2"]') as HTMLElement;
        expect(pastille.textContent).toBe("Bloc › Règles de politesse · v2 figée");
        fireEvent.click(pastille);
        fireEvent.click(screen.getByText("Suivre la dernière version"));
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("{{bloc:politesse}}"));
    });

    it("montre la carte au survol, avec « Retirer » qui ôte l'étiquette", async () => {
        vi.useFakeTimers();
        const suivi = vi.fn();
        render(<Champ initial="A {{outil:u1}} B" suivi={suivi} />);
        fireEvent.mouseOver(document.querySelector('[data-cle="outil:u1"]') as HTMLElement);
        act(() => {
            vi.advanceTimersByTime(250);
        });
        const carte = screen.getByTestId("carte-survol");
        expect(carte.textContent).toMatch(/Réserve un créneau/);
        fireEvent.click(screen.getByText("Retirer"));
        vi.useRealTimers();
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("A  B"));
    });
});
