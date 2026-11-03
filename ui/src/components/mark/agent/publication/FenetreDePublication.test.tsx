/**
 * [.mark] U11 : la fenêtre « Publier vX ».
 *
 * Questions de ce fichier :
 *
 *     Les contrôles viennent du serveur, chacun sur ses trois positions ? Changer une position l'écrit ? Un contrôle bloquant
 *     qui échoue ferme « Publier » et ouvre « Forcer », qui exige une raison avant d'envoyer `forcer` ? Un point de la liste
 *     vocale « sans équivalent chez nous » dit sa raison ? Le déploiement progressif n'apparaît que s'il est allumé, et la part
 *     choisie part avec la publication ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FenetreDePublication } from "./FenetreDePublication";
import type { VueDePublication } from "./types";

const m = vi.hoisted(() => ({ lire: vi.fn(), regler: vi.fn(), corriger: vi.fn(), publier: vi.fn() }));
vi.mock("next/link", () => ({ default: ({ children, href, ...r }: { children: React.ReactNode; href: string }) => <a href={href} {...r}>{children}</a> }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { promise: vi.fn(), success: vi.fn(), error: vi.fn() }) }));
vi.mock("@/client/sdk.gen", () => ({
    controlesDePublicationApiV1BuilderPublicationWorkflowIdGet: (o: unknown) => m.lire(o),
    reglerLaPublicationApiV1BuilderPublicationWorkflowIdReglagesPut: (o: unknown) => m.regler(o),
    corrigerLaListeVocaleApiV1BuilderPublicationWorkflowIdListeVocaleCorrigerPost: (o: unknown) => m.corriger(o),
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost: (o: unknown) => m.publier(o),
}));

const vue = (surcharge: Partial<VueDePublication> = {}): VueDePublication => ({
    version: 3,
    bloque: false,
    deploiement_actif: false,
    forcable: true,
    liste_vocale: [],
    controles: [
        { cle: "tests_obligatoires", libelle: "Required tests", position: "bloque", statut: "ok", problemes: [] },
        { cle: "bilan_du_prompt", libelle: "Bilan", position: "bloque", statut: "ok", problemes: [] },
        { cle: "liste_vocale", libelle: "Liste", position: "eteint", statut: "eteint", problemes: [] },
        { cle: "attaques", libelle: "Attaques", position: "eteint", statut: "eteint", problemes: [] },
        { cle: "garde_fous", libelle: "Garde-fous", position: "eteint", statut: "eteint", problemes: [] },
    ],
    ...surcharge,
});

beforeEach(() => {
    m.lire.mockReset().mockResolvedValue({ data: vue() });
    m.regler.mockReset().mockResolvedValue({ data: { ok: true } });
    m.corriger.mockReset().mockResolvedValue({ data: { ok: true } });
    m.publier.mockReset().mockResolvedValue({ data: { id: 1 } });
});
afterEach(cleanup);

const rendre = (onPublie = vi.fn(), fermer = vi.fn()) => {
    render(<FenetreDePublication agentId={5} version={3} fermer={fermer} onPublie={onPublie} />);
    return { onPublie, fermer };
};

describe("la fenêtre « Publier »", () => {
    it("montre les cinq contrôles du serveur, chacun sur ses trois positions, et publie quand rien ne bloque", async () => {
        const { onPublie } = rendre();
        const ligne = await screen.findByText("Required tests").then((e) => e.closest("tr")!);
        expect(screen.getByText("Publish v3")).toBeTruthy();
        expect(document.querySelectorAll("[data-controle]").length).toBe(5);
        expect(within(ligne).getAllByRole("button").map((b) => b.textContent).slice(-3)).toEqual(["Off", "Warns", "Blocks"]);
        fireEvent.click(screen.getByRole("button", { name: "Publish" }));
        await waitFor(() => expect(m.publier).toHaveBeenCalled());
        expect(m.publier.mock.calls[0][0].body).toEqual({ forcer: false, raison: null, pourcentage: null });
        await waitFor(() => expect(onPublie).toHaveBeenCalled());
    });

    it("changer la position d'un contrôle l'écrit, avec les autres positions inchangées", async () => {
        rendre();
        const ligne = (await screen.findByText("Voice checklist")).closest("tr")!;
        fireEvent.click(within(ligne).getByRole("button", { name: "Warns" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][0].body).toEqual({
            controles: { tests_obligatoires: "bloque", bilan_du_prompt: "bloque", liste_vocale: "previent", attaques: "eteint", garde_fous: "eteint" },
            deploiement: { actif: false },
        });
    });

    it("un contrôle bloquant qui échoue ferme « Publier » ; forcer exige une raison avant d'envoyer", async () => {
        const controles = vue().controles.map((c) => (c.cle === "tests_obligatoires" ? { ...c, statut: "echec" as const, problemes: ["Urgence: never replayed"] } : c));
        m.lire.mockResolvedValue({ data: vue({ bloque: true, controles }) });
        const { onPublie } = rendre();
        await screen.findByText("Urgence: never replayed");
        expect(screen.queryByRole("button", { name: "Publish" })).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: /Force the publication/ }));
        const bouton = await screen.findByRole("button", { name: "Publish anyway" });
        expect((bouton as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(screen.getByLabelText("Why publish anyway"), { target: { value: "vérifié au casque" } });
        expect((bouton as HTMLButtonElement).disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() => expect(m.publier).toHaveBeenCalled());
        expect(m.publier.mock.calls[0][0].body).toEqual({ forcer: true, raison: "vérifié au casque", pourcentage: null });
        await waitFor(() => expect(onPublie).toHaveBeenCalled());
    });

    it("la liste vocale dit « sans équivalent chez nous » et ne coche que ce que le code peut corriger", async () => {
        m.lire.mockResolvedValue({
            data: vue({
                liste_vocale: [
                    { id: "interruption", libelle: "Interruption coupée", statut: "sans_equivalent", raison: "Sans équivalent chez nous : mute_always", ecarts: [], corrections: null, corrige_seul: false },
                    { id: "silence_appelant", libelle: "Silence de l'appelant", statut: "ecart", raison: "", ecarts: [{ reglage: "max_user_idle_timeout", actuel: 10, attendu: "x" }], corrections: { max_user_idle_timeout: 6 }, corrige_seul: true },
                    { id: "modele_de_secours", libelle: "Modèle de secours", statut: "ecart", raison: "", ecarts: [{ reglage: "cerveau_de_repli", actuel: "empty", attendu: "y" }], corrections: null, corrige_seul: false },
                ],
            }),
        });
        rendre();
        await screen.findByText("Interruption coupée");
        expect(screen.getByText("no equivalent here")).toBeTruthy();
        expect(screen.getAllByRole("checkbox").length).toBe(1);
        fireEvent.click(screen.getByRole("checkbox", { name: /Fix Silence/ }));
        fireEvent.click(screen.getByRole("button", { name: "Fix the ticked points" }));
        await waitFor(() => expect(m.corriger).toHaveBeenCalled());
        expect(m.corriger.mock.calls[0][0].body).toEqual({ ids: ["silence_appelant"] });
    });

    it("le déploiement progressif n'apparaît que s'il est allumé ; la part choisie part avec la publication", async () => {
        rendre();
        await screen.findByText("Required tests");
        expect(screen.queryAllByText("Deployment").length).toBe(0);
        cleanup();
        m.lire.mockResolvedValue({ data: vue({ deploiement_actif: true }) });
        rendre();
        await screen.findByRole("button", { name: "A share of the calls" });
        fireEvent.click(screen.getByRole("button", { name: "A share of the calls" }));
        fireEvent.click(screen.getByRole("button", { name: "25 %" }));
        fireEvent.click(screen.getByRole("button", { name: "Publish on 25 %" }));
        await waitFor(() => expect(m.publier).toHaveBeenCalled());
        expect(m.publier.mock.calls[0][0].body).toEqual({ forcer: false, raison: null, pourcentage: 25 });
    });

    it("une panne de lecture montre l'état d'erreur, jamais un écran blanc ni le texte du serveur", async () => {
        m.lire.mockResolvedValue({ error: { detail: "boom-serveur" } });
        rendre();
        await waitFor(() => expect(screen.getByRole("button", { name: /Try again/i })).toBeTruthy());
        expect(document.body.textContent).not.toContain("boom-serveur");
    });
});
