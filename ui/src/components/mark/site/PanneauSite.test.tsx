/**
 * [.mark] U10 / S2 : l'écran « Intégrer » d'un agent de site, branché sur `/organizations/agents-site/*`.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | agent téléphonique | seul le canal est proposé : ni site, ni apparence, ni réglages |
 * | agent de site | le site, ses chemins, le script du SITE, l'apparence et les réglages .mark viennent du serveur |
 * | aperçu | l'accroche et la couleur choisies se voient dans l'aperçu |
 * | canal | basculer le canal appelle la route du canal |
 * | revenir au bleu | envoie une apparence vide (le défaut du serveur) |
 * | refus | une erreur du serveur s'affiche en clair, rien ne casse |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContexteBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({
    emplacement: vi.fn(),
    sites: vi.fn(),
    apparence: vi.fn(),
    reglages: vi.fn(),
    canal: vi.fn(),
    regler: vi.fn(),
    toastErreur: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet: sdk.emplacement,
    listerLesSitesApiV1OrganizationsSitesGet: sdk.sites,
    lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet: sdk.apparence,
    lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet: sdk.reglages,
    reglerLeCanalApiV1OrganizationsAgentsSiteWorkflowIdCanalPut: sdk.canal,
    reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut: sdk.regler,
    creerUnSiteApiV1OrganizationsSitesPost: vi.fn(),
    poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut: vi.fn(),
    reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut: vi.fn(),
    lireLaCouleurDuSiteApiV1OrganizationsAgentsSiteWorkflowIdLireSitePost: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("sonner", () => ({ toast: { error: sdk.toastErreur, success: vi.fn() } }));

import { PanneauSite } from "./PanneauSite";
import { lireNotifications, viderNotifications } from "@/components/mark/notifications";

const SITE = { id: 3, cle: "site_abc", nom: "Client", allowed_domains: ["client.fr"], dernier_chargement: null, script: '<script async src="https://x/embed/dograh-widget.js?site=site_abc"></script>' };
const APPARENCE = {
    apparence: { couleur_base: "#aa2200", textes: { accroche: "Bonjour\nà vous" } },
    couleurs: {},
};
const REGLAGES = {
    plafond_conversations_mois: 500,
    plafond_minutes_mois: 1500,
    duree_max_s: 600,
    sessions_par_heure_et_ip: 10,
    allowed_domains: ["client.fr"],
    conversations_ce_mois: 4,
    minutes_ce_mois: 12,
};

// K7 : le panneau déclare sa saisie non enregistrée à la page de l'agent (dernière déclaration par identifiant).
const declarations = vi.hoisted(() => ({ etat: [] as boolean[] }));

function rendre() {
    return render(
        <ContexteBrouillonLocal.Provider value={(_id, sale) => void declarations.etat.push(sale)}>
            <FournisseurLangue>
                <PanneauSite workflowId={42} />
            </FournisseurLangue>
        </ContexteBrouillonLocal.Provider>,
    );
}

beforeEach(() => {

  viderNotifications();
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.sites.mockResolvedValue({ data: [SITE] });
    sdk.canal.mockResolvedValue({ data: {} });
    sdk.regler.mockResolvedValue({ data: {} });
    declarations.etat = [];
});
afterEach(cleanup);

describe("PanneauSite", () => {
    it("un agent téléphonique ne montre que le canal", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        rendre();
        await screen.findByTestId("panneau-site");
        expect(screen.queryByTestId("reglages-mark")).toBeNull();
        expect(screen.queryByTestId("apercu-widget")).toBeNull();
        expect(sdk.apparence).not.toHaveBeenCalled();
    });

    it("un agent de site montre le site, le script, l'apparence et les réglages .mark réels", async () => {
        sdk.emplacement.mockResolvedValue({
            data: { workflow_id: 42, canal: "site", embed_token_id: 9, widget_actif: true, site_id: 3, site_cle: "site_abc", chemins: ["/tarifs", "/aide"] },
        });
        sdk.apparence.mockResolvedValue({ data: APPARENCE });
        sdk.reglages.mockResolvedValue({ data: REGLAGES });
        rendre();
        await screen.findByTestId("reglages-mark");
        expect(screen.getByText(/dograh-widget\.js\?site=site_abc/)).toBeTruthy();
        expect((screen.getByDisplayValue(/\/tarifs/) as HTMLTextAreaElement).value).toBe("/tarifs\n/aide");
        expect(screen.getByDisplayValue("500")).toBeTruthy();
        expect(screen.getByDisplayValue("600")).toBeTruthy();
        expect(screen.getByText(/4 conversations, 12 min ce mois-ci/)).toBeTruthy();
        const apercu = screen.getByTestId("apercu-widget");
        expect(apercu.textContent).toContain("Bonjour");
        expect(apercu.textContent).toContain("à vous");
    });

    it("basculer le canal appelle la route du canal", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        rendre();
        fireEvent.click(await screen.findByRole("switch"));
        await waitFor(() => expect(sdk.canal).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { canal: "site" } }));
    });

    it("« Revenir au bleu .mark » envoie une apparence vide", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "site", embed_token_id: 9, site_id: 3, chemins: ["/"] } });
        sdk.apparence.mockResolvedValue({ data: APPARENCE });
        sdk.reglages.mockResolvedValue({ data: REGLAGES });
        rendre();
        fireEvent.click(await screen.findByText("Revenir au bleu .mark"));
        await waitFor(() => expect(sdk.regler).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: {} }));
    });

    it("une erreur du serveur s'affiche en clair", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "telephone", chemins: [] } });
        sdk.canal.mockResolvedValue({ error: { detail: "This agent still answers a phone number." } });
        rendre();
        fireEvent.click(await screen.findByRole("switch"));
        await waitFor(() => expect(lireNotifications().map((n) => n.detail)).toContain("This agent still answers a phone number."));
    });
});

describe("PanneauSite : saisie gardée (K7)", () => {
    const site = () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "site", embed_token_id: 9, site_id: 3, site_cle: "site_abc", chemins: ["/tarifs"] } });
        sdk.apparence.mockResolvedValue({ data: APPARENCE });
        sdk.reglages.mockResolvedValue({ data: REGLAGES });
    };

    it("ne déclare rien tant que rien n'est saisi, puis déclare la saisie des chemins", async () => {
        site();
        rendre();
        const chemins = (await screen.findByDisplayValue(/\/tarifs/)) as HTMLTextAreaElement;
        expect(declarations.etat.at(-1)).toBe(false);
        fireEvent.change(chemins, { target: { value: "/tarifs\n/nouveau" } });
        await waitFor(() => expect(declarations.etat.at(-1)).toBe(true));
        fireEvent.change(chemins, { target: { value: "/tarifs" } });
        await waitFor(() => expect(declarations.etat.at(-1)).toBe(false));
    });

    it("déclare aussi un plafond ou les domaines modifiés dans les réglages .mark", async () => {
        site();
        rendre();
        const plafond = await screen.findByDisplayValue("500");
        fireEvent.change(plafond, { target: { value: "800" } });
        await waitFor(() => expect(declarations.etat).toContain(true));
    });
});
