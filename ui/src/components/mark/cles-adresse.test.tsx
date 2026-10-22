/**
 * [.mark] La bibliothèque de clés : protocole, fournisseur libre et adresse rattachée à la clé
 * (fiabilite-orchestration, lot 10, F10).
 *
 * Questions de ce fichier :
 *
 *     Le menu d'avant s'appelle-t-il « Protocole » ? Un champ « Fournisseur » en texte libre et une
 *     adresse partent-ils avec la clé ? La liste montre-t-elle le fournisseur libre et l'adresse
 *     d'une clé qui en a, et rien de plus pour une clé d'avant ? Choisir une clé qui a une adresse
 *     la donne au réglage, dans le même changement que la référence ?
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ChampCleModele } from "./cles/ChampCleModele";
import { BibliothequeCles } from "./cles/FenetreCles";

const ADRESSE = "https://api.fournisseur-test.example/v1";

const { ajouter, liste } = vi.hoisted(() => ({
    ajouter: vi.fn(),
    liste: [
        { uuid: "c-vieille", nom: "Mistral d'avant", fournisseur: "mistral" },
        {
            uuid: "c-scaleway",
            nom: "Scaleway Mistral",
            fournisseur: "mistral",
            nom_fournisseur: "Scaleway",
            adresse: "https://api.fournisseur-test.example/v1",
        },
    ] as { uuid: string; nom: string; fournisseur: string; nom_fournisseur?: string; adresse?: string }[],
}));

vi.mock("@/client", () => ({
    listerLesClesApiV1ClesGet: async () => ({ data: liste }),
    fournisseursDesClesApiV1ClesFournisseursGet: async () => ({ data: ["mistral", "openai"] }),
    ajouterUneCleApiV1ClesPost: (...a: unknown[]) => ajouter(...a),
    usagesDUneCleApiV1ClesUuidUsagesGet: vi.fn(),
    supprimerUneCleApiV1ClesUuidDelete: vi.fn(),
    identifiantDesigneApiV1ClesDesigneeUuidGet: vi.fn(),
}));

beforeEach(() => vi.clearAllMocks());

describe("[.mark] la bibliothèque de clés : protocole, fournisseur libre, adresse", () => {
    it("nomme le menu « Protocol », ajoute le fournisseur libre et l'adresse, et les envoie avec la clé", async () => {
        ajouter.mockResolvedValue({ data: { uuid: "nouvelle", nom: "N", fournisseur: "mistral" } });
        render(<BibliothequeCles />);
        const protocole = await screen.findByLabelText("Protocol");
        expect(protocole.tagName).toBe("SELECT");
        fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "Scaleway Mistral 2" } });
        fireEvent.change(screen.getByLabelText("Provider"), { target: { value: " Scaleway " } });
        fireEvent.change(screen.getByLabelText("Provider address"), { target: { value: ADRESSE } });
        fireEvent.change(screen.getByLabelText("Key value"), { target: { value: "SECRET-12345678" } });
        fireEvent.click(screen.getByRole("button", { name: "Save the key" }));
        await waitFor(() => expect(ajouter).toHaveBeenCalledOnce());
        expect(ajouter.mock.calls[0][0].body).toEqual({
            fournisseur: "mistral",
            nom: "Scaleway Mistral 2",
            cle: "SECRET-12345678",
            nom_fournisseur: "Scaleway",
            adresse: ADRESSE,
        });
    });

    it("n'envoie ni fournisseur libre ni adresse quand on n'en met pas (la clé d'avant)", async () => {
        ajouter.mockResolvedValue({ data: { uuid: "nouvelle", nom: "N", fournisseur: "mistral" } });
        render(<BibliothequeCles />);
        await screen.findByLabelText("Protocol");
        fireEvent.change(screen.getByLabelText("Key name"), { target: { value: "Simple" } });
        fireEvent.change(screen.getByLabelText("Key value"), { target: { value: "SECRET-12345678" } });
        fireEvent.click(screen.getByRole("button", { name: "Save the key" }));
        await waitFor(() => expect(ajouter).toHaveBeenCalledOnce());
        const corps = ajouter.mock.calls[0][0].body;
        expect(corps.nom_fournisseur).toBeUndefined();
        expect(corps.adresse).toBeUndefined();
    });

    it("montre le fournisseur libre et l'adresse d'une clé qui en a, rien de plus pour une clé d'avant", async () => {
        render(<BibliothequeCles />);
        const nouvelle = await screen.findByTestId("cle-c-scaleway");
        expect(nouvelle.textContent).toContain("Scaleway · Mistral");
        expect(within(nouvelle).getByTestId("adresse-de-la-cle").textContent).toBe(ADRESSE);
        const vieille = screen.getByTestId("cle-c-vieille");
        expect(within(vieille).queryByTestId("adresse-de-la-cle")).toBeNull();
        expect(vieille.textContent).not.toContain("·  ·");
    });
});

describe("[.mark] choisir une clé qui a une adresse la donne au réglage", () => {
    it("rend la référence ET l'adresse dans le même changement ; une clé sans adresse, la référence seule", async () => {
        const onChange = vi.fn();
        render(<ChampCleModele valeur="tapee" fournisseur="mistral" onChange={onChange} />);
        fireEvent.click(screen.getByRole("button", { name: "Keys…" }));
        const fenetre = await screen.findByTestId("fenetre-cles");
        fireEvent.click(within(await within(fenetre).findByTestId("cle-c-scaleway")).getByRole("button", { name: "Use" }));
        await waitFor(() => expect(onChange).toHaveBeenCalledOnce());
        expect(onChange).toHaveBeenCalledWith("mark-cle:c-scaleway", ADRESSE);
        onChange.mockClear();

        fireEvent.click(screen.getByRole("button", { name: "Keys…" }));
        const seconde = await screen.findByTestId("fenetre-cles");
        fireEvent.click(within(await within(seconde).findByTestId("cle-c-vieille")).getByRole("button", { name: "Use" }));
        await waitFor(() => expect(onChange).toHaveBeenCalledOnce());
        expect(onChange).toHaveBeenCalledWith("mark-cle:c-vieille", undefined);
    });

    it("nomme l'adresse de la clé désignée", async () => {
        render(<ChampCleModele valeur="mark-cle:c-scaleway" fournisseur="mistral" onChange={vi.fn()} />);
        expect((await screen.findByTestId("cle-de-la-bibliotheque")).textContent).toContain(
            `Scaleway Mistral · Mistral · key library · ${ADRESSE}`,
        );
    });
});
