/**
 * [.mark] U2 : le sélecteur d'espace montre le nom de l'espace où l'adresse place l'onglet, lu dans `GET /espaces`.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { SelecteurEspace } from "./selecteur-espace";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ loading: false, user: { email: "a@b.c" } }) }));
vi.mock("@/lib/espaces", () => ({
    adresseDe: (e: { id: number; espace: string }) => (e.espace === "labo" ? "/labo" : `/clients/${e.id}`),
    listerEspaces: vi.fn(async () => [
        { id: 1, nom: "Atelier .mark", provider_id: "mark", espace: "labo", selectionne: false },
        { id: 7, nom: "Nuances de Feu", provider_id: "ndf", espace: "client", selectionne: true },
    ]),
}));

afterEach(cleanup);

const monter = (espace: "labo" | "client", org: string | null) =>
    render(
        <FournisseurLangue>
            <SelecteurEspace espace={espace} org={org} />
        </FournisseurLangue>,
    );

describe("sélecteur d'espace", () => {
    it("dans un client : son nom d'affichage, pas son identifiant", async () => {
        monter("client", "7");
        await waitFor(() => expect(screen.getByText("Nuances de Feu")).toBeTruthy());
        expect(document.querySelector("[data-espace='client']")).not.toBeNull();
    });

    it("dans le Labo : le nom donné au Labo", async () => {
        monter("labo", null);
        await waitFor(() => expect(screen.getByText("Atelier .mark")).toBeTruthy());
        expect(document.querySelector("[data-espace='labo']")).not.toBeNull();
    });

    it("SE-1 : aucun libellé « Espace » au-dessus du nom ; « Client » reste pour un client", async () => {
        monter("labo", null);
        await waitFor(() => expect(screen.getByText("Atelier .mark")).toBeTruthy());
        expect(screen.queryByText("Espace")).toBeNull();
        cleanup();
        monter("client", "7");
        await waitFor(() => expect(screen.getByText("Nuances de Feu")).toBeTruthy());
        expect(screen.getByText("Client")).toBeTruthy();
    });

    it("avant la réponse du serveur : un libellé sans fausse valeur", () => {
        monter("labo", null);
        expect(screen.getByText("Labo")).toBeTruthy();
    });
});
