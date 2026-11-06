/**
 * [.mark] K6 : la liste du Chat et la carte du plan à la forme de la maquette. Questions : « quand » dit-il l'instant, les heures, hier
 * et la date dans les deux langues ? la recherche filtre-t-elle sur le titre et l'agent ? la pastille rouge marque-t-elle les changements
 * à valider ? le plan dit-il « 2 sur 3 » avec sa barre ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CarteDuPlan } from "./cartes";
import { ListeDesFils, quand } from "./ListeDesFils";

const m = vi.hoisted(() => ({
    renommer: vi.fn(),
    supprimer: vi.fn(),
    notifier: { succes: vi.fn(), echec: vi.fn() },
    erreurRenommer: false,
    erreurSupprimer: false,
}));

vi.mock("@/components/mark/notifications", () => ({ notifier: m.notifier }));
const compte = vi.hoisted(() => ({ user: { id: 1 }, loading: false })); // un objet stable : le vrai useAuth n'en rend pas un neuf à chaque rendu
vi.mock("@/lib/auth", () => ({ useAuth: () => compte }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("next/navigation", () => ({ usePathname: () => "/labo/builder" }));
vi.mock("@/components/mark/studio/nom-espace", () => ({ useNomEspace: () => null }));
vi.mock("@/client", () => ({
    listerLesFilsApiV1BuilderFilsGet: async () => ({
        data: [
            { id: 1, workflow_id: 7, titre: "Relecture du numéro", etat: "terminee", changements: 3, genre: "principal", auteur: null, modifie_le: new Date().toISOString() },
            { id: 2, workflow_id: null, titre: "Banc A", etat: "arretee", changements: 0, genre: "principal", auteur: null, modifie_le: new Date().toISOString() },
        ],
    }),
    getWorkflowsSummaryApiV1WorkflowSummaryGet: async () => ({ data: [{ id: 7, name: "Standard Durand" }] }),
    renommerUnFilApiV1BuilderFilsFilIdTitrePut: async (o: { path: { fil_id: number }; body: { titre: string } }) => {
        m.renommer(o);
        return m.erreurRenommer ? { error: { detail: "boom" } } : { data: { id: o.path.fil_id, titre: o.body.titre } };
    },
    supprimerUnFilApiV1BuilderFilsFilIdDelete: async (o: unknown) => {
        m.supprimer(o);
        return m.erreurSupprimer ? { error: { detail: "boom" } } : {};
    },
    // Le direct d'I1 : un flux qui ne rend rien.
    suivreLesModificationsApiV1BuilderLiveGet: () => new Promise(() => undefined),
}));

beforeEach(() => {
    vi.clearAllMocks();
    m.erreurRenommer = false;
    m.erreurSupprimer = false;
});
afterEach(cleanup);

async function ouvrirLeMenu(titre: string) {
    const ligne = (await screen.findByText(titre)).closest("li") as HTMLElement;
    const declencheur = ligne.querySelector('button[aria-label="Plus"], button[aria-label="More"]') as HTMLElement;
    fireEvent.pointerDown(declencheur, { button: 0, ctrlKey: false });
    fireEvent.click(declencheur);
    await screen.findByRole("menu");
}

describe("quand", () => {
    const maintenant = Date.parse("2026-11-04T12:00:00Z");
    it("dit l'instant, les heures, hier puis la date", () => {
        expect(quand("2026-11-04T11:59:40Z", "fr", maintenant)).toBe("À l'instant");
        expect(quand("2026-11-04T11:59:40Z", "en", maintenant)).toBe("Just now");
        expect(quand("2026-11-04T10:00:00Z", "fr", maintenant)).toMatch(/2 h/);
        expect(quand("2026-11-03T08:00:00Z", "fr", maintenant)).toMatch(/hier/i);
        expect(quand("2026-10-20T08:00:00Z", "fr", maintenant)).toBe("20/10");
        expect(quand(undefined, "fr", maintenant)).toBe("");
    });
});

describe("liste du Chat", () => {
    it("montre l'agent, la pastille des changements, et filtre par la recherche", async () => {
        render(<ListeDesFils />);
        expect(await screen.findByText("Standard Durand")).toBeTruthy();
        expect(screen.getByText("3")).toBeTruthy();
        fireEvent.change(screen.getByLabelText(/Rechercher un chat|Search a chat/), { target: { value: "banc" } });
        expect(screen.queryByText("Relecture du numéro")).toBeNull();
        expect(screen.getByText("Banc A")).toBeTruthy();
    });
});

describe("carte du plan", () => {
    it("dit « 1 sur 3 » avec une barre à un tiers", () => {
        render(<CarteDuPlan etapes={[{ libelle: "A", etat: "fait" }, { libelle: "B", etat: "en_cours" }, { libelle: "C", etat: "a_venir" }]} />);
        expect(screen.getByText(/1 (sur|of) 3/)).toBeTruthy();
        expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
    });
});

describe("menu ⋮ du Chat", () => {
    it("renomme en place : la route reçoit le titre, la liste le montre, une notification le dit", async () => {
        render(<ListeDesFils />);
        await ouvrirLeMenu("Banc A");
        fireEvent.click(await screen.findByRole("menuitem", { name: /Renommer|Rename/ }));
        const champ = screen.getByLabelText(/Nouveau titre|New title/) as HTMLInputElement;
        fireEvent.change(champ, { target: { value: "Banc B" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await waitFor(() => expect(m.renommer).toHaveBeenCalledWith({ path: { fil_id: 2 }, body: { titre: "Banc B" } }));
        expect(await screen.findByText("Banc B")).toBeTruthy();
        expect(m.notifier.succes).toHaveBeenCalled();
    });

    it("n'écrit rien si le titre n'a pas changé, et dit l'échec sans le texte du serveur", async () => {
        render(<ListeDesFils />);
        await ouvrirLeMenu("Banc A");
        fireEvent.click(await screen.findByRole("menuitem", { name: /Renommer|Rename/ }));
        fireEvent.keyDown(screen.getByLabelText(/Nouveau titre|New title/), { key: "Enter" });
        expect(m.renommer).not.toHaveBeenCalled();
        await ouvrirLeMenu("Banc A");
        fireEvent.click(await screen.findByRole("menuitem", { name: /Renommer|Rename/ }));
        m.erreurRenommer = true;
        const champ = screen.getByLabelText(/Nouveau titre|New title/);
        fireEvent.change(champ, { target: { value: "Autre" } });
        fireEvent.keyDown(champ, { key: "Enter" });
        await waitFor(() => expect(m.notifier.echec).toHaveBeenCalled());
        expect(JSON.stringify(m.notifier.echec.mock.calls[0][0])).not.toContain("boom");
        expect(screen.getByText("Banc A")).toBeTruthy();
    });

    it("supprime seulement après la confirmation, puis retire la ligne", async () => {
        render(<ListeDesFils />);
        await ouvrirLeMenu("Banc A");
        fireEvent.click(await screen.findByRole("menuitem", { name: /Supprimer|Delete/ }));
        expect(m.supprimer).not.toHaveBeenCalled(); // la fenêtre de confirmation d'abord
        expect(await screen.findByText(/Supprimer ce chat|Delete this chat/)).toBeTruthy();
        fireEvent.click(screen.getAllByRole("button", { name: /^Supprimer$|^Delete$/ }).at(-1) as HTMLElement);
        await waitFor(() => expect(m.supprimer).toHaveBeenCalledWith({ path: { fil_id: 2 } }));
        await waitFor(() => expect(screen.queryByText("Banc A")).toBeNull());
        expect(m.notifier.succes).toHaveBeenCalled();
    });

    it("garde la ligne et dit l'échec quand la suppression est refusée", async () => {
        m.erreurSupprimer = true;
        render(<ListeDesFils />);
        await ouvrirLeMenu("Banc A");
        fireEvent.click(await screen.findByRole("menuitem", { name: /Supprimer|Delete/ }));
        fireEvent.click(screen.getAllByRole("button", { name: /^Supprimer$|^Delete$/ }).at(-1) as HTMLElement);
        await waitFor(() => expect(m.notifier.echec).toHaveBeenCalled());
        expect(screen.getByText("Banc A")).toBeTruthy();
    });
});
