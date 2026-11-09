/**
 * [.mark] U2 ter, sous-lot 4 : Réglages › Équipe et rôles, branché sur `/equipe-mark/*`.
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | accès | sans ``equipe.gerer``, l'état « accès » remplace la page ; aucun membre n'est demandé |
 * | membres | les membres, leur rôle et les invitations en attente viennent du serveur ; une page de 25 à la fois |
 * | rôles | un rôle montre ses espaces et ses permissions réelles (n sur 15) ; Administrateur en lecture |
 * | journal | qui, quoi (dit en clair), quel espace, quand |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const sdk = vi.hoisted(() => ({
    monProfil: vi.fn(),
    membres: vi.fn(),
    invitations: vi.fn(),
    roles: vi.fn(),
    catalogue: vi.fn(),
    journal: vi.fn(),
}));
vi.mock("@/client/sdk.gen", () => ({
    monProfilApiV1EquipeMarkMoiGet: sdk.monProfil,
    listerLesMembresApiV1EquipeMarkMembresGet: sdk.membres,
    listerLesInvitationsApiV1EquipeMarkInvitationsGet: sdk.invitations,
    listerLesRolesApiV1EquipeMarkRolesGet: sdk.roles,
    catalogueApiV1EquipeMarkPermissionsGet: sdk.catalogue,
    annulerUneInvitationApiV1EquipeMarkInvitationsInvitationIdDelete: vi.fn(),
    changerLeRoleDUnMembreApiV1EquipeMarkMembresUserIdRolePut: vi.fn(),
    inviterApiV1EquipeMarkInvitationsPost: vi.fn(),
    retirerUnMembreApiV1EquipeMarkMembresUserIdDelete: vi.fn(),
    creerUnRoleApiV1EquipeMarkRolesPost: vi.fn(),
    modifierUnRoleApiV1EquipeMarkRolesRoleIdPut: vi.fn(),
    supprimerUnRoleApiV1EquipeMarkRolesRoleIdDelete: vi.fn(),
}));
vi.mock("./api-cloture", () => ({
    lireLeJournalFiltre: sdk.journal,
    typesDeGestes: vi.fn(async () => ({ data: [] })),
    lireLesReglagesDeLEquipe: vi.fn(async () => ({ data: undefined })),
    changerLAcces: vi.fn(),
}));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("@/lib/espaces", () => ({
    listerEspaces: vi.fn(async () => [{ id: 7, nom: "Nuances de Feu", provider_id: "ndf", espace: "client", selectionne: false }]),
}));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { EquipeEtRoles } from "./PageEquipe";

const ok = <T,>(data: T) => Promise.resolve({ data, error: undefined });

beforeEach(() => {
    Object.values(sdk).forEach((f) => f.mockReset());
    sdk.membres.mockImplementation(() =>
        ok({
            membres: [
                { user_id: 1, email: "evan@exemple.fr", prenom: "Evan", nom: "L", role_id: 1, role_nom: "Administrateur", depuis: "2026-03-12T09:00:00Z" },
                { user_id: 2, email: "pierre@exemple.fr", prenom: null, nom: null, role_id: 2, role_nom: "Membre" },
            ],
            total: 2,
            limit: 25,
            offset: 0,
        }),
    );
    sdk.invitations.mockImplementation(() =>
        ok({ invitations: [{ id: 9, email: "lea@exemple.fr", role_id: 2, role_nom: "Membre", expire_le: "2026-11-05T10:00:00Z" }], total: 1, limit: 25, offset: 0 }),
    );
    sdk.roles.mockImplementation(() =>
        ok([
            { id: 1, nom: "Administrateur", fixe: true, labo_ouvert: true, tous_les_clients: true, permissions: [], organisations: [], membres: 1 },
            {
                id: 2, nom: "Membre", fixe: false, labo_ouvert: true, tous_les_clients: false,
                permissions: ["agents.modifier", "builder.lancer", "tests.jouer", "conversations.voir"], organisations: [7], membres: 1,
            },
        ]),
    );
    sdk.catalogue.mockImplementation(() =>
        ok(Array.from({ length: 15 }, (_, i) => ({ cle: `p${i}`, groupe: "G", libelle: `Permission ${i}` }))),
    );
    sdk.journal.mockImplementation(() =>
        ok({
            lignes: [{ id: 1, quand: "2026-11-03T10:00:00Z", user_id: 1, auteur: "oss_1", prenom: "Evan", nom: "L", action: "invitation.creer", organization_id: 7, detail: null }],
            total: 1, limit: 25, offset: 0,
        }),
    );
});
afterEach(cleanup);

const monter = () =>
    render(
        <FournisseurLangue>
            <EquipeEtRoles />
        </FournisseurLangue>,
    );

describe("Équipe et rôles", () => {
    it("sans la permission : l'état « accès », aucun membre demandé", async () => {
        sdk.monProfil.mockImplementation(() => ok({ permissions: ["conversations.voir"] }));
        monter();
        await waitFor(() => expect(sdk.monProfil).toHaveBeenCalled());
        await waitFor(() => expect(screen.queryByText("Équipe et rôles")).toBeNull());
        expect(sdk.membres).not.toHaveBeenCalled();
    });

    it("membres et invitations en attente viennent du serveur, paginés par 25", async () => {
        sdk.monProfil.mockImplementation(() => ok({ permissions: ["equipe.gerer", "roles.gerer"] }));
        monter();
        await waitFor(() => expect(screen.getByText("Evan L")).toBeTruthy());
        expect(screen.getAllByText("pierre@exemple.fr").length).toBeGreaterThan(0); // sans nom : l'adresse
        expect(screen.getByText("lea@exemple.fr")).toBeTruthy();
        expect(sdk.membres).toHaveBeenCalledWith({ query: { limit: 25, offset: 0 } });
    });

    it("V4 : la colonne « Depuis » dit la date d'entrée lue du serveur, et un tiret quand elle manque", async () => {
        sdk.monProfil.mockImplementation(() => ok({ permissions: ["equipe.gerer", "roles.gerer"] }));
        monter();
        const evan = (await screen.findByText("Evan L")).closest("tr")!;
        expect(screen.getByText("Depuis")).toBeTruthy();
        expect(evan.textContent).toMatch(/12 mars 2026/);
        const pierre = screen.getAllByText("pierre@exemple.fr")[0].closest("tr")!;
        expect(pierre.textContent).toContain("—");
    });

    it("les rôles : espaces ouverts et permissions réelles ; le journal : qui, quoi, quel espace", async () => {
        sdk.monProfil.mockImplementation(() => ok({ permissions: ["equipe.gerer", "roles.gerer", "journal.lire"] }));
        monter();
        await waitFor(() => expect(screen.getByText("Evan L")).toBeTruthy());
        await waitFor(() => expect(screen.getByText("4 sur 15")).toBeTruthy());
        expect(screen.getByText("15 sur 15")).toBeTruthy(); // Administrateur : toutes
        expect(screen.getByText("Labo · 1 client(s)")).toBeTruthy();

        fireEvent.click(screen.getByRole("button", { name: "Consulter" }));
        await waitFor(() => expect(screen.getByText("A invité un membre")).toBeTruthy());
        expect(screen.getAllByText("Evan L").length).toBeGreaterThan(0);
        expect(screen.getByText("Nuances de Feu")).toBeTruthy();
    });
});
