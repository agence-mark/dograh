/**
 * [.mark] Les composants communs du design system (U1, sous-lot 1) : marques, liste, tableau, pagination, états
 * vides, fenêtres (E55, E71). Chaque composant est rendu, et son comportement décidé par Evan est vérifié.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { Inbox } from "lucide-react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { FournisseurLangue } from "../langue/langue";
import { EtatVide } from "./etat-vide";
import { FenetreChamps } from "./fenetre-champs";
import { FenetreOnglets, Segmente } from "./fenetre-onglets";
import { Liste } from "./liste";
import { Etiquette, Gravite, Marque, NoteJuge, Pastille, PointEtat } from "./marques";
import { fenetrePage, Paginee,PAR_PAGE } from "./pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "./tableau";

const pousser = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: pousser }) }));

afterEach(() => {
    cleanup();
    window.localStorage.clear();
    pousser.mockReset();
});

const avecLangue = (ui: React.ReactNode) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("marques (E19 à E25, E100)", () => {
    it("une seule forme de badge, quatre tons plus le plein, tous par jeton", () => {
        const { container } = avecLangue(
            <>
                {(["neutre", "succes", "attention", "danger", "plein"] as const).map((ton) => (
                    <Marque key={ton} ton={ton}>
                        {ton}
                    </Marque>
                ))}
            </>,
        );
        const marques = container.querySelectorAll("[data-ton]");
        expect(marques).toHaveLength(5);
        marques.forEach((m) => expect(m.className).toMatch(/bg-\(--marque-/));
    });

    it("la pastille est rouge seulement quand il faut agir", () => {
        const { container } = avecLangue(
            <>
                <Pastille n={3} />
                <Pastille urgent n={2} />
            </>,
        );
        expect(container.querySelectorAll("[data-urgente]")).toHaveLength(1);
        expect(screen.getByText("3")).toBeTruthy();
    });

    it("la note du juge pose la pastille rouge sous le seuil, et un tiret sans note", () => {
        const { container } = avecLangue(
            <>
                <NoteJuge note={3.2} />
                <NoteJuge note={4.1} />
                <NoteJuge note={null} />
            </>,
        );
        expect(container.querySelectorAll("[data-urgente]")).toHaveLength(1);
        expect(screen.getByText("3,2")).toBeTruthy();
        expect(screen.getByText("–")).toBeTruthy();
    });

    it("le point d'état n'utilise jamais d'orange : « attend quelqu'un » prend le bleu .mark", () => {
        const { container } = avecLangue(<PointEtat etat="attente">En attente</PointEtat>);
        expect(container.querySelector("[data-etat='attente']")?.className).toContain("bg-(--acc)");
    });

    it("la gravité s'écrit en français par défaut", () => {
        avecLangue(
            <>
                <Gravite n={3} />
                <Gravite n={2} />
                <Gravite n={1} />
            </>,
        );
        ["Grave", "À surveiller", "Faible"].forEach((mot) => expect(screen.getByText(mot)).toBeTruthy());
    });

    it("l'étiquette ne montre sa croix que si on peut la retirer", () => {
        const retirer = vi.fn();
        avecLangue(
            <>
                <Etiquette>fixe</Etiquette>
                <Etiquette retirer={retirer}>mobile</Etiquette>
            </>,
        );
        const croix = screen.getAllByRole("button");
        expect(croix).toHaveLength(1);
        fireEvent.click(croix[0]);
        expect(retirer).toHaveBeenCalledTimes(1);
    });
});

describe("liste", () => {
    it("rend le Select du design system, jamais un <select> natif", () => {
        const { container } = avecLangue(<Liste options={["a", "b"]} />);
        expect(container.querySelector("select")).toBeNull();
        expect(screen.getByRole("combobox")).toBeTruthy();
    });
});

describe("tableau (E28, E34, E53)", () => {
    it("sans cadre, un clic sur la ligne ouvre l'objet", () => {
        const { container } = avecLangue(
            <>
                <TitreTableau titre="Agents" />
                <Tableau colonnes={[{ titre: "Nom" }, { titre: "État" }]}>
                    <Ligne href="/agents/1">
                        <Cellule principale>Standard</Cellule>
                        <Cellule>publié</Cellule>
                    </Ligne>
                </Tableau>
            </>,
        );
        expect(container.querySelector("table")?.className).not.toMatch(/border|rounded|shadow/);
        fireEvent.click(screen.getByText("Standard"));
        expect(pousser).toHaveBeenCalledWith("/agents/1");
    });
});

describe("pagination (E61)", () => {
    const lignes = Array.from({ length: 60 }, (_, i) => i + 1);

    it("local : 25 par page, la barre apparaît au-delà d'une page et tourne", () => {
        avecLangue(<Paginee liste={lignes}>{(page) => <ul>{page.map((n) => <li key={n}>n{n}</li>)}</ul>}</Paginee>);
        expect(screen.getAllByRole("listitem")).toHaveLength(PAR_PAGE);
        expect(screen.getByText(/1–25 sur 60/)).toBeTruthy();
        fireEvent.click(screen.getByLabelText("Page suivante"));
        expect(screen.getByText("n26")).toBeTruthy();
        expect(screen.getByText(/26–50 sur 60/)).toBeTruthy();
    });

    it("pas de barre quand tout tient sur une page", () => {
        avecLangue(<Paginee liste={[1, 2, 3]}>{(page) => <p>{page.length}</p>}</Paginee>);
        expect(screen.queryByLabelText("Page suivante")).toBeNull();
    });

    it("serveur : la page demandée est rendue par l'appelant, la barre change de page", () => {
        const changer = vi.fn();
        avecLangue(
            <Paginee total={60} page={1} changerPage={changer}>
                <p>page deux</p>
            </Paginee>,
        );
        expect(screen.getByText(/26–50 sur 60/)).toBeTruthy();
        fireEvent.click(screen.getByLabelText("Page précédente"));
        expect(changer).toHaveBeenCalledWith(0);
    });

    it("limit / offset de la page", () => {
        expect(fenetrePage(2)).toEqual({ limit: 25, offset: 50 });
    });
});

describe("états vides (E102)", () => {
    it("premier : un titre et un symbole, jamais de bouton", () => {
        avecLangue(<EtatVide cas="premier" icone={Inbox} titre="Aucun agent" />);
        expect(screen.getByText("Aucun agent")).toBeTruthy();
        expect(screen.queryByRole("button")).toBeNull();
    });

    it("fait : une donnée réelle en gris", () => {
        avecLangue(<EtatVide cas="fait" titre="Rien à améliorer" donnee="Dernier point traité hier" />);
        expect(screen.getByText("Dernier point traité hier")).toBeTruthy();
    });

    it("filtre : efface les filtres", () => {
        const effacer = vi.fn();
        avecLangue(<EtatVide cas="filtre" recherche="zzz" effacer={effacer} />);
        expect(screen.getByText(/Aucun résultat pour/)).toBeTruthy();
        fireEvent.click(screen.getByText("Effacer les filtres"));
        expect(effacer).toHaveBeenCalled();
    });

    it("chargement : des gris à la forme d'une liste, pas de roue", () => {
        const { container } = avecLangue(<EtatVide cas="chargement" lignes={3} />);
        expect(container.querySelector("[aria-busy='true']")?.children).toHaveLength(3);
    });

    it("erreur : réessayer ; accès : texte par défaut", () => {
        const reessayer = vi.fn();
        avecLangue(
            <>
                <EtatVide cas="erreur" reessayer={reessayer} />
                <EtatVide cas="acces" />
            </>,
        );
        fireEvent.click(screen.getByText("Réessayer"));
        expect(reessayer).toHaveBeenCalled();
        expect(screen.getByText("Réservé aux administrateurs")).toBeTruthy();
    });
});

describe("fenêtres (E55, E71)", () => {
    it("fenêtre à onglets : changer d'onglet, pied fixe, valider", () => {
        const valider = vi.fn();
        const Essai = () => {
            const [o, setO] = useState("Général");
            return (
                <FenetreOnglets
                    fermer={vi.fn()}
                    titre="Outil"
                    onglets={["Général", "Activité"]}
                    onglet={o}
                    changerOnglet={setO}
                    onValider={valider}
                >
                    <p>corps {o}</p>
                </FenetreOnglets>
            );
        };
        avecLangue(<Essai />);
        fireEvent.click(screen.getByRole("tab", { name: "Activité" }));
        expect(screen.getByText("corps Activité")).toBeTruthy();
        fireEvent.click(screen.getByText("Enregistrer"));
        expect(valider).toHaveBeenCalled();
    });

    it("lecture seule : un seul bouton Fermer", () => {
        avecLangue(
            <FenetreOnglets fermer={vi.fn()} titre="Lecture" valider={null}>
                <p>x</p>
            </FenetreOnglets>,
        );
        expect(screen.getByText("Fermer")).toBeTruthy();
        expect(screen.queryByText("Annuler")).toBeNull();
    });

    it("une fenêtre ouverte depuis une fenêtre prend la même taille et une flèche retour à la place de la croix", () => {
        const Deux = () => {
            const [seconde, setSeconde] = useState(false);
            return (
                <Dialog open>
                    <DialogContent className="sm:max-w-4xl h-[86vh]">
                        <DialogTitle>Première</DialogTitle>
                        <button onClick={() => setSeconde(true)}>ouvrir</button>
                        <Dialog open={seconde} onOpenChange={setSeconde}>
                            <DialogContent className="sm:max-w-sm">
                                <DialogTitle>Seconde</DialogTitle>
                            </DialogContent>
                        </Dialog>
                    </DialogContent>
                </Dialog>
            );
        };
        avecLangue(<Deux />);
        const premiere = screen.getByText("Première").closest("[data-slot='dialog-content']") as HTMLElement;
        expect(premiere.hasAttribute("data-imbriquee")).toBe(false);
        expect(within(premiere).queryByLabelText("Retour")).toBeNull();
        fireEvent.click(screen.getByText("ouvrir"));
        const seconde = screen.getByText("Seconde").closest("[data-slot='dialog-content']") as HTMLElement;
        expect(seconde.hasAttribute("data-imbriquee")).toBe(true);
        expect(seconde.className).toContain("sm:max-w-4xl");
        expect(seconde.className).toContain("h-[86vh]");
        expect(within(seconde).getByLabelText("Retour")).toBeTruthy();
        expect(within(seconde).queryByText("Close")).toBeNull();
        fireEvent.click(within(seconde).getByLabelText("Retour"));
        expect(screen.queryByText("Seconde")).toBeNull();
    });

    it("fenêtre à champs : rend les valeurs saisies, affiche un champ selon un autre", () => {
        const valeurs = vi.fn();
        const fermer = vi.fn();
        avecLangue(
            <FenetreChamps
                ouverte
                fermer={fermer}
                titre="Nouvelle clé"
                valider="Enregistrer la clé"
                onValider={valeurs}
                sections={[
                    {
                        champs: [
                            { id: "nom", t: "texte", l: "Nom", v: "Mistral" },
                            { id: "avance", t: "inter", l: "Avancé" },
                            { id: "adresse", t: "texte", l: "Adresse", si: ["avance", [true]] },
                        ],
                    },
                ]}
            />,
        );
        expect(screen.queryByLabelText("Adresse")).toBeNull();
        fireEvent.click(screen.getByRole("switch", { name: "Avancé" }));
        fireEvent.change(screen.getByLabelText("Adresse"), { target: { value: "https://x" } });
        fireEvent.click(screen.getByText("Enregistrer la clé"));
        expect(valeurs).toHaveBeenCalledWith({ nom: "Mistral", avance: true, adresse: "https://x" });
        expect(fermer).toHaveBeenCalled();
    });

    it("fenêtre à champs : l'explication est dans le « ! », jamais une phrase visible (04/11)", () => {
        avecLangue(
            <FenetreChamps
                ouverte
                fermer={vi.fn()}
                titre="Nouvelle clé"
                info="Sert à joindre le fournisseur. Elle n'est jamais réaffichée."
                valider="Enregistrer"
                sections={[{ champs: [{ id: "nom", t: "texte", l: "Nom", info: "Le nom sous lequel on la retrouve. Choisissez-en un clair." }] }]}
            />,
        );
        expect(screen.getAllByRole("button", { name: "Précision" })).toHaveLength(2);
        expect(screen.queryByText(/Sert à joindre le fournisseur/)).toBeNull();
        expect(screen.queryByText(/Le nom sous lequel on la retrouve/)).toBeNull();
    });

    it("fermée, la fenêtre à champs ne rend rien", () => {
        const { container } = avecLangue(<FenetreChamps ouverte={false} fermer={vi.fn()} titre="x" sections={[]} valider="Ok" />);
        expect(container.textContent).toBe("");
    });

    it("segmenté : marque l'option choisie", () => {
        const changer = vi.fn();
        avecLangue(<Segmente valeur="a" options={["a", "b"]} changer={changer} />);
        fireEvent.click(screen.getByText("b"));
        expect(changer).toHaveBeenCalledWith("b");
    });
});
