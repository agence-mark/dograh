/**
 * [.mark] Partie 3, sous-lot 19 : le panneau de droite. Les fenêtres s'ouvrent dans un panneau unique à onglets, sans
 * voile ; l'aperçu est remplacé au clic suivant ; un détail s'empile avec sa flèche retour ; Échap remonte d'un niveau ;
 * `centree` et « hors cadre » gardent la fenêtre au milieu ; la page garde sa largeur utile (menu replié, puis par-dessus).
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { FournisseurLangue } from "../langue/langue";
import { Info } from "./marques";

import { FenetreChamps } from "./fenetre-champs";
import { adapter, ContextePanneau, LARGEUR_DEFAUT, largeurAnnoncee, PanneauDroit, useEtatPanneau } from "./panneau-droit";

// L'info-bulle (Radix) mesure son déclencheur : jsdom n'a pas ResizeObserver.
globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
};

afterEach(() => cleanup());

function Cadre({ children }: { children: React.ReactNode }) {
    const etat = useEtatPanneau();
    return (
        <ContextePanneau.Provider value={etat}>
            <main data-testid="page">{children}</main>
            <PanneauDroit etat={etat} dessus={false} largeurAffichee={etat.largeur} />
        </ContextePanneau.Provider>
    );
}

function Fenetre({ titre, centree, nouvelOnglet, enfant }: { titre: string; centree?: boolean; nouvelOnglet?: boolean; enfant?: string }) {
    const [ouverte, setOuverte] = useState(true);
    const [detail, setDetail] = useState(false);
    return (
        <Dialog open={ouverte} onOpenChange={setOuverte} centree={centree} nouvelOnglet={nouvelOnglet}>
            <DialogContent className="sm:max-w-3xl">
                <DialogTitle>{titre}</DialogTitle>
                {enfant && <button onClick={() => setDetail(true)}>{`ouvrir ${enfant}`}</button>}
                {enfant && (
                    <Dialog open={detail} onOpenChange={setDetail}>
                        <DialogContent>
                            <DialogTitle>{enfant}</DialogTitle>
                        </DialogContent>
                    </Dialog>
                )}
            </DialogContent>
        </Dialog>
    );
}

const onglets = () => screen.queryAllByRole("tab");
const corps = () => document.querySelector("[data-corps-panneau]") as HTMLElement;

describe("titre d'un onglet qui porte une info-bulle (clôture D2)", () => {
    it("le « ! » de l'info-bulle ne passe ni à l'onglet ni au lien retour", () => {
        function AvecInfo() {
            const [detail, setDetail] = useState(false);
            return (
                <FournisseurLangue>
                    <Dialog open onOpenChange={() => {}}>
                        <DialogContent>
                            <DialogTitle>
                                Développeurs <Info>Les clés et le serveur MCP.</Info>
                            </DialogTitle>
                            <button onClick={() => setDetail(true)}>ouvrir la clé</button>
                            <Dialog open={detail} onOpenChange={setDetail}>
                                <DialogContent>
                                    <DialogTitle>Clé</DialogTitle>
                                </DialogContent>
                            </Dialog>
                        </DialogContent>
                    </Dialog>
                </FournisseurLangue>
            );
        }
        render(
            <Cadre>
                <AvecInfo />
            </Cadre>,
        );
        expect(onglets().map((o) => o.textContent)).toEqual(["Développeurs"]);
        fireEvent.click(screen.getByText("ouvrir la clé"));
        const retour = corps().textContent ?? "";
        expect(retour).toContain("Développeurs");
        expect(retour).not.toContain("Développeurs!");
    });
});

describe("fenêtres dans le panneau de droite", () => {
    it("hors du cadre commun, la fenêtre reste centrée", () => {
        render(<Fenetre titre="Seule" />);
        expect(document.querySelector('[data-slot="dialog-content"][data-centree]')).toBeTruthy();
        expect(document.querySelector("[data-panneau]")).toBeNull();
    });

    it("dans le cadre, la fenêtre devient un onglet du panneau, sans voile ni verrou de page", async () => {
        render(
            <Cadre>
                <Fenetre titre="Versions" />
            </Cadre>,
        );
        expect(onglets().map((o) => o.textContent)).toEqual(["Versions"]);
        expect(corps().querySelector('[data-slot="dialog-content"][data-panneau]')).toBeTruthy();
        expect(document.querySelector('[data-slot="dialog-overlay"]')).toBeNull();
        expect(document.querySelector('[data-slot="dialog-content"][data-centree]')).toBeNull();
        expect(document.body.style.pointerEvents).not.toBe("none");
        expect(screen.getByTestId("page").getAttribute("aria-hidden")).toBeNull();
    });

    it("`centree` garde la fenêtre au milieu même dans le cadre", () => {
        render(
            <Cadre>
                <Fenetre titre="Supprimer" centree />
            </Cadre>,
        );
        expect(document.querySelector('[data-slot="dialog-content"][data-centree]')).toBeTruthy();
        expect(onglets()).toHaveLength(0);
    });

    it("un aperçu est remplacé par le suivant ; le double-clic épingle", async () => {
        const { rerender } = render(
            <Cadre>
                <Fenetre titre="Un" />
            </Cadre>,
        );
        fireEvent.doubleClick(onglets()[0]);
        rerender(
            <Cadre>
                <Fenetre titre="Un" />
                <Fenetre titre="Deux" />
            </Cadre>,
        );
        expect(onglets().map((o) => o.textContent)).toEqual(["Un", "Deux"]);
        rerender(
            <Cadre>
                <Fenetre titre="Un" />
                <Fenetre titre="Deux" />
                <Fenetre titre="Trois" />
            </Cadre>,
        );
        await act(async () => {
            await new Promise((r) => setTimeout(r, 10));
        });
        // « Un » est épinglé et reste ; « Deux » (aperçu) a été remplacé par « Trois ».
        expect(onglets().map((o) => o.textContent)).toEqual(["Un", "Trois"]);
    });

    it("un détail ouvert depuis la fenêtre s'empile dans le même onglet avec une flèche au nom du parent ; la flèche remonte", () => {
        render(
            <Cadre>
                <Fenetre titre="Tri du motif" enfant="Condition" />
            </Cadre>,
        );
        fireEvent.click(screen.getByText("ouvrir Condition"));
        expect(onglets()).toHaveLength(1);
        const fleche = document.querySelector("[data-fleche-retour]") as HTMLElement;
        expect(fleche.textContent).toBe("Tri du motif");
        fireEvent.click(fleche);
        expect(document.querySelector("[data-fleche-retour]")).toBeNull();
        expect(onglets()).toHaveLength(1);
    });

    it("un objet à part entière (`nouvelOnglet`) prend son propre onglet", () => {
        render(
            <Cadre>
                <Fenetre titre="Étape" />
                <Fenetre titre="Outil" nouvelOnglet />
            </Cadre>,
        );
        expect(onglets().map((o) => o.textContent)).toEqual(["Étape", "Outil"]);
    });

    it("Échap remonte d'un niveau (détail), puis ferme l'onglet", async () => {
        render(
            <Cadre>
                <Fenetre titre="Tri du motif" enfant="Condition" />
            </Cadre>,
        );
        fireEvent.click(screen.getByText("ouvrir Condition"));
        const echap = () => fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
        echap();
        expect(document.querySelector("[data-fleche-retour]")).toBeNull();
        expect(onglets()).toHaveLength(1);
        echap();
        expect(onglets()).toHaveLength(0);
    });

    it("la croix de l'onglet ferme la fenêtre", () => {
        render(
            <Cadre>
                <Fenetre titre="Versions" />
            </Cadre>,
        );
        fireEvent.click(screen.getByLabelText("Close tab"));
        expect(onglets()).toHaveLength(0);
    });
});

describe("largeur et adaptation", () => {
    it("lit la largeur annoncée par la fenêtre", () => {
        expect(largeurAnnoncee("flex sm:max-w-3xl h-[86vh]")).toBe(600);
        expect(largeurAnnoncee("p-0")).toBeUndefined();
    });

    it("grand écran : la page est poussée, rien ne se replie", () => {
        expect(adapter(1920, LARGEUR_DEFAUT, true)).toEqual({ replierMenu: false, dessus: false, largeurAffichee: LARGEUR_DEFAUT });
    });

    it("écran moyen : le menu se replie d'abord", () => {
        const a = adapter(1280, LARGEUR_DEFAUT, true);
        expect(a.replierMenu).toBe(true);
        expect(a.dessus).toBe(false);
    });

    it("écran étroit : le panneau passe par-dessus la page, jamais plus de 70 %", () => {
        const a = adapter(1000, 900, true);
        expect(a.dessus).toBe(true);
        expect(a.largeurAffichee).toBe(700);
    });
});

describe("la règle des fenêtres à champs", () => {
    const champs = (n: number) => [{ champs: Array.from({ length: n }, (_, i) => ({ id: `c${i}`, t: "texte" as const, l: `Champ ${i}`, v: "" })) }];
    it("une saisie de deux champs s'ouvre dans le panneau (clôture, SA-3 : seules les confirmations dangereuses et les exceptions listées restent centrées)", () => {
        render(
            <Cadre>
                <FenetreChamps ouverte fermer={() => {}} titre="Renommer" sections={champs(2)} valider="OK" />
            </Cadre>,
        );
        expect(document.querySelector('[data-slot="dialog-content"][data-centree]')).toBeNull();
        expect(onglets().map((o) => o.textContent)).toEqual(["Renommer"]);
    });
    it("une fenêtre qui demande d'être centrée l'est, même à deux champs", () => {
        render(
            <Cadre>
                <FenetreChamps ouverte centree fermer={() => {}} titre="Nouveau" sections={champs(2)} valider="OK" />
            </Cadre>,
        );
        expect(document.querySelector('[data-slot="dialog-content"][data-centree]')).toBeTruthy();
        expect(onglets()).toHaveLength(0);
    });
    it("au-delà de deux champs, elle s'ouvre dans le panneau", () => {
        render(
            <Cadre>
                <FenetreChamps ouverte fermer={() => {}} titre="Réglages" sections={champs(3)} valider="OK" />
            </Cadre>,
        );
        expect(onglets().map((o) => o.textContent)).toEqual(["Réglages"]);
    });
    it("une confirmation dangereuse reste centrée", () => {
        render(
            <Cadre>
                <FenetreChamps ouverte fermer={() => {}} titre="Supprimer" danger sections={champs(3)} valider="Supprimer" />
            </Cadre>,
        );
        expect(onglets()).toHaveLength(0);
    });
});

describe("onglets qui gardent leur largeur (correctifs du 10/11, point 1)", () => {
    it("un onglet ne rétrécit jamais : il garde son texte, la rangée défile et le menu « ⋯ » les liste tous", () => {
        render(
            <FournisseurLangue>
                <Cadre>
                    <Fenetre titre="Nouvel outil" nouvelOnglet />
                </Cadre>
            </FournisseurLangue>,
        );
        const [onglet] = screen.getAllByTestId("onglet-du-panneau");
        expect(onglet.className).toContain("shrink-0");
        expect(onglet.querySelector("span")?.className).toContain("max-w-56");
    });
});
