/**
 * [.mark] L3e sous-lot 1 : la page des alertes sur les vrais appels (onglet Alertes de Qualité).
 * Question : une alerte levée se lit-elle avec son titre et son résumé, « Voir les appels » ouvre-t-il les appels concernés, et un seuil
 * enregistré part-il pour LE signal choisi seulement ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({
    qualite: vi.fn(),
    lire: vi.fn(),
    regler: vi.fn(),
    evaluer: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    lireLaQualiteApiV1QualiteGet: (...a: unknown[]) => sdk.qualite(...a),
    lireLesAlertesApiV1BuilderAlertesWorkflowIdGet: (...a: unknown[]) => sdk.lire(...a),
    reglerLesAlertesApiV1BuilderAlertesWorkflowIdPut: (...a: unknown[]) => sdk.regler(...a),
    evaluerLesAlertesApiV1BuilderAlertesWorkflowIdEvaluerPost: (...a: unknown[]) => sdk.evaluer(...a),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }), usePathname: () => "/labo/qualite" }));

import { AlertesDesAppels, SIGNAUX_DES_APPELS } from "./AlertesDesAppels";

const seuils = { hausse: 50, appels_min: 10, jours: 7, cas_min: 3 };
const bornes = { hausse: { defaut: 50, bas: 1, haut: 1000 }, appels_min: { defaut: 10, bas: 1, haut: 1000 }, jours: { defaut: 7, bas: 1, haut: 30 }, cas_min: { defaut: 3, bas: 1, haut: 1000 } };
const vue = () => ({
    mail: false,
    types: Object.fromEntries(SIGNAUX_DES_APPELS.map((c) => [c, { actif: true, seuils }])),
    catalogue: Object.fromEntries(SIGNAUX_DES_APPELS.map((c) => [c, { titre: { fr: `Titre ${c}`, en: `Title ${c}` }, explication: { fr: "expl", en: "expl" }, seuils: bornes }])),
    levees: [
        { id: "hausse_transferts:4:p1", type: "hausse_transferts", resume: "appels transférés 0 % → 40 % sur 7 jours (4 appel(s) concerné(s)).", appels: [301, 302], appels_concernes: 4, periode_jours: 7 },
        { id: "version_moins_bien:4:v3", type: "version_moins_bien", resume: "autre type", version: 3, contre: 2 },
    ],
});

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

function monter(langue: "fr" | "en" = "fr") {
    sdk.qualite.mockResolvedValue({ data: { agents: [{ workflow_id: 4, workflow_nom: "Accueil" }] }, error: undefined });
    sdk.lire.mockResolvedValue({ data: vue(), error: undefined });
    window.localStorage.setItem("mark.langue", langue);
    return render(
        <FournisseurLangue>
            <AlertesDesAppels />
        </FournisseurLangue>,
    );
}

describe("la colonne « Maintenant » (É63, clôture D2)", () => {
    it("dit la hausse de chaque signal à cet instant, un tiret quand elle n'est pas mesurable", async () => {
        sdk.qualite.mockResolvedValue({ data: { agents: [{ workflow_id: 4, workflow_nom: "Accueil" }] }, error: undefined });
        sdk.lire.mockResolvedValue({
            data: { ...vue(), maintenant: { hausse_rates: { hausse: 12.5, appels: 30 }, hausse_transferts: { hausse: -4, appels: 30 }, hausse_pannes: { hausse: null, appels: 3 } } },
            error: undefined,
        });
        window.localStorage.setItem("mark.langue", "fr");
        render(
            <FournisseurLangue>
                <AlertesDesAppels />
            </FournisseurLangue>,
        );
        await screen.findByText("Maintenant");
        const lire = (code: string) => document.querySelector(`[data-maintenant="${code}"]`)!.textContent;
        expect(lire("hausse_rates")).toBe("+12,5 %");
        expect(lire("hausse_transferts")).toBe("-4 %");
        expect(lire("hausse_pannes")).toBe("–");
        expect(lire("hausse_latence")).toBe("–");
    });
});

describe("Alertes sur les vrais appels", () => {
    it("montre l'alerte levée (pas celle d'une version), ouvre les appels concernés avec un lien par appel", async () => {
        monter();
        expect(await screen.findByTestId("alertes-declenchees")).toBeTruthy();
        expect(screen.getByText(/0 % → 40 %/)).toBeTruthy();
        expect(screen.queryByText("autre type")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Voir les appels" }));
        const liens = screen.getByTestId("appels-concernes").querySelectorAll("a");
        expect([...liens].map((a) => a.getAttribute("href"))).toEqual(["/workflow/4/run/301", "/workflow/4/run/302"]);
        expect(screen.getByText("2 de plus")).toBeTruthy();
    });

    it("liste les cinq signaux en seuils et enregistre le seuil du signal choisi", async () => {
        monter();
        fireEvent.click(await screen.findByText("Titre hausse_pannes"));
        sdk.regler.mockResolvedValue({ data: vue(), error: undefined });
        const champ = await screen.findByLabelText("Seuil de hausse (%)");
        fireEvent.change(champ, { target: { value: "80" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(sdk.regler).toHaveBeenCalled());
        const appel = sdk.regler.mock.calls[0][0];
        expect(appel.path).toEqual({ workflow_id: 4 });
        expect(Object.keys(appel.body.types)).toEqual(["hausse_pannes"]);
        expect(appel.body.types.hausse_pannes.seuils.hausse).toBe(80);
    });

    it("refuse une valeur hors bornes sous le champ", async () => {
        monter();
        fireEvent.click(await screen.findByText("Titre hausse_latence"));
        fireEvent.change(await screen.findByLabelText("Période (jours)"), { target: { value: "99" } });
        expect(screen.getByText("Entre 1 et 30.")).toBeTruthy();
        expect((screen.getByRole("button", { name: "Enregistrer" }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("anglais : « See the calls »", async () => {
        monter("en");
        expect(await screen.findByRole("button", { name: "See the calls" })).toBeTruthy();
    });
});
