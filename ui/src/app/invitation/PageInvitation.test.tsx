/**
 * [.mark] U2 ter : la page « Rejoindre l'équipe .mark ».
 *
 * | Test | Ce qu'il prouve |
 * |---|---|
 * | lien refusé | un jeton inconnu, périmé ou utilisé montre « Invitation périmée », sans formulaire |
 * | sans jeton | pas d'appel au serveur, même écran |
 * | lien valable | l'adresse et le rôle de l'invitation, prénom, nom, mot de passe |
 * | 12 caractères | le bouton reste fermé tant que le mot de passe a moins de 12 caractères ou n'est pas confirmé |
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "@/components/mark/langue/langue";

const lire = vi.fn();
vi.mock("@/client/sdk.gen", () => ({
    lireUneInvitationApiV1AuthInvitationJetonGet: (...a: unknown[]) => lire(...a),
    accepterUneInvitationApiV1AuthInvitationJetonAccepterPost: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import { PageInvitation } from "./PageInvitation";

const monter = (jeton: string) =>
    render(
        <FournisseurLangue>
            <PageInvitation jeton={jeton} />
        </FournisseurLangue>,
    );

beforeEach(() => lire.mockReset());
afterEach(cleanup);

describe("page Rejoindre l'équipe", () => {
    it("un lien refusé par le serveur : invitation périmée, aucun formulaire", async () => {
        lire.mockResolvedValue({ error: { detail: "gone" }, data: undefined });
        monter("mort");
        await waitFor(() => expect(screen.getByText("Invitation périmée")).toBeTruthy());
        expect(screen.queryByLabelText("Mot de passe")).toBeNull();
    });

    it("sans jeton : même écran, aucun appel", () => {
        monter("");
        expect(screen.getByText("Invitation périmée")).toBeTruthy();
        expect(lire).not.toHaveBeenCalled();
    });

    it("un lien valable : l'adresse invitée, son rôle, et un mot de passe de 12 caractères au moins", async () => {
        lire.mockResolvedValue({ data: { email: "pierre@exemple.fr", role_nom: "Administrateur" }, error: undefined });
        monter("bon");
        await waitFor(() => expect(screen.getByText("Administrateur")).toBeTruthy());
        expect((screen.getByLabelText("E-mail") as HTMLInputElement).value).toBe("pierre@exemple.fr");
        const bouton = screen.getByRole("button", { name: "Créer mon compte" }) as HTMLButtonElement;
        expect(bouton.disabled).toBe(true);
        fireEvent.change(screen.getByLabelText(/^Mot de passe/), { target: { value: "court" } });
        fireEvent.change(screen.getByLabelText(/^Confirmer le mot de passe/), { target: { value: "court" } });
        expect(bouton.disabled).toBe(true);
        expect(screen.getByText("12 caractères au moins.")).toBeTruthy();
        fireEvent.change(screen.getByLabelText(/^Mot de passe/), { target: { value: "un-mot-de-passe-long" } });
        expect(bouton.disabled).toBe(true); // pas encore confirmé
        fireEvent.change(screen.getByLabelText(/^Confirmer le mot de passe/), { target: { value: "un-mot-de-passe-long" } });
        expect(bouton.disabled).toBe(false);
    });
});
