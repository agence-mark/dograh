/**
 * [.mark] Partie 3, sous-lot 6 (SE-11 = D-3): la fenêtre « Planifier la suite » et le bandeau d'alerte de l'onglet Tests.
 *
 * Questions de ce fichier :
 *
 *     La planification est-elle éteinte tant qu'on ne l'allume pas, et l'enregistrement envoie-t-il le rejeu (fréquence, jour, heure,
 *     essais) et l'alerte (actif, seuils, mail) aux bonnes routes ? « Vérifier maintenant » est-il refusé tant qu'une saisie n'est
 *     pas enregistrée ? Les dernières exécutions disent-elles la régression ? Le bandeau montre-t-il l'alerte, pointe-t-il vers
 *     « À améliorer », et n'offre-t-il jamais de retirer une version ? L'origine « Déploiement » est-elle offerte ?
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ORIGINES } from "@/components/mark/ameliorer/libelles";

import { BandeauDAlertes } from "./BandeauDAlertes";
import { ORIGINES_DE_TRI } from "./libelles";
import { PlanifierLaSuite } from "./PlanifierLaSuite";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/agents/42/tests" }));

const m = vi.hoisted(() => ({ rejeu: vi.fn(), alertes: vi.fn(), regler: vi.fn(), reglerAlertes: vi.fn(), evaluer: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    lireLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdGet: (o: unknown) => m.rejeu(o),
    lireLesAlertesApiV1BuilderAlertesWorkflowIdGet: (o: unknown) => m.alertes(o),
    reglerLeRejeuPlanifieApiV1BuilderPlanificationWorkflowIdPut: (o: unknown) => m.regler(o),
    reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut: (o: unknown) => m.reglerAlertes(o),
    evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost: (o: unknown) => m.evaluer(o),
}));

const REJEU = {
    actif: false,
    frequence: "quotidien",
    jour: 0,
    heure: 3,
    repetitions: 1,
    quoi: "toute_la_suite",
    prevenir: "tous",
    derniere: null,
    historique: [
        { periode: "2026-11-03", statut: "joue", ok: false, reussis: 11, total: 12, version: 7 },
        { periode: "2026-11-02", statut: "joue", ok: true, reussis: 12, total: 12, version: 6 },
        { periode: "2026-11-01", statut: "interrompu" },
    ],
};
const ALERTES = {
    mail: false,
    types: { version_moins_bien: { actif: true, seuils: { baisse_note: 0.5, hausse_impasses: 0.05, appels_min: 10, jours: 14 } } },
    levees: [{ id: "version_moins_bien:42:v7", type: "version_moins_bien", version: 7, contre: 6, resume: "Version 7 contre version 6 : note du juge 4.4 → 3.7 sur 5." }],
};

beforeEach(() => {
    m.rejeu.mockResolvedValue({ data: REJEU });
    m.alertes.mockResolvedValue({ data: ALERTES });
    m.regler.mockImplementation(async ({ body }: { body: object }) => ({ data: { ...REJEU, ...body } }));
    m.reglerAlertes.mockResolvedValue({ data: ALERTES });
    m.evaluer.mockResolvedValue({ data: { alertes: [], eteints: [], ...ALERTES } });
});
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

describe("la fenêtre « Planifier la suite »", () => {
    const ouvrir = async () => {
        render(<PlanifierLaSuite agentId={42} fermer={vi.fn()} />);
        return await screen.findByText("Scheduled replay");
    };

    it("est éteinte par défaut, cache ses réglages tant qu'elle l'est, et dit les dernières exécutions dont la régression", async () => {
        await ouvrir();
        expect((screen.getByRole("switch", { name: "Schedule on" }) as HTMLElement).getAttribute("aria-checked")).toBe("false");
        expect(screen.queryByText("Tries per test")).toBeNull();
        const histoire = within(screen.getByTestId("historique-planifie"));
        expect(histoire.getByText(/11\/12 · regression/)).toBeTruthy();
        expect(histoire.getByText("12/12")).toBeTruthy();
        expect(histoire.getByText(/stopped/)).toBeTruthy();
        expect(screen.getByTestId("alertes-levees").textContent).toContain("note du juge 4.4 → 3.7");
    });

    it("enregistre le rejeu et l'alerte aux deux routes, avec ce qui a été réglé", async () => {
        await ouvrir();
        fireEvent.click(screen.getByRole("switch", { name: "Schedule on" }));
        fireEvent.click(screen.getByRole("button", { name: "Every week" }));
        fireEvent.change(screen.getByLabelText("Hour (Paris time)"), { target: { value: "5" } });
        fireEvent.change(screen.getByLabelText("Score drop"), { target: { value: "1" } });
        fireEvent.change(screen.getByLabelText("Dead ends up by"), { target: { value: "8" } });
        fireEvent.click(screen.getByRole("switch", { name: "Tell by e-mail" }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][0]).toEqual({ path: { workflow_id: 42 }, body: { actif: true, frequence: "hebdomadaire", jour: 0, heure: 5, repetitions: 1, quoi: "toute_la_suite", prevenir: "tous" } });
        expect(m.reglerAlertes.mock.calls[0][0]).toEqual({
            path: { workflow_id: 42 },
            body: { mail: true, types: { version_moins_bien: { actif: true, seuils: { baisse_note: 1, hausse_impasses: 0.08, appels_min: 10, jours: 14 } } } },
        });
    });

    it("clôture, D19 : « Ce qui est rejoué » et « Prévenir » se choisissent, par défaut ce que le rejeu faisait, et partent à l'enregistrement", async () => {
        await ouvrir();
        fireEvent.click(screen.getByRole("switch", { name: "Schedule on" }));
        const quoi = screen.getByText("What is replayed").closest("[data-ligne], div")!.parentElement!;
        expect(within(quoi).getByRole("button", { name: "The whole suite", pressed: true })).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Required tests" }));
        fireEvent.click(screen.getByRole("button", { name: "Suite and attacks" }));
        fireEvent.click(screen.getByRole("combobox", { name: /Tell$/ }));
        fireEvent.click(screen.getByRole("option", { name: "Nobody" }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect(m.regler.mock.calls[0][0].body).toMatchObject({ quoi: "suite_et_attaques", prevenir: "personne" });
    });

    it("« Vérifier maintenant » est refusé tant qu'une saisie n'est pas enregistrée, puis évalue et le dit", async () => {
        await ouvrir();
        const bouton = screen.getByRole("button", { name: "Check now" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(false);
        fireEvent.click(screen.getByRole("switch", { name: "Schedule on" }));
        expect(bouton.disabled).toBe(true);
        expect(screen.getByText("Save first.")).toBeTruthy();
        fireEvent.click(screen.getByRole("switch", { name: "Schedule on" }));
        expect(bouton.disabled).toBe(false);
        fireEvent.click(bouton);
        await waitFor(() => expect(m.evaluer).toHaveBeenCalledWith({ path: { workflow_id: 42 } }));
        expect(m.regler).not.toHaveBeenCalled(); // vérifier ne règle rien
    });

    it("un enregistrement refusé le dit sans fermer la fenêtre ni perdre la saisie", async () => {
        m.regler.mockResolvedValue({ error: { detail: "Unknown frequency" } });
        await ouvrir();
        fireEvent.click(screen.getByRole("switch", { name: "Schedule on" }));
        fireEvent.click(screen.getByRole("button", { name: "Save" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalled());
        expect((screen.getByRole("switch", { name: "Schedule on" }) as HTMLElement).getAttribute("aria-checked")).toBe("true");
    });
});

describe("le bandeau d'alerte et l'origine Déploiement", () => {
    it("montre la dernière alerte, pointe vers À améliorer et n'offre jamais de retirer une version", async () => {
        render(<BandeauDAlertes agentId={42} />);
        const bandeau = await screen.findByTestId("bandeau-d-alerte");
        expect(bandeau.textContent).toContain("Version 7 does worse than version 6");
        expect(bandeau.textContent).toContain("Nothing was changed");
        expect(within(bandeau).getByRole("link", { name: "Open To improve" }).getAttribute("href")).toBe("/labo/a-ameliorer");
        expect(within(bandeau).queryAllByRole("button")).toHaveLength(0);
    });

    it("ne montre rien sans alerte ou quand la lecture échoue", async () => {
        m.alertes.mockResolvedValue({ data: { ...ALERTES, levees: [] } });
        const { container, rerender } = render(<BandeauDAlertes agentId={42} />);
        await waitFor(() => expect(m.alertes).toHaveBeenCalled());
        expect(container.innerHTML).toBe("");
        m.alertes.mockResolvedValue({ error: { detail: "x" } });
        rerender(<BandeauDAlertes agentId={43} />);
        await waitFor(() => expect(m.alertes).toHaveBeenCalledTimes(2));
        expect(container.innerHTML).toBe("");
    });

    it("l'origine Déploiement est offerte dans « À améliorer » et dans l'ancien « À trier »", () => {
        expect(ORIGINES.deploiement.fr).toContain("déploiement");
        expect(ORIGINES_DE_TRI.deploiement.libelle.fr).toBe("Déploiement");
        expect(ORIGINES_DE_TRI.deploiement.suite.fr).toContain("rien n'est retiré automatiquement");
    });
});
