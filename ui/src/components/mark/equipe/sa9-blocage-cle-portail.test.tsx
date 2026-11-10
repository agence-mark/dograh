/**
 * [.mark] Clôture, SA-9 (8) : la clé du portail appartient à la personne qui l'a régénérée.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | blocage | bloquer une personne qui porte une clé de portail ouvre une fenêtre qui le dit (français, anglais) ; rien n'est coupé avant « Bloquer quand même » |
 * | sans clé | une personne sans clé de portail se bloque comme avant, sans fenêtre |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const m = vi.hoisted(() => ({ acces: vi.fn(), membres: vi.fn(), succes: vi.fn(), echec: vi.fn() }));
vi.mock("@/client/sdk.gen", () => ({
    listerLesMembresApiV1EquipeMarkMembresGet: m.membres,
    listerLesInvitationsApiV1EquipeMarkInvitationsGet: vi.fn(async () => ({ data: { invitations: [], total: 0, limit: 25, offset: 0 } })),
    listerLesRolesApiV1EquipeMarkRolesGet: vi.fn(async () => ({ data: [] })),
    annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete: vi.fn(),
    changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut: vi.fn(),
    inviterApiV1EquipeMarkInvitationsPost: vi.fn(),
    retirerUnMembreApiV1EquipeMarkMembresUserIdDelete: vi.fn(),
}));
vi.mock("./api-cloture", () => ({ changerLAcces: m.acces, lireLesReglagesDeLEquipe: vi.fn(async () => ({ data: undefined })), reglerLeMessageBloque: vi.fn() }));
vi.mock("./ReglagesDeLEquipe", () => ({ ReglageMessageBloque: () => null }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec, information: vi.fn() } }));

import { VueMembres } from "./VueMembres";

beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn();
    m.acces.mockResolvedValue({});
    m.membres.mockResolvedValue({
        data: {
            membres: [
                { user_id: 1, email: "e@b.c", prenom: "Evan", nom: "L", role_id: 1, role_nom: "Administrateur", depuis: null, acces_actif: true, cles_portail: 2 },
                { user_id: 2, email: "p@b.c", prenom: "Pierre", nom: "M", role_id: 1, role_nom: "Administrateur", depuis: null, acces_actif: true, cles_portail: 0 },
            ],
            total: 2, limit: 25, offset: 0,
        },
    });
});
afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const dans = () => render(<FournisseurLangue><VueMembres /></FournisseurLangue>);

describe("[.mark] SA-9 : bloquer une personne qui porte une clé de portail", () => {
    it("la fenêtre le dit avant ; rien n'est coupé tant qu'on ne confirme pas", async () => {
        dans();
        fireEvent.click(await screen.findByRole("switch", { name: /Accès actif de Evan L/ }));
        expect(await screen.findByText(/porte la clé du portail de 2 client\(s\)/)).toBeTruthy();
        expect(screen.getByText(/La bloquer coupe aussi ce portail/)).toBeTruthy();
        expect(m.acces).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Bloquer quand même" }));
        await waitFor(() => expect(m.acces).toHaveBeenCalledWith(1, false));
    });

    it("sans clé de portail : le blocage part tout de suite, comme avant", async () => {
        dans();
        fireEvent.click(await screen.findByRole("switch", { name: /Accès actif de Pierre M/ }));
        await waitFor(() => expect(m.acces).toHaveBeenCalledWith(2, false));
        expect(screen.queryByText(/clé du portail/)).toBeNull();
    });
});
