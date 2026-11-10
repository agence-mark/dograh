/**
 * [.mark] Correctifs d'écran, point 14 : Réglages d'un client › Général se renomme.
 *
 * Questions de ce fichier :
 *
 *     La ligne « Nom » montre-t-elle le nom d'affichage du client (et seulement dans un client) ? Un nom vide est-il refusé sous
 *     le champ, sans rien envoyer ? Un nom valide part au serveur (nettoyé), dit son succès par une notification, et le nom
 *     change dans le sélecteur d'espace SANS recharger ? Un refus du serveur dit une phrase, garde la fenêtre et sa saisie ?
 */
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({
    chemin: "/clients/2/reglages",
    espaces: [] as Array<{ id: number; nom: string; provider_id: string; espace: string; selectionne: boolean }>,
    regler: vi.fn(),
    succes: vi.fn(),
    echec: vi.fn(),
}));

vi.mock("next/navigation", () => ({ usePathname: () => m.chemin, useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("@/components/mark/notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));
vi.mock("@/lib/espaces", async () => {
    const { signalerChangementDEspaces } = await import("@/lib/espaces-changes");
    return {
        adresseDe: (e: { id: number; espace: string }) => (e.espace === "labo" ? "/labo" : `/clients/${e.id}`),
        listerEspaces: vi.fn(async () => m.espaces.map((e) => ({ ...e }))),
        reglerEspace: async (id: number, corps: { nom_affichage?: string | null }) => {
            await m.regler(id, corps);
            const e = m.espaces.find((x) => x.id === id)!;
            e.nom = corps.nom_affichage ?? e.nom;
            signalerChangementDEspaces();
        },
    };
});
vi.mock("react-timezone-select", () => ({ default: () => <select aria-label="Fuseau" /> }));
vi.mock("@/components/mark/cles/SectionClesApi", () => ({ SectionClesApi: () => <div /> }));
vi.mock("@/components/mark/parametres-organisation/ThemeApresAppel", () => ({ useApresAppel: () => ({ ecran: null }) }));
vi.mock("@/components/mark/parametres-organisation/preferences", () => ({
    usePreferencesOrganisation: () => ({
        chargement: false,
        enCours: false,
        enregistrees: {
            test_phone_number: "",
            timezone: "Europe/Paris",
            adresses_notification: [],
            external_pbx_integrations_enabled: false,
            disposition_mapping_enabled: false,
            disposition_mapping: {},
            adresse_etablissement: null,
        },
        enregistrer: async () => ({ ok: true, refusAdresse: null }),
    }),
}));

import { signalerChangementDEspaces } from "@/lib/espaces-changes";

import { FournisseurLangue } from "../langue/langue";
import { SelecteurEspace } from "../studio/selecteur-espace";
import { ReglagesOrganisation } from "./ReglagesOrganisation";

beforeEach(() => {
    m.chemin = "/clients/2/reglages";
    m.espaces = [
        { id: 1, nom: "Labo", provider_id: "mark", espace: "labo", selectionne: false },
        { id: 2, nom: "Atelier des Tilleuls", provider_id: "t", espace: "client", selectionne: true },
    ];
    m.regler.mockReset();
    m.regler.mockResolvedValue(undefined);
    m.succes.mockReset();
    m.echec.mockReset();
    window.history.replaceState(null, "", "/clients/2/reglages");
    // La lecture des espaces est partagée entre les tests (module) : on la périme.
    signalerChangementDEspaces();
});
afterEach(cleanup);

const monter = () =>
    render(
        <FournisseurLangue>
            <SelecteurEspace espace="client" org="2" />
            <ReglagesOrganisation />
        </FournisseurLangue>,
    );

const ligneNom = async () => (await waitFor(() => document.querySelector("[data-nom-organisation]") as HTMLElement));
const ouvrir = async () => {
    const ligne = await ligneNom();
    await waitFor(() => expect(ligne.textContent).toContain("Atelier des Tilleuls"));
    fireEvent.click(within(ligne).getByRole("button", { name: /Renommer/ }));
    return screen.findByRole("dialog");
};

describe("la ligne « Nom » (point 14)", () => {
    it("montre le nom d'affichage du client, sous le libellé « Nom »", async () => {
        monter();
        const ligne = await ligneNom();
        await waitFor(() => expect(ligne.textContent).toContain("Atelier des Tilleuls"));
        expect(screen.getByText("Nom")).toBeTruthy();
    });

    it("n'existe pas dans le Labo", async () => {
        m.chemin = "/labo/reglages";
        monter();
        await screen.findByText("Numéro de test");
        expect(document.querySelector("[data-nom-organisation]")).toBeNull();
    });

    it("un nom vide est refusé sous le champ, rien n'est envoyé", async () => {
        monter();
        const fenetre = await ouvrir();
        fireEvent.change(within(fenetre).getByLabelText("Nom"), { target: { value: "   " } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Enregistrer" }));
        expect((await within(fenetre).findByRole("alert")).textContent).toContain("Donnez un nom");
        expect(m.regler).not.toHaveBeenCalled();
        expect(m.succes).not.toHaveBeenCalled();
    });

    it("un nom valide part nettoyé, dit son succès, ferme, et change le sélecteur sans recharger", async () => {
        monter();
        const fenetre = await ouvrir();
        fireEvent.change(within(fenetre).getByLabelText("Nom"), { target: { value: "  Menuiserie Durand  " } });
        fireEvent.click(within(fenetre).getByRole("button", { name: "Enregistrer" }));
        await waitFor(() => expect(m.regler).toHaveBeenCalledWith(2, { nom_affichage: "Menuiserie Durand" }));
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        // Le sélecteur d'espace (lu une fois au montage) a relu le nom, comme la ligne elle-même.
        await waitFor(() => expect(document.querySelector("[data-espace='client']")!.textContent).toContain("Menuiserie Durand"));
        expect((await ligneNom()).textContent).toContain("Menuiserie Durand");
    });

    it("un refus du serveur dit une phrase, garde la fenêtre ouverte et la saisie", async () => {
        m.regler.mockRejectedValue(new Error("boom interne SQL"));
        monter();
        const fenetre = await ouvrir();
        fireEvent.change(within(fenetre).getByLabelText("Nom"), { target: { value: "Nouveau nom" } });
        await act(async () => {
            fireEvent.click(within(fenetre).getByRole("button", { name: "Enregistrer" }));
        });
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect(JSON.stringify(m.echec.mock.calls[0][0])).not.toContain("boom interne");
        expect(m.succes).not.toHaveBeenCalled();
        expect(screen.getByRole("dialog")).toBeTruthy();
        expect((within(screen.getByRole("dialog")).getByLabelText("Nom") as HTMLInputElement).value).toBe("Nouveau nom");
    });
});
