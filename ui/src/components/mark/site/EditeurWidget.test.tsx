/**
 * [.mark] V5 : l'éditeur du widget du site (maquette `editeur-widget.tsx`), branché sur les routes réelles.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | chargement | le nom de l'agent, les quatre onglets, les réglages .mark lus du serveur ; l'aperçu reçoit l'apparence réelle |
 * | texte | changer l'accroche dans la bulle d'un élément, puis Enregistrer : la route de l'apparence reçoit ce texte |
 * | couleur | une couleur d'un élément est écrite dans SA retouche, aucune autre ne bouge |
 * | fautes | un texte hors bornes se lit sous le champ et bloque l'enregistrement (aucune écriture) |
 * | réglages .mark | plafond, durée, modes : la route des réglages ; l'expiration n'est envoyée que si elle change |
 * | affichage | l'interrupteur écrit « affiché / coupé » |
 * | quitter | Annuler avec une modification demande confirmation ; sans modification, ferme direct |
 * | pose | sans widget encore : l'onglet « Pose » s'ouvre, « Poser l'agent » écrit l'emplacement |
 * | clé | régénérer demande confirmation puis appelle la route |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContexteBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({
    emplacement: vi.fn(),
    sites: vi.fn(),
    apparence: vi.fn(),
    reglages: vi.fn(),
    reglerApparence: vi.fn(),
    reglerReglages: vi.fn(),
    affichage: vi.fn(),
    emplacementPut: vi.fn(),
    regenerer: vi.fn(),
    apercu: vi.fn(),
}));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        lireLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdGet: sdk.emplacement,
        listerLesSitesApiV1OrganizationsSitesGet: sdk.sites,
        lireLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparenceGet: sdk.apparence,
        lireLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesGet: sdk.reglages,
        reglerLApparenceApiV1OrganizationsAgentsSiteWorkflowIdApparencePut: sdk.reglerApparence,
        reglerLesReglagesApiV1OrganizationsAgentsSiteWorkflowIdReglagesPut: sdk.reglerReglages,
        reglerLAffichageApiV1OrganizationsAgentsSiteWorkflowIdAffichagePut: sdk.affichage,
        poserLEmplacementApiV1OrganizationsAgentsSiteWorkflowIdEmplacementPut: sdk.emplacementPut,
        regenererLaCleDuSiteApiV1OrganizationsSitesSiteIdRegenererClePost: sdk.regenerer,
    }),
);
const utilisateur = vi.hoisted(() => ({ email: "a@b.c" }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: utilisateur }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));
// L'aperçu monte le vrai widget (testé dans `dograh-widget-site.test.ts`, repères compris, et capturé) : ici une doublure
// qui note ce qu'il reçoit et laisse « cliquer » un élément.
vi.mock("./ApercuWidget", () => ({
    ApercuWidget: (p: { apparence: unknown; modes: string; etat: string; zone: string | null; onChoisir: (z: string | null) => void; contenu: React.ReactNode }) => {
        sdk.apercu(p);
        return (
            <div data-testid="apercu-widget" data-etat={p.etat} data-modes={p.modes}>
                {["accroche", "demarrer", "avisPasser"].map((z) => (
                    <button key={z} onClick={() => p.onChoisir(z)}>{`zone-${z}`}</button>
                ))}
                <div data-testid="bulle">{p.contenu}</div>
            </div>
        );
    },
}));

import { lireNotifications, viderNotifications } from "@/components/mark/notifications";

import { EditeurWidget } from "./EditeurWidget";

const EMPLACEMENT = { workflow_id: 42, canal: "site", embed_token_id: 9, widget_actif: true, site_id: 3, site_cle: "site_abc", chemins: ["/"], agent_nom: "Assistant du site", version_publiee: 2, dernier_chargement: null };
const SITE = { id: 3, cle: "site_abc", nom: "Client", allowed_domains: ["client.fr"], dernier_chargement: null, script: '<script async src="https://x/embed/dograh-widget.js?site=site_abc"></script>' };
const APPARENCE = {
    apparence: {
        couleur_base: "#1b5fb0", fond_fenetre: "#ffffff", texte_fenetre: "#0f1c2e", couleurs: {}, police: "switzer", embleme: "orbe", logo_url: null, orbe_animee: true,
        position: "bas-droite", fenetre: "ancree", declenchement: "delai", delai_s: 4, lien_confidentialite: null, avis: true,
        textes: { accroche: "Une question ?\nParlez-moi.", titre: "Assistant", avis_passer: "Passer", merci: "Merci", bouton_demarrer: "Parler" },
    },
    couleurs: {},
};
const REGLAGES = { plafond_conversations_mois: 500, plafond_minutes_mois: 1500, duree_max_s: 600, sessions_par_heure_et_ip: 10, allowed_domains: ["client.fr"], conversations_ce_mois: 4, minutes_ce_mois: 12, modes: "voix_et_ecrit", jeton_expire_le: null };

const fermer = vi.fn();
const declarations = vi.hoisted(() => ({ etat: [] as boolean[] }));
function rendre() {
    return render(
        <ContexteBrouillonLocal.Provider value={(_id, sale) => void declarations.etat.push(sale)}>
            <FournisseurLangue>
                <EditeurWidget workflowId={42} onFermer={fermer} />
            </FournisseurLangue>
        </ContexteBrouillonLocal.Provider>,
    );
}
const widgetPose = () => {
    sdk.emplacement.mockResolvedValue({ data: EMPLACEMENT });
    sdk.sites.mockResolvedValue({ data: [SITE] });
    sdk.apparence.mockResolvedValue({ data: APPARENCE });
    sdk.reglages.mockResolvedValue({ data: REGLAGES });
};
const onglet = (nom: RegExp) => fireEvent.mouseDown(screen.getByRole("tab", { name: nom }));
const enregistrer = () => screen.getByRole("button", { name: "Enregistrer" }) as HTMLButtonElement;

beforeEach(() => {
    viderNotifications();
    fermer.mockReset();
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.reglerApparence.mockResolvedValue({ data: {} });
    sdk.reglerReglages.mockResolvedValue({ data: {} });
    sdk.affichage.mockResolvedValue({ data: {} });
    sdk.emplacementPut.mockResolvedValue({ data: {} });
    sdk.regenerer.mockResolvedValue({ data: {} });
    declarations.etat = [];
});
afterEach(cleanup);

describe("EditeurWidget : chargement", () => {
    it("montre l'agent, les quatre onglets et passe l'apparence réelle à l'aperçu", async () => {
        widgetPose();
        rendre();
        expect(await screen.findByText("Assistant du site")).toBeTruthy();
        for (const nom of [/Apparence/, /Comportement/, /Pose sur le site/, /Réglages \.mark/]) expect(screen.getByRole("tab", { name: nom })).toBeTruthy();
        const dernier = sdk.apercu.mock.calls.at(-1)![0];
        expect(dernier.apparence.textes.accroche).toBe("Une question ?\nParlez-moi.");
        expect(dernier.modes).toBe("voix_et_ecrit");
        expect(enregistrer().disabled).toBe(true);
    });

    it("S-2 : l'en-tête nomme la fiche d'établissement de l'agent, ou dit « sans lieu »", async () => {
        widgetPose();
        sdk.emplacement.mockResolvedValue({ data: { ...EMPLACEMENT, etablissement_nom: "Agence Nord" } });
        rendre();
        expect((await screen.findAllByText(/· Agence Nord/)).length).toBeGreaterThan(0);
        cleanup();
        sdk.emplacement.mockResolvedValue({ data: { ...EMPLACEMENT, etablissement_nom: null } });
        rendre();
        expect((await screen.findAllByText(/· sans lieu/)).length).toBeGreaterThan(0);
    });

    it("les réglages .mark viennent du serveur", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Réglages \.mark/);
        expect(((await screen.findByLabelText("Plafond du mois (conversations)")) as HTMLInputElement).value).toBe("500");
        expect((screen.getByLabelText("Durée maximale d'une conversation (s)") as HTMLInputElement).value).toBe("600");
        expect((screen.getByLabelText("Domaines autorisés") as HTMLInputElement).value).toBe("client.fr");
        expect((screen.getByLabelText("Agent branché") as HTMLInputElement).value).toBe("Assistant du site (v2)");
        expect(screen.getByText(/Ce mois-ci : 4 \(1 %\)/)).toBeTruthy();
    });

    it("une lecture qui échoue se dit, sans casser", async () => {
        sdk.emplacement.mockResolvedValue({ data: undefined });
        sdk.sites.mockResolvedValue({ data: [] });
        rendre();
        await waitFor(() => expect(document.querySelector("[data-testid=editeur-widget]")).not.toBeNull());
        expect(screen.queryByText("Assistant du site")).toBeNull();
    });
});

describe("EditeurWidget : écrire l'apparence", () => {
    it("le texte de l'accroche, choisi dans l'aperçu, part à la route de l'apparence", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-accroche"));
        const champ = within(screen.getByTestId("bulle")).getByLabelText("Texte") as HTMLTextAreaElement;
        fireEvent.change(champ, { target: { value: "Bonjour\nà vous" } });
        expect(enregistrer().disabled).toBe(false);
        fireEvent.click(enregistrer());
        await waitFor(() => expect(sdk.reglerApparence).toHaveBeenCalled());
        const envoi = sdk.reglerApparence.mock.calls[0][0];
        expect(envoi.path).toEqual({ workflow_id: 42 });
        expect(envoi.body.textes.accroche).toBe("Bonjour\nà vous");
        expect(envoi.body.textes.titre).toBe("Assistant");
        expect(sdk.reglerReglages).not.toHaveBeenCalled();
        await waitFor(() => expect(fermer).toHaveBeenCalled());
        expect(lireNotifications().map((n) => n.sorte)).toContain("succes");
    });

    it("une couleur est écrite dans la retouche de son élément, aucune autre ne bouge", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-demarrer"));
        const hex = within(screen.getByTestId("bulle")).getByLabelText("Fond (hex)") as HTMLInputElement;
        fireEvent.change(hex, { target: { value: "#aa2200" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(sdk.reglerApparence).toHaveBeenCalled());
        expect(sdk.reglerApparence.mock.calls[0][0].body.couleurs).toEqual({ boutons: "#aa2200" });
        expect(sdk.reglerApparence.mock.calls[0][0].body.couleur_base).toBe("#1b5fb0");
    });

    it("un texte hors bornes se lit sous le champ et bloque l'enregistrement", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-accroche"));
        fireEvent.change(within(screen.getByTestId("bulle")).getByLabelText("Texte"), { target: { value: "a\nb\nc\nd" } });
        expect(within(screen.getByTestId("bulle")).getByRole("alert").textContent).toBe("3 lignes au plus.");
        expect(enregistrer().disabled).toBe(true);
        fireEvent.change(within(screen.getByTestId("bulle")).getByLabelText("Texte"), { target: { value: "" } });
        expect(within(screen.getByTestId("bulle")).getByRole("alert").textContent).toBe("Ce texte ne peut pas être vide.");
        expect(sdk.reglerApparence).not.toHaveBeenCalled();
    });

    it("une couleur mal écrite se lit sous le champ et n'est pas envoyée", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-demarrer"));
        fireEvent.change(within(screen.getByTestId("bulle")).getByLabelText("Fond (hex)"), { target: { value: "bleu" } });
        expect(within(screen.getByTestId("bulle")).getByText("Une couleur s'écrit #rgb ou #rrggbb.")).toBeTruthy();
        expect(enregistrer().disabled).toBe(true);
    });

    it("une erreur du serveur se dit par une notification, la fenêtre reste ouverte", async () => {
        widgetPose();
        sdk.reglerApparence.mockResolvedValue({ error: { detail: "a text cannot be empty" } });
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-accroche"));
        fireEvent.change(within(screen.getByTestId("bulle")).getByLabelText("Texte"), { target: { value: "Salut" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(lireNotifications().map((n) => n.sorte)).toContain("echec"));
        expect(fermer).not.toHaveBeenCalled();
    });
});

describe("EditeurWidget : réglages .mark et affichage", () => {
    it("le plafond part à la route des réglages ; l'expiration n'est envoyée que si elle change", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Réglages \.mark/);
        fireEvent.change(await screen.findByLabelText("Plafond du mois (conversations)"), { target: { value: "800" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(sdk.reglerReglages).toHaveBeenCalled());
        const corps = sdk.reglerReglages.mock.calls[0][0].body;
        expect(corps).toMatchObject({ plafond_conversations_mois: 800, plafond_minutes_mois: 1500, duree_max_s: 600, sessions_par_heure_et_ip: 10, modes: "voix_et_ecrit", allowed_domains: ["client.fr"] });
        expect(corps).not.toHaveProperty("jeton_expire_le");
        expect(sdk.reglerApparence).not.toHaveBeenCalled();
    });

    it("une date d'expiration est envoyée quand on la change", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Réglages \.mark/);
        fireEvent.change(await screen.findByLabelText(/Expiration du jeton/), { target: { value: "2027-01-31" } });
        fireEvent.click(enregistrer());
        await waitFor(() => expect(sdk.reglerReglages).toHaveBeenCalled());
        expect(sdk.reglerReglages.mock.calls[0][0].body.jeton_expire_le).toBe("2027-01-31");
    });

    it("un plafond hors bornes se lit sous le champ et bloque l'enregistrement", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Réglages \.mark/);
        fireEvent.change(await screen.findByLabelText("Durée maximale d'une conversation (s)"), { target: { value: "5" } });
        expect(screen.getByText("Entre 60 et 3600.")).toBeTruthy();
        expect(enregistrer().disabled).toBe(true);
    });

    it("l'interrupteur écrit « affiché / coupé »", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByRole("switch", { name: "Affiché sur le site" }));
        expect(screen.getByText("Coupé sur le site")).toBeTruthy();
        fireEvent.click(enregistrer());
        await waitFor(() => expect(sdk.affichage).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { actif: false } }));
        expect(sdk.reglerApparence).not.toHaveBeenCalled();
    });
});

describe("EditeurWidget : quitter", () => {
    it("sans modification, Annuler ferme tout de suite", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        expect(fermer).toHaveBeenCalled();
    });

    it("avec une modification, Annuler prévient ; « Continuer » garde la saisie, « Quitter » ferme", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        fireEvent.click(screen.getByText("zone-accroche"));
        fireEvent.change(within(screen.getByTestId("bulle")).getByLabelText("Texte"), { target: { value: "Salut" } });
        await waitFor(() => expect(declarations.etat.at(-1)).toBe(true));
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        expect(await screen.findByText("Quitter sans enregistrer ?")).toBeTruthy();
        expect(fermer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Continuer à modifier" }));
        expect(fermer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        fireEvent.click(await screen.findByRole("button", { name: "Quitter sans enregistrer" }));
        expect(fermer).toHaveBeenCalled();
        expect(sdk.reglerApparence).not.toHaveBeenCalled();
    });
});

describe("EditeurWidget : pose sur le site", () => {
    it("sans widget encore, ouvre « Pose » ; « Poser l'agent » écrit l'emplacement", async () => {
        sdk.emplacement.mockResolvedValue({ data: { workflow_id: 42, canal: "site", chemins: [], agent_nom: "Assistant du site" } });
        sdk.sites.mockResolvedValue({ data: [SITE] });
        rendre();
        await screen.findByTestId("emplacement");
        expect(screen.queryByTestId("script-du-site")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Client" }));
        fireEvent.change(screen.getByLabelText(/Pages servies/), { target: { value: "/tarifs\n/aide" } });
        fireEvent.click(screen.getByRole("button", { name: "Poser l'agent" }));
        await waitFor(() => expect(sdk.emplacementPut).toHaveBeenCalledWith({ path: { workflow_id: 42 }, body: { site_id: 3, chemins: ["/tarifs", "/aide"] } }));
    });

    it("le script du SITE est montré, avec l'état de détection", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Pose sur le site/);
        expect((await screen.findByTestId("script-du-site")).textContent).toContain("dograh-widget.js?site=site_abc");
        expect(screen.getByTestId("script-detecte").textContent).toContain("pas encore vu");
    });

    it("régénérer le jeton demande confirmation puis appelle la route du site", async () => {
        widgetPose();
        rendre();
        await screen.findByText("Assistant du site");
        onglet(/Réglages \.mark/);
        fireEvent.click(await screen.findByRole("button", { name: "Régénérer le jeton" }));
        expect(await screen.findByText("Régénérer le jeton du site ?")).toBeTruthy();
        expect(sdk.regenerer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Régénérer" }));
        await waitFor(() => expect(sdk.regenerer).toHaveBeenCalledWith({ path: { site_id: 3 } }));
    });
});
