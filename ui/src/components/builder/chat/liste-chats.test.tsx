/**
 * [.mark] K6 : la liste du Chat et la carte du plan à la forme de la maquette. Questions : « quand » dit-il l'instant, les heures, hier
 * et la date dans les deux langues ? la recherche filtre-t-elle sur le titre et l'agent ? la pastille rouge marque-t-elle les changements
 * à valider ? le plan dit-il « 2 sur 3 » avec sa barre ?
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CarteDuPlan } from "./cartes";
import { ListeDesFils, quand } from "./ListeDesFils";

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
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
}));

afterEach(cleanup);

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
