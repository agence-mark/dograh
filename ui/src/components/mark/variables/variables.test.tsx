/**
 * [.mark] U3 bis, ter (E62, E63, E64, E67) : variables en étiquettes, genres, éditeur de tableau.
 *
 * | Test | La garantie |
 * |---|---|
 * | aller-retour | découper puis recomposer redonne le texte à l'identique (repli, espaces écrits à la main) |
 * | inconnue | une clé absente du catalogue est détectée ; `initial_context.*` et l'heure restent ouverts |
 * | champ | les motifs deviennent des pastilles, rouge si inconnue ; taper `{{` ouvre le menu ; l'insertion écrit `{{cle}}` |
 * | repli | « si vide, dire » écrit le `fallback` du moteur |
 * | genres | chaque genre se range dans la forme existante et se relit |
 * | tableau | collage multi-cases et import CSV relus à l'identique ; cadenas ; plafond ; annuler ne garde rien |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ColonneObjet } from "@/client/types.gen";

import { FournisseurLangue } from "../langue/langue";
import { ChampVariables, lireDom } from "./ChampVariables";
import { EditeurDeTableau } from "./EditeurDeTableau";
import { formeDuGenre, genreDe, nomTechnique } from "./genres";
import { coller, importerCsv, nettoyerMontant, type Tableau, texteRecu } from "./tableau-logique";
import { apercu, clesInconnues, decouper, motif, serialiser, sourceDe, type VariableCatalogue } from "./texte-etiquettes";

vi.mock("@/components/ui/dialog", () => ({
    Dialog: ({ open, children }: { open: boolean; children: React.ReactNode }) => (open ? <div>{children}</div> : null),
    DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
    DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });

afterEach(cleanup);

const CATALOGUE: VariableCatalogue[] = [
    { cle: "etablissement", libelle: "Nom de l'établissement", source: "entreprise", exemple: "Maison Durand" },
    { cle: "tarif", libelle: "Tarif", source: "entreprise", exemple: "35 €" },
    { cle: "prenom", libelle: "Prénom", source: "fiche", exemple: "" },
    { cle: "societe", libelle: "Société", source: "campagne", exemple: "ACME" },
    { cle: "date_appel", libelle: "Date de l'appel", source: "appel", exemple: "2026-11-04" },
];

describe("le texte d'un champ à étiquettes", () => {
    it.each([
        "Bonjour {{prenom}} !",
        "{{ prenom | fallback:cher client }} et {{tarif}}",
        "{{prenom|madame}}",
        "sans variable",
        "{{a}}{{b}}\nligne {{c}}",
    ])("redonne %j à l'identique après découpe", (texte) => {
        expect(serialiser(decouper(texte))).toBe(texte);
    });

    it("lit le repli sous les deux écritures et écrit le fallback du moteur", () => {
        const v = decouper("{{x | fallback:cher client}} {{y | madame}}").filter((s) => s.type === "variable");
        expect(v.map((s) => (s.type === "variable" ? s.repli : null))).toEqual(["cher client", "madame"]);
        expect(motif("x", "cher client")).toBe("{{x | fallback:cher client}}");
        expect(motif("x", null)).toBe("{{x}}");
    });

    it("détecte une clé inconnue, laisse ouvertes les familles du moteur et donne une source par clé", () => {
        expect(clesInconnues("{{prenom}} {{inconnue}} {{initial_context.ville}} {{current_time_Europe/Paris}} {{inconnue}}", CATALOGUE)).toEqual(["inconnue"]);
        expect(sourceDe("tarif", CATALOGUE)).toBe("entreprise");
        expect(sourceDe("prenom", CATALOGUE)).toBe("fiche");
        expect(sourceDe("societe", CATALOGUE)).toBe("campagne");
        expect(sourceDe("initial_context.ville", CATALOGUE)).toBe("appel");
        expect(sourceDe("zzz", CATALOGUE)).toBe("inconnue");
    });

    it("l'aperçu met les valeurs, le repli à défaut, la clé sinon", () => {
        expect(apercu("{{tarif}} / {{prenom | cher client}} / {{zzz}}", CATALOGUE)).toBe("35 € / cher client / {{zzz}}");
    });
});

const Champ = ({ initial, catalogue = CATALOGUE, lu = true, suivi }: { initial: string; catalogue?: VariableCatalogue[]; lu?: boolean; suivi?: (v: string) => void }) => {
    const [valeur, setValeur] = useState(initial);
    return (
        <FournisseurLangue>
            <ChampVariables
                value={valeur}
                onChange={(v) => {
                    setValeur(v);
                    suivi?.(v);
                }}
                catalogue={catalogue}
                catalogueLu={lu}
                ariaLabel="Prompt"
            />
        </FournisseurLangue>
    );
};

describe("ChampVariables", () => {
    it("montre chaque motif comme une pastille de la couleur de sa source et relit le même texte", () => {
        render(<Champ initial={"Bonjour {{prenom}} chez {{etablissement}}\nsuite"} />);
        const champ = screen.getByTestId("champ-variables");
        const pastilles = champ.querySelectorAll("[data-cle]");
        expect([...pastilles].map((p) => p.getAttribute("data-source"))).toEqual(["fiche", "entreprise"]);
        expect((pastilles[0] as HTMLElement).style.background).toMatch(/rgb\(4, 120, 87\)|#047857/i);
        expect(lireDom(champ)).toBe("Bonjour {{prenom}} chez {{etablissement}}\nsuite");
    });

    it("met en rouge une clé inconnue et compte les inconnues ; sans réponse du serveur, aucune n'est déclarée inconnue", () => {
        const { unmount } = render(<Champ initial="{{prenom}} {{fantome}}" />);
        expect(document.querySelector('[data-cle="fantome"]')?.getAttribute("data-source")).toBe("inconnue");
        expect(screen.getByTestId("compteur-inconnues").textContent).toMatch(/1/);
        unmount();
        render(<Champ initial="{{fantome}}" lu={false} />);
        expect(screen.queryByTestId("compteur-inconnues")).toBeNull();
    });

    it("s'ouvre en tapant {{ et insère l'étiquette choisie à la place des accolades", async () => {
        const suivi = vi.fn();
        render(<Champ initial="" suivi={suivi} />);
        const champ = screen.getByTestId("champ-variables");
        champ.textContent = "Bonjour {{";
        const noeud = champ.firstChild as Text;
        const range = document.createRange();
        range.setStart(noeud, noeud.length);
        range.collapse(true);
        window.getSelection()?.removeAllRanges();
        window.getSelection()?.addRange(range);
        fireEvent.input(champ);
        expect(await screen.findByTestId("menu-variables")).not.toBeNull();
        fireEvent.click(document.querySelector('[data-variable="tarif"]') as HTMLElement);
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("Bonjour {{tarif}}"));
        expect(screen.queryByTestId("menu-variables")).toBeNull();
    });

    it("s'ouvre au double-clic, cherche, et choisit au clavier", async () => {
        const suivi = vi.fn();
        render(<Champ initial="Bonjour " suivi={suivi} />);
        fireEvent.doubleClick(screen.getByTestId("champ-variables"));
        const recherche = await screen.findByLabelText(/Chercher une variable|Search a variable/);
        fireEvent.change(recherche, { target: { value: "soc" } });
        expect(document.querySelectorAll("[data-variable]")).toHaveLength(1);
        fireEvent.keyDown(screen.getByTestId("menu-variables"), { key: "Enter" });
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("Bonjour {{societe}}"));
    });

    it("écrit « si vide, dire » comme le fallback du moteur et retire l'étiquette d'un bloc", async () => {
        const suivi = vi.fn();
        render(<Champ initial="Bonjour {{prenom}}" suivi={suivi} />);
        fireEvent.click(document.querySelector('[data-cle="prenom"]') as HTMLElement);
        fireEvent.change(await screen.findByLabelText(/Si vide, dire|If empty, say/), { target: { value: "cher client" } });
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("Bonjour {{prenom | fallback:cher client}}"));
        fireEvent.click(screen.getByText(/Retirer|Remove/));
        await waitFor(() => expect(suivi).toHaveBeenLastCalledWith("Bonjour "));
    });

    it("montre l'aperçu avec les valeurs", () => {
        render(<Champ initial="Tarif : {{tarif}}" />);
        fireEvent.click(screen.getByText(/Aperçu avec les valeurs|Preview with values/));
        expect(screen.getByTestId("apercu-variables").textContent).toBe("Tarif : 35 €");
    });
});

describe("les genres du créateur", () => {
    it("rangent chaque genre dans une forme existante et le relisent", () => {
        expect(genreDe({ forme: "valeur", type: "texte", colonnes: [] })).toBe("mot");
        expect(genreDe({ forme: "valeur", type: "montant", colonnes: [] })).toBe("nombre");
        expect(genreDe({ forme: "valeur", type: "oui_non", colonnes: [] })).toBe("oui_non");
        expect(genreDe({ forme: "valeur", type: "date", colonnes: [] })).toBe("date");
        expect(genreDe({ forme: "liste", type: null, colonnes: [{ libelle: "a" } as ColonneObjet] })).toBe("liste");
        expect(genreDe({ forme: "liste", type: null, colonnes: [{ libelle: "a" }, { libelle: "b" }] as ColonneObjet[] })).toBe("tableau");
        expect(formeDuGenre("liste")).toBe("liste");
        expect(formeDuGenre("mot")).toBe("valeur");
    });

    it("calcule le nom technique depuis le libellé", () => {
        expect(nomTechnique("Frais de déplacement")).toBe("frais_de_deplacement");
        expect(nomTechnique("3 marques")).toBe("v_3_marques");
        expect(nomTechnique("")).toBe("");
    });
});

const TAB: Tableau = {
    colonnes: [
        { libelle: "Prestation", type: "texte", ordre: 1, pose_par: "mark" },
        { libelle: "Prix", type: "montant", ordre: 2, pose_par: "client" },
    ] as ColonneObjet[],
    lignes: [{ ordre: 1, valeurs: { Prestation: "Ramonage", Prix: "60" } }],
};

describe("l'éditeur de tableau (E67)", () => {
    it("répartit un collage Excel dans les cases, ajoute colonnes et lignes, nettoie les montants", () => {
        const colle = coller(TAB, 1, 0, "Entretien\t1 234,50 €\nDébistrage\t80,00 €\tbonus");
        expect(colle.colonnes.map((c) => c.libelle)).toEqual(["Prestation", "Prix", "Colonne 3"]);
        expect(colle.lignes.map((l) => l.valeurs)).toEqual([
            { Prestation: "Ramonage", Prix: "60" },
            { Prestation: "Entretien", Prix: "1234.50" },
            { Prestation: "Débistrage", Prix: "80.00", "Colonne 3": "bonus" },
        ]);
        expect(nettoyerMontant("12,5")).toBe("12.5");
        expect(nettoyerMontant("abc")).toBe("abc");
    });

    it("lit un CSV (première ligne = colonnes, guillemets, point-virgule) et le relit à l'identique", () => {
        const t = importerCsv('Nom;Note\n"Dupont; Jean";"il dit ""oui"""\nRika;');
        expect(t.colonnes.map((c) => c.libelle)).toEqual(["Nom", "Note"]);
        expect(t.lignes.map((l) => l.valeurs)).toEqual([{ Nom: "Dupont; Jean", Note: 'il dit "oui"' }, { Nom: "Rika", Note: "" }]);
        expect(texteRecu(t)).toBe("Nom | Note\nDupont; Jean | il dit \"oui\"\nRika | ");
    });

    const ouvrir = (tableau: Tableau, plafond = 3000, verrou = false) => {
        const valider = vi.fn();
        const annuler = vi.fn();
        render(
            <FournisseurLangue>
                <EditeurDeTableau tableau={tableau} plafond={plafond} verrouillerColonnesMark={verrou} onValider={valider} onAnnuler={annuler} />
            </FournisseurLangue>,
        );
        return { valider, annuler };
    };

    it("Entrée crée la ligne suivante au bout ; Valider rend le tableau tapé", () => {
        const { valider } = ouvrir(TAB);
        fireEvent.keyDown(document.querySelector('[data-case="0-0"]') as HTMLElement, { key: "Enter" });
        expect(document.querySelectorAll("[data-ligne-tableau]")).toHaveLength(2);
        fireEvent.change(document.querySelector('[data-case="1-0"]') as HTMLElement, { target: { value: "Entretien" } });
        fireEvent.click(screen.getByTestId("valider-tableau"));
        expect(valider.mock.calls[0][0].lignes[1].valeurs).toEqual({ Prestation: "Entretien" });
    });

    it("accepte un collage de tableur dans une case", () => {
        const { valider } = ouvrir(TAB);
        fireEvent.paste(document.querySelector('[data-case="0-0"]') as HTMLElement, { clipboardData: { getData: () => "A\t1,5\nB\t2" } });
        fireEvent.click(screen.getByTestId("valider-tableau"));
        expect(valider.mock.calls[0][0].lignes.map((l: { valeurs: Record<string, string> }) => l.valeurs)).toEqual([
            { Prestation: "A", Prix: "1.5" },
            { Prestation: "B", Prix: "2" },
        ]);
    });

    it("grise Valider au-delà du plafond ; Annuler ne garde rien", () => {
        const { valider, annuler } = ouvrir(TAB, 10);
        expect((screen.getByTestId("valider-tableau") as HTMLButtonElement).disabled).toBe(true);
        expect(document.querySelector('[data-jauge="depasse"]')).not.toBeNull();
        fireEvent.click(screen.getByTestId("annuler-tableau"));
        expect(annuler).toHaveBeenCalled();
        expect(valider).not.toHaveBeenCalled();
    });

    it("dans le portail, le cadenas ferme le nom, le type et la suppression d'une colonne posée par .mark mais pas le déplacement, et grise l'import", () => {
        ouvrir(TAB, 3000, true);
        const col = document.querySelector('[data-colonne="Prestation"]') as HTMLElement;
        expect(col.querySelector("svg[aria-label]")).not.toBeNull();
        expect((screen.getByLabelText(/Colonne 1|Column 1/) as HTMLInputElement).disabled).toBe(true);
        expect((screen.getByLabelText(/Retirer la colonne 1|Remove the column 1/) as HTMLButtonElement).disabled).toBe(true);
        expect((screen.getByLabelText(/Déplacer à droite 1|Move right 1/) as HTMLButtonElement).disabled).toBe(false);
        expect((screen.getByLabelText(/Retirer la colonne 2|Remove the column 2/) as HTMLButtonElement).disabled).toBe(false);
        expect((screen.getByTestId("importer-csv") as HTMLButtonElement).disabled).toBe(true);
    });

    it("dans Dograh, rien n'est verrouillé et l'import est ouvert", () => {
        ouvrir(TAB, 3000, false);
        expect((screen.getByLabelText(/Colonne 1|Column 1/) as HTMLInputElement).disabled).toBe(false);
        expect((screen.getByTestId("importer-csv") as HTMLButtonElement).disabled).toBe(false);
    });
});
