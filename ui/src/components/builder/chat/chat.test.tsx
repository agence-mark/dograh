/**
 * [.mark] builder partie 2, U5 : le fil du chat côté écran.
 *
 * Questions de ce fichier : le même flux donne-t-il toujours les mêmes lignes (rechargement) ? Le plan est-il UNE carte tenue à
 * jour ? Une action est-elle une ligne avec sa roue puis son résultat ? « Modifier et relancer » retire-t-il le message et la suite ?
 * Le Markdown est-il rendu sans jamais interpréter de HTML ? La question propose-t-elle sa réponse, et ne répond-on qu'à la dernière ?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CarteDuPlan, CarteQuestion, LigneAction } from "./cartes";
import { appliquer, dernierMessage, type EvenementDuFil, type LigneDuFil, lireLesBlocs, planCourant } from "./evenements";
import { Markdown } from "./Markdown";

afterEach(cleanup);

const rejouer = (flux: [number, EvenementDuFil][]): LigneDuFil[] => flux.reduce<LigneDuFil[]>((l, [id, e]) => appliquer(l, id, e), []);

describe("evenements", () => {
    const flux: [number, EvenementDuFil][] = [
        [1, { type: "message", texte: "Construis" }],
        [2, { type: "texte", texte: "Je " }],
        [3, { type: "texte", texte: "commence" }],
        [4, { type: "action", id: "a1", nom: "fiche_lire", arguments: {} }],
        [5, { type: "carte", carte: { type: "plan", etapes: [{ libelle: "Lire", etat: "en_cours" }] } }],
        [6, { type: "resultat", id: "a1", nom: "fiche_lire", ok: true, resultat: { x: 1 } }],
        [7, { type: "carte", carte: { type: "plan", etapes: [{ libelle: "Lire", etat: "fait" }] } }],
        [8, { type: "fin", raison: "fin" }],
    ];

    it("rejouer deux fois le même flux donne les mêmes lignes (rechargement sans perte)", () => {
        expect(rejouer(flux)).toEqual(rejouer(flux));
    });

    it("joint le texte, ferme l'action avec son résultat, garde un seul plan à jour", () => {
        const lignes = rejouer(flux);
        expect(lignes.filter((l) => l.genre === "texte")).toEqual([{ genre: "texte", texte: "Je commence" }]);
        expect(lignes.find((l) => l.genre === "action")).toMatchObject({ fini: true, ok: true });
        expect(lignes.filter((l) => l.genre === "carte")).toHaveLength(1);
        expect(planCourant(lignes)).toEqual([{ libelle: "Lire", etat: "fait" }]);
        expect(lignes.some((l) => l.genre === "fin")).toBe(false); // une fin normale ne s'affiche pas
    });

    it("« modifier et relancer » retire le message et tout ce qui a suivi", () => {
        const lignes = rejouer([...flux, [9, { type: "message", texte: "Mauvaise" }], [10, { type: "texte", texte: "x" }], [11, { type: "retrait", depuis: 9 }]]);
        expect(dernierMessage(lignes)).toEqual({ id: 1, texte: "Construis" });
        expect(lignes.some((l) => l.genre === "texte" && l.texte === "x")).toBe(false);
    });

    it("un arrêt et un redémarrage s'affichent, la reprise est silencieuse", () => {
        const lignes = rejouer([[1, { type: "fin", raison: "redemarrage" }], [2, { type: "reprise" }]]);
        expect(lignes[0]).toEqual({ genre: "fin", raison: "redemarrage" });
    });

    it("lit un flux SSE coupé en deux morceaux, avec ses identifiants", async () => {
        const enc = new TextEncoder();
        const morceaux = ['id: 7\ndata: {"type":"te', 'xte","texte":"é"}\n\nid: 8\ndata: {"type":"fin","raison":"fin"}\n\n: battement\n\n'];
        const flot = new ReadableStream<Uint8Array>({
            start(c) {
                morceaux.forEach((m) => c.enqueue(enc.encode(m)));
                c.close();
            },
        });
        const vus = [];
        for await (const b of lireLesBlocs(flot)) vus.push(b);
        expect(vus.map((b) => b.id)).toEqual([7, 8]);
        expect(vus[0].evenement).toEqual({ type: "texte", texte: "é" });
    });
});

describe("cartes et Markdown", () => {
    it("le plan dessine ses trois états", () => {
        render(<CarteDuPlan etapes={[{ libelle: "A", etat: "fait" }, { libelle: "B", etat: "en_cours" }, { libelle: "C", etat: "a_venir" }]} />);
        expect(document.querySelectorAll("[data-etat]")).toHaveLength(3);
        expect(document.querySelector('[data-etat="en_cours"]')?.textContent).toBe("B");
    });

    it("la question propose sa réponse, le choix envoie, et rien ne part si elle n'est plus la dernière", () => {
        const repondre = vi.fn();
        const { rerender } = render(<CarteQuestion question="Quel ton ?" reponseProposee="Chaleureux" choix={["Sobre"]} repondre={repondre} active />);
        fireEvent.click(screen.getByText(/Chaleureux/));
        expect(repondre).toHaveBeenCalledWith("Chaleureux");
        fireEvent.click(screen.getByText("Sobre"));
        expect(repondre).toHaveBeenLastCalledWith("Sobre");
        rerender(<CarteQuestion question="Quel ton ?" reponseProposee="Chaleureux" choix={[]} repondre={repondre} active={false} />);
        expect((screen.getByText(/Chaleureux/).closest("button") as HTMLButtonElement).disabled).toBe(true);
    });

    it("la ligne d'action tourne tant qu'il n'y a pas de résultat, puis se déplie", () => {
        const { rerender } = render(<LigneAction ligne={{ genre: "action", id: "a", nom: "fiche_lire", arguments: { x: 1 }, fini: false }} />);
        expect(screen.getByLabelText("en cours")).toBeTruthy();
        rerender(<LigneAction ligne={{ genre: "action", id: "a", nom: "fiche_lire", arguments: { x: 1 }, fini: true, ok: true, resultat: { y: 2 } }} />);
        expect(screen.getByLabelText("fait")).toBeTruthy();
        fireEvent.click(screen.getByText("fiche_lire"));
        expect(document.body.textContent).toContain('"y": 2');
    });

    it("le Markdown rend listes, gras et code, et n'interprète jamais de HTML", () => {
        const { container } = render(<Markdown texte={"Un **gras** et `code`\n\n- a\n- b\n\n```\nbloc\n```\n\n<img src=x onerror=alert(1)>"} />);
        expect(container.querySelector("strong")?.textContent).toBe("gras");
        expect(container.querySelectorAll("li")).toHaveLength(2);
        expect(container.querySelector("pre")?.textContent).toBe("bloc");
        expect(container.querySelector("img")).toBeNull();
        expect(container.textContent).toContain("<img src=x");
    });
});
