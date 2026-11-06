/**
 * [.mark] Partie 3, SA-L3c : fusionner, mettre à jour, protéger, revenir à une version de la principale, comparer.
 *
 * Questions de ce fichier :
 *
 *     La fusion montre ce qui change et les conflits à trancher, et reste éteinte tant qu'un conflit n'a pas de choix ?
 *     Sur une principale protégée, elle exige « Fusion relue » ? Elle envoie les choix et les versions lues dans l'aperçu ?
 *     Un aperçu périmé (409) se relit au lieu d'écrire ? La mise à jour dit « déjà à jour » ? Les versions proposent « Revenir à la
 *     vN » sur la principale seulement, la protection et les gestes sur les autres branches ? Comparer met la meilleure valeur en
 *     évidence, dit le verdict et groupe la configuration par famille ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ApercuDeFusion, ApercuDeMiseAJour, BranchesVue, ComparaisonVue } from "@/client/types.gen";

import { lireNotifications, notifier, viderNotifications } from "@/components/mark/notifications";

import { FenetreFusion } from "./FenetreFusion";
import { FenetreVersions } from "./FenetreVersions";
import { ContexteNomAgent } from "../contexte-agent";
import { ecartDe, formater, PageComparer } from "./PageComparer";

const m = vi.hoisted(() => ({
    apercuFusion: vi.fn(),
    apercuMaj: vi.fn(),
    fusionner: vi.fn(),
    majPost: vi.fn(),
    defaire: vi.fn(),
    epingler: vi.fn(),
    proteger: vi.fn(),
    comparer: vi.fn(),
    lire: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("next/link", () => ({ default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/client/sdk.gen", () => ({
    apercuDeLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionGet: m.apercuFusion,
    apercuDeLaMiseAJourApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourGet: m.apercuMaj,
    fusionnerUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdFusionPost: m.fusionner,
    mettreAJourUneBrancheApiV1BuilderBranchesWorkflowIdBranchIdMiseAJourPost: m.majPost,
    defaireLaFusionApiV1BuilderBranchesWorkflowIdBranchIdFusionDefairePost: m.defaire,
    epinglerLaPrincipaleApiV1BuilderBranchesWorkflowIdPrincipaleVersionPut: m.epingler,
    protegerLaPrincipaleApiV1BuilderBranchesWorkflowIdPrincipaleProtectionPut: m.proteger,
    comparerEnDuelApiV1BuilderBranchesWorkflowIdComparerGet: m.comparer,
    lireLesBranchesApiV1BuilderBranchesWorkflowIdGet: m.lire,
}));

const FUSION: ApercuDeFusion = {
    branche: { id: 2, nom: "Accueil court", version: 5, id_version: 41 },
    cible: { nom: "Principale", version: 3, id_version: 30 },
    depart: { version: 2 },
    champs: [
        { cle: "prompt:1", famille: "prompts", libelle: "Départ", statut: "reprise", avant: "Bonjour", source: "Allô, cabinet", cible: "Bonjour" },
        { cle: "prompt:2", famille: "prompts", libelle: "Fin", statut: "conflit", avant: "Au revoir", source: "À bientôt", cible: "Bonne journée" },
        { cle: "reglage:voix", famille: "reglages", libelle: "voix", statut: "gardee", avant: "a", source: "a", cible: "b" },
    ],
    resume: { reprise: 1, gardee: 1, conflit: 1 },
    problemes: [],
    protegee: true,
    relue_obligatoire: true,
    trafic: { part_branche: 10, part_principale: 90, part_principale_apres: 100 },
    defaisable: false,
};

const rendreFusion = (apercu: Partial<ApercuDeFusion> = {}, sens: "fusion" | "maj" = "fusion") => {
    m.apercuFusion.mockResolvedValue({ data: { ...FUSION, ...apercu } });
    const apres = vi.fn();
    const fermer = vi.fn();
    render(<FenetreFusion agentId={5} brancheId={2} sens={sens} ouverte fermer={fermer} apres={apres} />);
    return { apres, fermer };
};

beforeEach(() => {
    for (const f of Object.values(m)) f.mockReset();
    m.fusionner.mockResolvedValue({ data: { ok: true } });
    m.majPost.mockResolvedValue({ data: { ok: true } });
    m.defaire.mockResolvedValue({ data: { ok: true } });
    m.epingler.mockResolvedValue({ data: { ok: true } });
    m.proteger.mockResolvedValue({ data: { ok: true, protegee: true, protegee_par_defaut: false } });
});
afterEach(cleanup);

const bouton = (nom: RegExp | string) => screen.getByRole("button", { name: nom }) as HTMLButtonElement;

describe("la fusion", () => {
    it("montre ce qui change, les conflits à trancher et l'effet sur le trafic", async () => {
        rendreFusion();
        await screen.findByText("What changes");
        expect(document.body.textContent).toContain("Bonjour → Allô, cabinet"); // la valeur reprise, de la cible vers la source
        expect(screen.getByText("To decide", { exact: false })).toBeTruthy();
        expect(screen.getByRole("radiogroup", { name: "Fin" })).toBeTruthy();
        expect(document.querySelector("[data-trafic]")?.textContent).toContain("90 % → 100 %");
        expect(document.querySelector("[data-trafic]")?.textContent).toContain("10 %");
    });

    it("reste éteinte tant qu'un conflit n'a pas de choix, et exige « Fusion relue » sur une principale protégée", async () => {
        rendreFusion();
        await screen.findByText("What changes");
        expect(bouton("Merge").disabled).toBe(true);
        fireEvent.click(screen.getAllByRole("radio", { name: /Keep Accueil court/ })[0]);
        expect(bouton("Merge").disabled).toBe(true); // le conflit est choisi, la relecture manque
        fireEvent.click(screen.getByRole("checkbox", { name: "Merge reviewed" }));
        expect(bouton("Merge").disabled).toBe(false);
    });

    it("envoie les choix, la relecture et les versions lues dans l'aperçu, puis relit les branches", async () => {
        const { apres, fermer } = rendreFusion();
        await screen.findByText("What changes");
        fireEvent.click(screen.getAllByRole("radio", { name: /Keep Main/ })[0]);
        fireEvent.click(screen.getByRole("checkbox", { name: "Merge reviewed" }));
        fireEvent.click(bouton("Merge"));
        await waitFor(() => expect(m.fusionner).toHaveBeenCalled());
        expect(m.fusionner.mock.calls[0][0]).toEqual({
            path: { workflow_id: 5, branch_id: 2 },
            body: { choix: { "prompt:2": "cible" }, relue: true, version_branche: 41, version_cible: 30 },
        });
        await waitFor(() => expect(apres).toHaveBeenCalledWith("fusion"));
        expect(fermer).toHaveBeenCalled();
    });

    it("sans protection, aucune case de relecture", async () => {
        rendreFusion({ protegee: false, relue_obligatoire: false });
        await screen.findByText("What changes");
        expect(screen.queryByRole("checkbox", { name: "Merge reviewed" })).toBeNull();
        fireEvent.click(screen.getAllByRole("radio", { name: /Keep Accueil court/ })[0]);
        expect(bouton("Merge").disabled).toBe(false);
    });

    it("un problème dit ce qui bloque et garde le bouton éteint", async () => {
        rendreFusion({ champs: [], resume: { reprise: 0, gardee: 0, conflit: 0 }, protegee: false, relue_obligatoire: false, problemes: [{ code: "brouillon_en_attente" }] });
        await screen.findByRole("alert");
        expect(screen.getByRole("alert").textContent).toContain("unpublished draft");
        expect(bouton("Merge").disabled).toBe(true);
    });

    it("un aperçu périmé (409) relit l'aperçu au lieu d'écrire quoi que ce soit de plus", async () => {
        rendreFusion({ protegee: false, relue_obligatoire: false });
        await screen.findByText("What changes");
        fireEvent.click(screen.getAllByRole("radio", { name: /Keep Accueil court/ })[0]);
        m.fusionner.mockResolvedValue({ error: { detail: "The branch or the main branch changed since the preview: read it again" }, response: { status: 409 } });
        fireEvent.click(bouton("Merge"));
        await waitFor(() => expect(m.apercuFusion).toHaveBeenCalledTimes(2));
    });
});

describe("la mise à jour depuis la principale", () => {
    const MAJ: ApercuDeMiseAJour = {
        branche: { id: 2, nom: "Accueil court", version: 5, brouillon: true, id_base: 20 },
        principale: { version: 3, id_version: 30 },
        depart: { version: 2 },
        a_jour: false,
        champs: [{ cle: "prompt:2", famille: "prompts", libelle: "Fin", statut: "reprise", avant: "Au revoir", source: "À bientôt", cible: "Au revoir" }],
        resume: { reprise: 1, gardee: 0, conflit: 0 },
        problemes: [],
    };

    it("envoie la version de la principale et la base lues, sans case de relecture", async () => {
        m.apercuMaj.mockResolvedValue({ data: MAJ });
        const apres = vi.fn();
        render(<FenetreFusion agentId={5} brancheId={2} sens="maj" ouverte fermer={vi.fn()} apres={apres} />);
        await screen.findByText("What changes");
        expect(screen.queryByRole("checkbox")).toBeNull();
        fireEvent.click(bouton("Update"));
        await waitFor(() => expect(m.majPost).toHaveBeenCalled());
        expect(m.majPost.mock.calls[0][0].body).toEqual({ choix: {}, version_principale: 30, base_attendue: 20 });
        await waitFor(() => expect(apres).toHaveBeenCalledWith("maj"));
    });

    it("une branche déjà à jour le dit et ne se met pas à jour", async () => {
        m.apercuMaj.mockResolvedValue({ data: { ...MAJ, a_jour: true, champs: [] } });
        render(<FenetreFusion agentId={5} brancheId={2} sens="maj" ouverte fermer={vi.fn()} apres={vi.fn()} />);
        await screen.findByText("This branch is already up to date with the main branch.");
        expect(bouton("Update").disabled).toBe(true);
    });
});

const VUE: BranchesVue = {
    repartition_active: true,
    branches: [
        {
            id: 1, nom: "Principale", principale: true, protegee: false, protegee_par_defaut: false, part: 90, version_en_ligne: 3,
            versions: [{ id: 30, numero: 3, publiee_le: null }, { id: 20, numero: 2, publiee_le: null }],
            brouillons: [],
        },
        { id: 2, nom: "Accueil court", principale: false, protegee: false, protegee_par_defaut: false, part: 10, version_en_ligne: 5, versions: [{ id: 41, numero: 5, publiee_le: null }], brouillons: [] },
        { id: 3, nom: "Vide", principale: false, protegee: false, protegee_par_defaut: false, part: 0, version_en_ligne: null, versions: [], brouillons: [] },
    ],
};

describe("les versions : gestes de L3c", () => {
    const rendre = (vue: BranchesVue = VUE) => {
        const p = { fusionner: vi.fn(), mettreAJour: vi.fn(), apres: vi.fn() };
        render(<FenetreVersions agentId={5} ouverte fermer={vi.fn()} vue={vue} ouverteId={null} ouvrir={vi.fn()} repartition={vi.fn()} {...p} />);
        return p;
    };

    it("Fusionner et Mettre à jour sur les branches autres que la principale ; Fusionner éteint sans version publiée", () => {
        const p = rendre();
        const fusionner = screen.getAllByRole("button", { name: /Merge/ });
        expect(fusionner).toHaveLength(2);
        expect((fusionner[1] as HTMLButtonElement).disabled).toBe(true); // « Vide » n'a pas de version
        fireEvent.click(fusionner[0]);
        expect(p.fusionner).toHaveBeenCalledWith(2);
        fireEvent.click(screen.getAllByRole("button", { name: "Update" })[0]);
        expect(p.mettreAJour).toHaveBeenCalledWith(2);
        expect(screen.getByRole("link", { name: /Compare two branches or versions/ }).getAttribute("href")).toBe("/agents/5/comparer");
    });

    it("« Revenir à la vN » seulement sur les versions de la principale qui ne sont pas en ligne", async () => {
        const p = rendre();
        expect(screen.queryByRole("button", { name: "Go back to v3" })).toBeNull(); // la version en ligne
        fireEvent.click(screen.getByRole("button", { name: "Go back to v2" }));
        await waitFor(() => expect(m.epingler).toHaveBeenCalledWith({ path: { workflow_id: 5 }, body: { version: 2 } }));
        await waitFor(() => expect(p.apres).toHaveBeenCalled());
        fireEvent.click(screen.getByRole("button", { name: /Accueil court/ }));
        expect(screen.queryByRole("button", { name: /Go back to/ })).toBeNull(); // une autre branche : pas de retour à la vN
    });

    it("la protection se pose et se lève ; protégée par la règle, aucun bouton pour la lever", async () => {
        const p = rendre();
        fireEvent.click(screen.getByRole("button", { name: "Protect" }));
        await waitFor(() => expect(m.proteger).toHaveBeenCalledWith({ path: { workflow_id: 5 }, body: { protegee: true } }));
        await waitFor(() => expect(p.apres).toHaveBeenCalled());
        cleanup();
        const defaut = structuredClone(VUE);
        defaut.branches[0].protegee = true;
        defaut.branches[0].protegee_par_defaut = true;
        render(<FenetreVersions agentId={5} ouverte fermer={vi.fn()} vue={defaut} ouverteId={null} ouvrir={vi.fn()} repartition={vi.fn()} fusionner={vi.fn()} mettreAJour={vi.fn()} apres={vi.fn()} />);
        expect(screen.queryByRole("button", { name: "Lift protection" })).toBeNull();
        expect(screen.queryByRole("button", { name: "Protect" })).toBeNull();
        expect(screen.getByText(/protected/)).toBeTruthy();
    });
});

const COMPARAISON: ComparaisonVue = {
    jours: 7,
    appels_min: 5,
    gauche: { type: "branche", id: 1, nom: "Principale", version: 3, part: 70 },
    droite: { type: "branche", id: 2, nom: "Accueil court", version: 5, part: 30 },
    mesures: [
        { cle: "part", gauche: 70, droite: 30, ecart: -40, meilleur: null },
        { cle: "appels", gauche: 20, droite: 10, ecart: -10, meilleur: null },
        { cle: "resolution", gauche: 0.5, droite: 0.8, ecart: 0.3, meilleur: "droite" },
        { cle: "transferts", gauche: 0.2, droite: 0.1, ecart: -0.1, meilleur: null },
        { cle: "note", gauche: 3, droite: 4, ecart: 1, meilleur: "droite" },
        { cle: "cout", gauche: 0.2, droite: 0.3, ecart: 0.1, meilleur: "gauche" },
        { cle: "latence", gauche: null, droite: null, ecart: null, meilleur: null },
    ],
    verdict: { gagnant: "droite", pour_gauche: ["cout"], pour_droite: ["resolution", "note"] },
    configuration: [
        { cle: "prompt:1", famille: "prompts", libelle: "Départ", avant: "Bonjour", apres: "Allô, cabinet" },
        { cle: "reglage:voix", famille: "reglages", libelle: "voix", avant: null, apres: "b" },
    ],
};

describe("comparer en duel", () => {
    beforeEach(() => {
        m.lire.mockResolvedValue({ data: VUE });
        m.comparer.mockResolvedValue({ data: COMPARAISON });
    });

    it("met la meilleure valeur en évidence, dit le verdict et lit les deux côtés de l'adresse", async () => {
        render(<PageComparer agentId={5} />);
        await screen.findByText("Results");
        expect(m.comparer).toHaveBeenCalledWith({ path: { workflow_id: 5 }, query: { gauche: "branche:1", droite: "branche:2" } });
        const meilleurs = Array.from(document.querySelectorAll("[data-meilleur]")).map((n) => n.textContent);
        expect(meilleurs).toEqual(["80 %", "4 / 5", "0,2 $"]); // la résolution et la note à droite, le coût (plus bas) à gauche
        expect(document.querySelector("[data-verdict]")?.textContent).toContain("Accueil court");
        expect(document.querySelector("[data-verdict]")?.textContent).toContain("2 of 3 measures");
        expect(screen.getByText("Median latency").closest("tr")?.textContent).toContain("–"); // une donnée absente reste vide
        expect(document.querySelector("[data-cote=gauche]")?.textContent).toContain("70 % of the calls");
    });

    it("T6 : une flèche « Retour à ⟦agent⟧ » devant le titre ramène à l'agent", async () => {
        render(
            <ContexteNomAgent.Provider value="Cabinet Dupont">
                <PageComparer agentId={5} />
            </ContexteNomAgent.Provider>,
        );
        await screen.findByText("Results");
        const fleche = document.querySelector('a[href="/agents/5"]') as HTMLAnchorElement;
        expect(fleche.getAttribute("href")).toBe("/agents/5");
        expect(fleche.textContent).toContain("Back to Cabinet Dupont");
        expect(fleche.compareDocumentPosition(screen.getByRole("heading", { level: 1 })) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });

    it("groupe la différence de configuration par famille, repliable, avant barré et après", async () => {
        render(<PageComparer agentId={5} />);
        await screen.findByText("Configuration difference");
        const prompts = document.querySelector("[data-famille=prompts]")!;
        expect(prompts.textContent).toContain("Bonjour");
        expect(prompts.textContent).toContain("Allô, cabinet");
        expect(document.querySelector("[data-famille=reglages]")?.textContent).toContain("(absent)");
        fireEvent.click(prompts.querySelector("button")!);
        expect(prompts.textContent).not.toContain("Allô, cabinet");
    });

    it("« Fusionner la deuxième dans la première » ouvre la fusion de la branche B, seulement si A est la principale", async () => {
        m.apercuFusion.mockResolvedValue({ data: FUSION });
        render(<PageComparer agentId={5} />);
        fireEvent.click(await screen.findByRole("button", { name: "Merge the second into the first" }));
        await screen.findByTestId("fenetre-fusion");
        expect(m.apercuFusion.mock.calls[0][0]).toEqual({ path: { workflow_id: 5, branch_id: 2 } });
        cleanup();
        // l'échange met la branche en A : plus de fusion proposée
        render(<PageComparer agentId={5} />);
        await screen.findByText("Results");
        fireEvent.click(screen.getByRole("button", { name: "Swap the two sides" }));
        await waitFor(() => expect(screen.queryByRole("button", { name: "Merge the second into the first" })).toBeNull());
    });

    it("« insuffisant » sous cinq appels d'un côté", async () => {
        m.comparer.mockResolvedValue({ data: { ...COMPARAISON, verdict: { gagnant: "insuffisant", pour_gauche: [], pour_droite: [] } } });
        render(<PageComparer agentId={5} />);
        await screen.findByText(/Fewer than 5 calls/);
    });

    it("l'échange des deux côtés relit la comparaison dans l'autre sens", async () => {
        render(<PageComparer agentId={5} />);
        await screen.findByText("Results");
        fireEvent.click(screen.getByRole("button", { name: "Swap the two sides" }));
        await waitFor(() => expect(m.comparer).toHaveBeenLastCalledWith({ path: { workflow_id: 5 }, query: { gauche: "branche:2", droite: "branche:1" } }));
    });
});

describe("la mise en forme des chiffres", () => {
    it("lit les parts en %, la note sur 5, le coût en $ et la latence en s ; une donnée absente est un tiret", () => {
        expect(formater("part", 30)).toBe("30 %");
        expect(formater("resolution", 0.8)).toBe("80 %");
        expect(formater("note", 4)).toBe("4 / 5");
        expect(formater("cout", 0.3)).toBe("0,3 $");
        expect(formater("latence", 1.25)).toBe("1,25 s");
        expect(formater("latence", null)).toBe("–");
    });

    it("l'écart se lit de A vers B, en points pour une part", () => {
        expect(ecartDe({ cle: "resolution", gauche: 0.5, droite: 0.8, ecart: 0.3, meilleur: "droite" })).toEqual({ texte: "+30 pts", signe: 1 });
        expect(ecartDe({ cle: "cout", gauche: 0.2, droite: 0.1, ecart: -0.1, meilleur: "droite" })).toEqual({ texte: "−0,1 $", signe: -1 });
        expect(ecartDe({ cle: "latence", gauche: null, droite: 1, ecart: null, meilleur: null })).toBeNull();
    });
});

describe("la principale protégée refuse une écriture", () => {
    it("quelle que soit l'action, la notification dit que la principale est protégée et quoi faire", () => {
        viderNotifications();
        notifier.echec({ fr: "Enregistrement impossible.", en: "Could not save." }, { erreur: { detail: "The main branch is protected: ...", code: "principale_protegee" } });
        const [n] = lireNotifications();
        expect(n.texte.en).toContain("The main branch is protected");
        expect(n.texte.en).toContain("merge it after a review");
        viderNotifications();
        notifier.echec({ fr: "Enregistrement impossible.", en: "Could not save." }, { erreur: { detail: "autre", code: "autre" } });
        expect(lireNotifications()[0].texte.en).toBe("Could not save.");
    });
});
