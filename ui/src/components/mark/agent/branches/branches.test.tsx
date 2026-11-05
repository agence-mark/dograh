/**
 * [.mark] Partie 3, SA-L3b : les branches d'agent à l'écran (repère `⑂● · v12 ▾`, Nouvelle branche, Versions, Répartition du trafic).
 *
 * Questions de ce fichier :
 *
 *     La branche ouverte se retient par onglet et par agent, et part en en-tête de chaque requête de CET agent seulement ?
 *     Le sélecteur liste les branches avec leur part et ouvre celle qu'on choisit ? « Nouvelle branche » dit sa faute sous le
 *     champ sans rien envoyer, et envoie la version de départ ? La répartition garde au moins 1 % à la principale, ne dépasse
 *     jamais 100 et envoie des parts qui font 100 ? Éteinte, elle ne se règle pas ? Les versions disent « Vous » pour son brouillon ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BranchesVue } from "@/client/types.gen";
import { agentDeAdresse, brancheOuverte, ENTETE_BRANCHE, entetesDeBranche, ouvrirBranche } from "@/lib/brancheOuverte";

import { fauteDeNom, FenetreNouvelleBranche } from "./FenetreNouvelleBranche";
import { FenetreRepartition, partsAEnvoyer, poser } from "./FenetreRepartition";
import { FenetreVersions } from "./FenetreVersions";
import { SelecteurBranche } from "./SelecteurBranche";

const m = vi.hoisted(() => ({ creer: vi.fn(), regler: vi.fn() }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    creerUneBrancheApiV1BuilderBranchesWorkflowIdPost: m.creer,
    reglerLaRepartitionApiV1BuilderBranchesWorkflowIdRepartitionPut: m.regler,
}));

const VUE: BranchesVue = {
    repartition_active: true,
    branches: [
        {
            id: 1, nom: "Principale", principale: true, protegee: false, part: 90, version_en_ligne: 3,
            versions: [{ id: 30, numero: 3, publiee_le: "2026-10-28T17:20:00Z" }, { id: 20, numero: 2, publiee_le: "2026-10-21T11:05:00Z" }],
            brouillons: [{ id: 99, numero: 4, a_moi: true }],
        },
        {
            id: 2, nom: "Accueil court", principale: false, protegee: false, part: 10, version_en_ligne: 1,
            versions: [{ id: 41, numero: 5, publiee_le: "2026-10-26T11:12:00Z" }],
            brouillons: [{ id: 98, numero: 6, a_moi: false }],
        },
        { id: 3, nom: "Urgence gaz", principale: false, protegee: false, part: 0, version_en_ligne: 2, versions: [], brouillons: [] },
    ],
};

beforeEach(() => {
    window.sessionStorage.clear();
    m.creer.mockReset().mockResolvedValue({ data: { id: 8 } });
    m.regler.mockReset().mockResolvedValue({ data: { ok: true } });
});
afterEach(cleanup);

describe("la branche ouverte dans l'onglet", () => {
    it("se retient par agent et part en en-tête des requêtes de CET agent seulement", () => {
        expect(entetesDeBranche("/agents/5")).toEqual({});
        ouvrirBranche(5, 12);
        expect(brancheOuverte(5)).toBe(12);
        expect(entetesDeBranche("/agents/5/settings")).toEqual({ [ENTETE_BRANCHE]: "12" });
        expect(entetesDeBranche("/workflow/5")).toEqual({ [ENTETE_BRANCHE]: "12" });
        expect(entetesDeBranche("/agents/6")).toEqual({}); // un autre agent : la principale
        expect(entetesDeBranche("/labo/agents")).toEqual({});
        expect(agentDeAdresse("/agents/5x")).toBeNull();
        ouvrirBranche(5, null);
        expect(entetesDeBranche("/agents/5")).toEqual({});
    });

    it("une valeur retenue illisible est ignorée", () => {
        window.sessionStorage.setItem("mark:branche:5", "abc");
        expect(brancheOuverte(5)).toBeNull();
    });
});

describe("le sélecteur de branche", () => {
    const rendre = (ouverte: number | null = null) => {
        const choisir = vi.fn();
        const nouvelle = vi.fn();
        render(<SelecteurBranche vue={VUE} ouverte={ouverte} choisir={choisir} nouvelle={nouvelle} />);
        return { choisir, nouvelle };
    };
    const ouvrirMenu = () => {
        const declencheur = screen.getByRole("button", { name: /Branch/ });
        fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
        fireEvent.click(declencheur);
    };

    it("montre la branche ouverte avec sa part, liste les autres et ouvre celle qu'on choisit", async () => {
        const { choisir } = rendre();
        expect(screen.getByRole("button", { name: "Branch : Principale · Live 90 %" })).toBeTruthy();
        ouvrirMenu();
        await screen.findByText("Accueil court");
        expect(screen.getByText("10 %")).toBeTruthy();
        expect(screen.getByText("draft")).toBeTruthy(); // « Urgence gaz » : aucune part
        fireEvent.click(screen.getByText("Accueil court"));
        expect(choisir).toHaveBeenCalledWith(2);
    });

    it("choisir la principale rend null, « New branch » ouvre la fenêtre", async () => {
        const { choisir, nouvelle } = rendre(2);
        expect(screen.getByRole("button", { name: "Branch : Accueil court · Live 10 %" })).toBeTruthy();
        ouvrirMenu();
        fireEvent.click(await screen.findByText("Principale"));
        expect(choisir).toHaveBeenCalledWith(null);
        ouvrirMenu();
        fireEvent.click(await screen.findByText("New branch"));
        expect(nouvelle).toHaveBeenCalled();
    });
});

describe("la fenêtre « Nouvelle branche »", () => {
    const rendre = () => {
        const cree = vi.fn();
        const fermer = vi.fn();
        render(<FenetreNouvelleBranche agentId={5} ouverte fermer={fermer} vue={VUE} cree={cree} />);
        return { cree, fermer };
    };

    it("dit sa faute sous le champ et n'envoie rien : nom vide, nom déjà pris (casse ignorée), trop long", async () => {
        const t = (x: { en: string; fr: string }) => x.en;
        expect(fauteDeNom("", VUE.branches, t)).toBe("Give the branch a name.");
        expect(fauteDeNom("  accueil   COURT ", VUE.branches, t)).toBe("A branch already has this name.");
        expect(fauteDeNom("x".repeat(61), VUE.branches, t)).toBe("60 characters at most.");
        expect(fauteDeNom("Nouvelle idée", VUE.branches, t)).toBeNull();
        rendre();
        fireEvent.click(screen.getByRole("button", { name: "Create the branch" }));
        expect((await screen.findByRole("alert")).textContent).toBe("Give the branch a name.");
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "accueil court" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the branch" }));
        await waitFor(() => expect(screen.getByRole("alert").textContent).toBe("A branch already has this name."));
        expect(m.creer).not.toHaveBeenCalled();
    });

    it("crée depuis la version en ligne par défaut, ou depuis la version choisie, puis ouvre la branche", async () => {
        const { cree } = rendre();
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "  Essai   court " } });
        fireEvent.click(screen.getByRole("button", { name: "Create the branch" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(m.creer.mock.calls[0][0]).toEqual({ path: { workflow_id: 5 }, body: { nom: "Essai court", depuis_version: null } });
        await waitFor(() => expect(cree).toHaveBeenCalledWith(8));
    });

    it("un refus du serveur garde la fenêtre et la saisie, sans montrer le texte du serveur", async () => {
        m.creer.mockResolvedValue({ error: { detail: "A branch with this name already exists" } });
        const { cree, fermer } = rendre();
        fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Essai" } });
        fireEvent.click(screen.getByRole("button", { name: "Create the branch" }));
        await waitFor(() => expect(m.creer).toHaveBeenCalled());
        expect(cree).not.toHaveBeenCalled();
        expect(fermer).not.toHaveBeenCalled();
        expect((screen.getByLabelText("Name") as HTMLInputElement).value).toBe("Essai");
        expect(document.body.textContent).not.toContain("A branch with this name already exists");
    });
});

describe("la répartition du trafic", () => {
    it("la principale prend le reste : les parts envoyées font toujours 100", () => {
        expect(partsAEnvoyer(VUE, { 2: 25, 3: 5 })).toEqual({ 2: 25, 3: 5, 1: 70 });
        expect(partsAEnvoyer(VUE, {})).toEqual({ 2: 0, 3: 0, 1: 100 });
    });

    it("garde au moins 1 % à la principale : la somme des autres branches ne dépasse pas 99", () => {
        expect(poser({ 2: 60, 3: 0 }, 3, 80)).toEqual({ 2: 60, 3: 39 });
        expect(poser({ 2: 0, 3: 0 }, 2, 150)).toEqual({ 2: 99, 3: 0 });
        expect(poser({ 2: 10, 3: 0 }, 2, -4)).toEqual({ 2: 0, 3: 0 });
    });

    const rendre = (vue: BranchesVue = VUE) => {
        const apres = vi.fn();
        render(<FenetreRepartition agentId={5} ouverte fermer={vi.fn()} vue={vue} apres={apres} />);
        return { apres };
    };

    it("montre un curseur par branche (hors principale) et la part de la principale qui suit", () => {
        rendre();
        const curseur = screen.getByLabelText("Accueil court") as HTMLInputElement;
        expect(curseur.min).toBe("0");
        expect(curseur.max).toBe("99");
        expect(curseur.value).toBe("10");
        expect(document.querySelector("[data-part-principale]")?.textContent).toBe("90 %");
        fireEvent.change(curseur, { target: { value: "40" } });
        expect(document.querySelector("[data-part-principale]")?.textContent).toBe("60 %");
        fireEvent.change(screen.getByLabelText("Urgence gaz"), { target: { value: "70" } });
        // 40 + 70 dépasse 99 : le curseur s'arrête à ce qui reste
        expect((screen.getByLabelText("Urgence gaz") as HTMLInputElement).value).toBe("59");
        expect(document.querySelector("[data-part-principale]")?.textContent).toBe("1 %");
    });

    it("envoie les parts de toutes les branches et dit le résultat ; un refus garde la fenêtre", async () => {
        const { apres } = rendre();
        fireEvent.change(screen.getByLabelText("Accueil court"), { target: { value: "25" } });
        fireEvent.click(screen.getByRole("button", { name: "Apply" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][0]).toEqual({ path: { workflow_id: 5 }, body: { parts: { 2: 25, 3: 0, 1: 75 } } });
        await waitFor(() => expect(apres).toHaveBeenCalled());
    });

    it("un refus du serveur n'ouvre rien de plus et ne montre pas son texte", async () => {
        m.regler.mockResolvedValue({ error: { detail: "The shares must add up to 100" } });
        const { apres } = rendre();
        fireEvent.click(screen.getByRole("button", { name: "Apply" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(apres).not.toHaveBeenCalled();
        expect(document.body.textContent).not.toContain("The shares must add up to 100");
    });

    it("éteinte pour l'agent : les curseurs sont grisés et la phrase dit où l'allumer", () => {
        rendre({ ...VUE, repartition_active: false });
        expect((screen.getByLabelText("Accueil court") as HTMLInputElement).disabled).toBe(true);
        expect(screen.getByRole("status").textContent).toContain("Settings > Publication");
    });
});

describe("les versions", () => {
    it("liste les branches, les versions de la branche choisie et les brouillons (« You » pour le sien)", () => {
        const ouvrir = vi.fn();
        render(<FenetreVersions ouverte fermer={vi.fn()} vue={VUE} ouverteId={null} ouvrir={ouvrir} repartition={vi.fn()} />);
        expect(screen.getByText("v3")).toBeTruthy();
        expect(screen.getByText("live")).toBeTruthy();
        expect(screen.getByText("You")).toBeTruthy();
        expect(screen.getByText("Someone else")).toBeTruthy();
        fireEvent.click(screen.getAllByRole("button", { name: "Open" })[0]);
        expect(ouvrir).toHaveBeenCalledWith(2);
        fireEvent.click(screen.getByRole("button", { name: /Accueil court/ }));
        expect(screen.getByText("v5")).toBeTruthy();
    });

    it("la répartition s'ouvre depuis les versions", () => {
        const repartition = vi.fn();
        render(<FenetreVersions ouverte fermer={vi.fn()} vue={VUE} ouverteId={2} ouvrir={vi.fn()} repartition={repartition} />);
        fireEvent.click(screen.getByRole("button", { name: "Traffic split" }));
        expect(repartition).toHaveBeenCalled();
    });
});
