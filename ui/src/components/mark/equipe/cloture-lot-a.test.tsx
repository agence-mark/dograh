/**
 * [.mark] Clôture, lot A (D21 à D24) : l'écran.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | accès actif | l'interrupteur d'un membre appelle le serveur, dit son résultat par une notification, un échec reste dit ; un membre bloqué se lit « Bloqué » |
 * | journal | les filtres « Type de geste » et « Porte » partent au serveur ; la colonne « Porte » dit écran, API ou MCP ; les gestes nouveaux sont dits en clair |
 * | durée | la durée du journal est bornée par le serveur (hors bornes : message sous le champ, pas d'envoi) |
 * | clé | le panneau de droits d'une clé : rôle, suspension et trois interrupteurs MCP éteints par défaut, désactivés sans rôle |
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({
    journal: vi.fn(),
    types: vi.fn(),
    reglages: vi.fn(),
    acces: vi.fn(),
    duree: vi.fn(),
    interrupteurs: vi.fn(),
    role: vi.fn(),
    suspendre: vi.fn(),
    membres: vi.fn(),
    succes: vi.fn(),
    echec: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    listerLesMembresApiV1EquipeMarkMembresGet: m.membres,
    listerLesInvitationsApiV1EquipeMarkInvitationsGet: vi.fn(async () => ({ data: { invitations: [], total: 0, limit: 25, offset: 0 } })),
    listerLesRolesApiV1EquipeMarkRolesGet: vi.fn(async () => ({ data: [{ id: 3, nom: "Éditeur", permissions: [], organisations: [], membres: 0, fixe: false, labo_ouvert: true, tous_les_clients: true }] })),
    annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete: vi.fn(),
    changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut: vi.fn(),
    inviterApiV1EquipeMarkInvitationsPost: vi.fn(),
    retirerUnMembreApiV1EquipeMarkMembresUserIdDelete: vi.fn(),
}));
vi.mock("./api-cloture", () => ({
    lireLeJournalFiltre: m.journal,
    typesDeGestes: m.types,
    lireLesReglagesDeLEquipe: m.reglages,
    changerLAcces: m.acces,
    reglerLaDureeDuJournal: m.duree,
    reglerLeMessageBloque: vi.fn(),
    changerLesInterrupteursMcp: m.interrupteurs,
    changerLeRoleDeLaCle: m.role,
    suspendreLaCle: m.suspendre,
}));
vi.mock("@/lib/espaces", () => ({ listerEspaces: vi.fn(async () => [{ id: 7, nom: "Nuances de Feu", provider_id: "ndf", espace: "client", selectionne: false }]) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec, information: vi.fn() } }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { PanneauDroitsCle } from "@/components/mark/cles/PanneauDroitsCle";

import { VueJournal } from "./VueJournal";
import { VueMembres } from "./VueMembres";

const REGLAGES = { message_acces_bloque: { fr: "", en: "", defaut: { fr: "Votre accès est bloqué.", en: "Your access is blocked." } }, journal_mois: 12, journal_mois_min: 1, journal_mois_max: 120 };

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    m.reglages.mockResolvedValue({ data: REGLAGES });
    m.types.mockResolvedValue({ data: ["cle_api.creer", "membre.acces_bloque"] });
    m.acces.mockResolvedValue({});
    m.interrupteurs.mockResolvedValue({});
    m.role.mockResolvedValue({});
    m.suspendre.mockResolvedValue({});
    m.membres.mockResolvedValue({
        data: {
            membres: [
                { user_id: 1, email: "a@b.c", prenom: "Evan", nom: "L", role_id: 1, role_nom: "Administrateur", depuis: null, acces_actif: true },
                { user_id: 2, email: "p@b.c", prenom: "Pierre", nom: "M", role_id: 1, role_nom: "Administrateur", depuis: null, acces_actif: false },
            ],
            total: 2, limit: 25, offset: 0,
        },
    });
    m.journal.mockResolvedValue({
        data: {
            lignes: [{ id: 1, quand: "2026-11-09T10:00:00Z", user_id: 1, auteur: "x", prenom: "Evan", nom: "L", action: "cle_api.creer", organization_id: 7, detail: null, origine: "mcp" }],
            total: 1, limit: 25, offset: 0,
        },
    });
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const dans = (ui: React.ReactElement) => render(<FournisseurLangue>{ui}</FournisseurLangue>);

describe("[.mark] clôture, lot A : l'écran", () => {
    it("accès actif : bloquer appelle le serveur et le dit ; un échec reste dit ; un membre bloqué se lit « Bloqué »", async () => {
        dans(<VueMembres />);
        const evan = await screen.findByRole("switch", { name: /Accès actif de Evan L/ });
        expect(screen.getByText("Bloqué")).toBeTruthy();
        expect((screen.getByRole("switch", { name: /Accès actif de Pierre M/ }) as HTMLElement).getAttribute("aria-checked")).toBe("false");
        fireEvent.click(evan);
        await waitFor(() => expect(m.acces).toHaveBeenCalledWith(1, false));
        await waitFor(() => expect(m.succes).toHaveBeenCalledWith({ fr: "Accès bloqué : sessions et clés coupées.", en: "Access blocked: sessions and keys cut." }));
        m.acces.mockResolvedValue({ error: { detail: "x" } });
        fireEvent.click(await screen.findByRole("switch", { name: /Accès actif de Pierre M/ }));
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
    });

    it("journal : les filtres type de geste et porte partent au serveur ; la porte et les gestes nouveaux se disent en clair", async () => {
        dans(<VueJournal />);
        await screen.findByText("A créé une clé d'API");
        expect(within(screen.getByRole("table")).getByText("MCP")).toBeTruthy();
        const filtres = await screen.findByTestId("filtres-du-journal");
        const [, , type, porte] = within(filtres).getAllByRole("combobox");
        fireEvent.keyDown(type, { key: "Enter" });
        fireEvent.click(await screen.findByRole("option", { name: "A bloqué l'accès d'un membre" }));
        await waitFor(() => expect(m.journal).toHaveBeenLastCalledWith(expect.objectContaining({ action: "membre.acces_bloque", offset: 0 })));
        fireEvent.keyDown(porte, { key: "Enter" });
        fireEvent.click(await screen.findByRole("option", { name: "API" }));
        await waitFor(() => expect(m.journal).toHaveBeenLastCalledWith(expect.objectContaining({ action: "membre.acces_bloque", origine: "api" })));
    });

    it("durée du journal : bornée, message sous le champ, rien n'est envoyé hors bornes", async () => {
        m.duree.mockResolvedValue({ data: { ...REGLAGES, journal_mois: 6 } });
        dans(<VueJournal />);
        const champ = (await screen.findByLabelText("Gardé (mois)")) as HTMLInputElement;
        fireEvent.change(champ, { target: { value: "5000" } });
        expect(screen.getByRole("alert").textContent).toContain("Entre 1 et 120 mois");
        expect((screen.getByRole("button", { name: "Enregistrer" }) as HTMLButtonElement).disabled).toBe(true);
        fireEvent.change(champ, { target: { value: "6" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.duree).toHaveBeenCalledWith(6));
        expect(m.duree).toHaveBeenCalledTimes(1);
    });

    it("panneau d'une clé : trois interrupteurs MCP éteints, désactivés sans rôle ; avec un rôle, un interrupteur appelle le serveur", async () => {
        const recharger = vi.fn();
        const { rerender } = dans(<PanneauDroitsCle cle={{ id: 9, role_id: null }} recharger={recharger} />);
        for (const nom of ["Publier par MCP", "Tests payants par MCP", "Appels réels par MCP"]) {
            const s = screen.getByRole("switch", { name: nom }) as HTMLButtonElement;
            expect(s.getAttribute("aria-checked")).toBe("false");
            expect(s.disabled).toBe(true);
        }
        rerender(
            <FournisseurLangue>
                <PanneauDroitsCle cle={{ id: 9, role_id: 3, role_nom: "Éditeur", mcp_publier: false }} recharger={recharger} />
            </FournisseurLangue>,
        );
        fireEvent.click(screen.getByRole("switch", { name: "Publier par MCP" }));
        await waitFor(() => expect(m.interrupteurs).toHaveBeenCalledWith(9, { publier: true }));
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
        expect(recharger).toHaveBeenCalled();
        fireEvent.click(screen.getByRole("switch", { name: "Clé active" }));
        await waitFor(() => expect(m.suspendre).toHaveBeenCalledWith(9, true));
    });
});
