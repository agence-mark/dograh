/**
 * [.mark] Builder partie 3, SA-L3a : « Prêt à publier », la liste unique.
 *
 * Questions de ce fichier :
 *
 *     Les quatre états sont-ils dessinés (fait, à faire, bloquant, hérité), les obligatoires en tête, les lignes faites repliées ?
 *     Ce qui manque est-il écrit en clair, en français et en anglais ? « Régler » mène-t-il à l'endroit exact (étape, onglet, thème) ?
 *     Une correction en un clic part-elle avec son identifiant et son étape, et la liste est-elle relue après ? La liste est-elle
 *     relue après un enregistrement (compteur) et après un geste du builder ?
 */
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../../langue/langue";
import { endroitDeLaLigne } from "./endroit";
import { ListePret, type LigneDePret, useListeDePret } from "./ListePret";
import { useRecalculDuPret } from "./recalcul";
import { useCorrectionEnUnClic } from "./useCorrection";

const m = vi.hoisted(() => ({ lire: vi.fn(), corriger: vi.fn() }));

vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet: (o: unknown) => m.lire(o),
    corrigerUnReglageApiV1BuilderPublicationWorkflowIdCorrigerUnReglagePost: (o: unknown) => m.corriger(o),
}));

afterEach(() => cleanup());
beforeEach(() => {
    m.lire.mockReset();
    m.corriger.mockReset();
});

const ligne = (id: string, etat: string, extra: Partial<LigneDePret> = {}): LigneDePret =>
    ({ id, niveau: "requis", etat, theme: "agent", source: id, manquants: [], corrections: [], noms: [], ...extra }) as LigneDePret;

const TEXTES = {
    variables: { titre: { en: "Variables filled", fr: "Variables remplies" }, source: { en: "src", fr: "src" } },
    fiche: { titre: { en: "Record defined", fr: "Fiche définie" }, source: { en: "src", fr: "src" } },
};

const monter = (lignes: LigneDePret[], extra: Partial<React.ComponentProps<typeof ListePret>> = {}) =>
    render(
        <FournisseurLangue>
            <ListePret lignes={lignes} textesDesEtapes={TEXTES} regler={vi.fn()} {...extra} />
        </FournisseurLangue>,
    );

describe("la liste dessinée", () => {
    it("met les lignes à faire en tête, replie les faites, dit ce qui manque et marque ce qui bloque", () => {
        const regler = vi.fn();
        monter([ligne("variables", "bloquant", { manquants: ["ville"] }), ligne("bilan_du_prompt", "fait"), ligne("fiche", "herite")], { regler });
        expect(document.querySelector("[data-etape='variables'] [data-cercle='bloquant']")).not.toBeNull();
        expect(screen.getByText("ville")).toBeTruthy();
        expect(screen.getByText("Bloque")).toBeTruthy();
        expect(document.querySelector("[data-preparation='resume']")?.textContent).toContain("1 contrôle bloque la publication");
        // faites et héritées : repliées, puis dépliées
        expect(document.querySelector("[data-etape='bilan_du_prompt']")).toBeNull();
        fireEvent.click(document.querySelector("[data-preparation='faites']")!);
        expect(document.querySelector("[data-etape='bilan_du_prompt'] [data-cercle='fait']")).not.toBeNull();
        expect(document.querySelector("[data-etape='fiche'] [data-cercle='herite']")).not.toBeNull();
        expect(screen.getByText("hérité du principal")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Régler" }));
        expect(regler.mock.calls[0][0].id).toBe("variables");
    });

    it("n'affiche pas une ligne sans objet et dit « tout est prêt » quand rien ne reste", () => {
        monter([ligne("outils", "sans_objet"), ligne("variables", "fait")]);
        expect(document.querySelector("[data-etape='outils']")).toBeNull();
        expect(document.querySelector("[data-preparation='resume']")?.textContent).toContain("Tout est prêt");
    });

    it("écrit un réglage sans effet en clair avec le nom de l'étape et propose ses corrections", () => {
        const corriger = vi.fn();
        monter(
            [
                ligne("condition_sur_le_modele:1:e1", "a_faire", {
                    constat: "condition_sur_le_modele",
                    noms: ["Accueil", "Urgence"],
                    niveau: "conseille",
                    corrections: [
                        { id: "faire_decider_la_fiche", noeud_id: "1", nom: "Accueil" },
                        { id: "retirer_la_condition", liaison_id: "e1" },
                    ],
                }),
            ],
            { corriger },
        );
        expect(screen.getByText("Règles sur une étape où le modèle décide")).toBeTruthy();
        expect(screen.getByText(/La liaison « Urgence » de « Accueil » a des règles de la fiche/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Faire décider la fiche sur « Accueil »" }));
        expect(corriger.mock.calls[0][1]).toMatchObject({ id: "faire_decider_la_fiche", noeud_id: "1" });
        expect(screen.getByRole("button", { name: "Retirer les règles" })).toBeTruthy();
    });

    it("N2 : « Voir la liste » déplie une liste longue de noms, « Réduire » la replie ; une liste courte n'a pas le lien", () => {
        monter([ligne("outils_a_jour", "a_faire", { niveau: "conseille", noms: ["Alpha", "Bravo", "Charlie", "Delta", "Echo"] })]);
        expect(screen.getByText(/Alpha, Bravo, Charlie …/)).toBeTruthy();
        expect(screen.queryByText(/Delta/)).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Voir la liste (5)" }));
        expect(screen.getByText(/Alpha, Bravo, Charlie, Delta, Echo/)).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Réduire" }));
        expect(screen.queryByText(/Delta/)).toBeNull();
        cleanup();
        monter([ligne("outils_a_jour", "a_faire", { niveau: "conseille", noms: ["Alpha", "Bravo"] })]);
        expect(screen.queryByRole("button", { name: /Voir la liste/ })).toBeNull();
    });

    it("n'offre aucune correction sans la fonction qui la joue", () => {
        monter([ligne("impasse_sans_issue", "bloquant", { constat: "impasse_sans_issue", corrections: [{ id: "eteindre_la_sortie_d_impasse" }] })]);
        expect(document.querySelector("[data-correction]")).toBeNull();
    });
});

describe("l'endroit exact", () => {
    it("mène à l'étape, à l'onglet ou au thème", () => {
        expect(endroitDeLaLigne({ noeud_id: "7", onglet: null, theme: "agent" }, 5)).toMatchObject({ sorte: "adresse", adresse: "/workflow/5?etape=7" });
        expect(endroitDeLaLigne({ noeud_id: null, onglet: "tests", theme: "agent" }, 5).adresse).toBe("/workflow/5/tests");
        expect(endroitDeLaLigne({ noeud_id: null, onglet: "parcours", theme: "agent" }, 5).adresse).toBe("/workflow/5");
        expect(endroitDeLaLigne({ noeud_id: null, onglet: null, theme: "briques" }, 5)).toMatchObject({ sorte: "theme", theme: "briques", adresse: "/workflow/5/settings?theme=briques" });
    });
});

function Sonde({ id }: { id: number }) {
    const { lignes, relire } = useListeDePret(id);
    const { corriger } = useCorrectionEnUnClic(id, relire);
    return (
        <>
            <span data-sonde="n">{lignes?.length ?? "vide"}</span>
            <button onClick={() => void corriger({ id: "allumer_la_fiche" })}>corriger</button>
        </>
    );
}

describe("recalcul", () => {
    it("relit la liste après un enregistrement, et une correction l'écrit puis relit", async () => {
        m.lire.mockResolvedValue({ data: { etapes: [ligne("a", "fait")] } });
        m.corriger.mockResolvedValue({ data: { ok: true } });
        render(
            <FournisseurLangue>
                <Sonde id={3} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(m.lire).toHaveBeenCalledTimes(1));
        await act(async () => useRecalculDuPret.getState().demander());
        await waitFor(() => expect(m.lire.mock.calls.length).toBeGreaterThanOrEqual(2));
        const avant = m.lire.mock.calls.length;
        fireEvent.click(screen.getByText("corriger"));
        await waitFor(() => expect(m.corriger).toHaveBeenCalledTimes(1));
        expect(m.corriger.mock.calls[0][0]).toMatchObject({ path: { workflow_id: 3 }, body: { correction: "allumer_la_fiche", noeud_id: null, liaison_id: null } });
        await waitFor(() => expect(m.lire.mock.calls.length).toBeGreaterThan(avant));
    });
});
