/**
 * [.mark] The tool type « Integration » on screen (chantier l-agent-travaille, L5), rendered.
 *
 *   - the creation fields propose the catalogue and hand the first action with its defaults;
 *   - the tool page: changing the action resets its rules to the action's own; rules that are
 *     not JSON keep « Save » asleep; « Anticipate » cannot be switched on for an action that
 *     writes (refused by the server too), and shows the trigger fields when on;
 *   - the connections: « Not connected » / « Connected », and the authorization link asked
 *     for THAT connector only (the organization is never sent: the server's).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ChampsCreationIntegration, ConfigOutilIntegration, lireReglages } from "./ConfigOutilIntegration";
import { type ConfigIntegration, configParDefaut, useConnecteurs } from "./useConnecteurs";

const CATALOGUE = [
    {
        nom: "agenda_essai",
        libelle: "Agenda d'essai",
        integration: "agenda-essai",
        actions: [
            {
                nom: "trouver",
                description: "Find slots.",
                ecrit: false,
                anticipable_permis: true,
                parametres: [{ nom: "motif", type: "string", description: "", obligatoire: false }],
                reglages_par_defaut: { nombre: 3 },
            },
            { nom: "poser", description: "Book.", ecrit: true, anticipable_permis: false, parametres: [], reglages_par_defaut: { agenda: "primary" } },
        ],
    },
    // l-agent-collegue (L2): an internal connector, nothing to connect.
    {
        nom: "equipe",
        libelle: "Team (internal)",
        integration: "interne",
        interne: true,
        actions: [
            {
                nom: "diriger_vers_personne",
                description: "Direct to a person.",
                ecrit: true,
                anticipable_permis: false,
                parametres: [{ nom: "personne", type: "string", description: "", obligatoire: true, choix: [], liste_du_contexte: "equipe_cles" }],
                reglages_par_defaut: { delai_transfert_s: 30 },
            },
        ],
    },
];

const m = vi.hoisted(() => ({ connexions: vi.fn(), lien: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) => (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
    getCatalogueApiV1ConnecteursCatalogueGet: () => Promise.resolve({ data: CATALOGUE }),
    getConnexionsApiV1ConnecteursConnexionsGet: m.connexions,
    postLienApiV1ConnecteursLienPost: m.lien,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const Page = ({ valide }: { valide: (v: boolean) => void }) => {
    const connecteurs = useConnecteurs();
    const [valeur, setValeur] = useState<ConfigIntegration | null>(null);
    if (connecteurs.catalogue && !valeur) setValeur(configParDefaut(connecteurs.catalogue));
    if (!valeur) return null;
    return (
        <>
            <ConfigOutilIntegration connecteurs={connecteurs} valeur={valeur} onChange={setValeur} onValide={valide} />
            <output data-testid="envoye">{JSON.stringify(valeur)}</output>
        </>
    );
};

describe("[.mark] the integration tool on screen", () => {
    it("hands the first action of the catalogue with its defaults at creation", async () => {
        m.connexions.mockResolvedValue({ data: { nango_configure: false, connexions: [] } });
        const recu = vi.fn();
        render(
            <FournisseurLangue>
                <ChampsCreationIntegration onChange={recu} />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(recu).toHaveBeenCalled());
        expect(recu.mock.calls.at(-1)?.[0]).toMatchObject({ connecteur: "agenda_essai", action: "trouver", reglages: { nombre: 3 }, anticipable: false });
    });

    it("keeps Save asleep on rules that are not JSON, and anticipates read-only actions only", async () => {
        m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [] } });
        const valide = vi.fn();
        render(
            <FournisseurLangue>
                <Page valide={valide} />
            </FournisseurLangue>,
        );
        const reglages = (await screen.findByRole("textbox", { name: /règles du client/i })) as HTMLTextAreaElement;
        fireEvent.change(reglages, { target: { value: "{ pas du json" } });
        await waitFor(() => expect(valide).toHaveBeenLastCalledWith(false));
        fireEvent.change(reglages, { target: { value: '{"nombre": 2}' } });
        await waitFor(() => expect(valide).toHaveBeenLastCalledWith(true));
        expect(JSON.parse(screen.getByTestId("envoye").textContent!).reglages).toEqual({ nombre: 2 });

        const anticiper = screen.getByRole("switch", { name: /anticiper/i });
        expect(anticiper.getAttribute("aria-disabled")).not.toBe("true");
        fireEvent.click(anticiper);
        fireEvent.change(await screen.findByPlaceholderText("motif"), { target: { value: "motif_appel" } });
        expect(JSON.parse(screen.getByTestId("envoye").textContent!)).toMatchObject({ anticipable: true, declencheurs: { motif: "motif_appel" } });
    });

    it("shows the connection state and asks the link for that connector only", async () => {
        m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [] } });
        m.lien.mockResolvedValue({ data: { lien: "https://connect.example.org/x", expire_le: null } });
        render(
            <FournisseurLangue>
                <Page valide={() => undefined} />
            </FournisseurLangue>,
        );
        expect(await screen.findByText("Non connecté")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /lien d'autorisation pour le client/i }));
        await waitFor(() => expect(m.lien).toHaveBeenCalledWith({ body: { connecteurs: ["agenda_essai"] } }));
        expect(await screen.findByDisplayValue("https://connect.example.org/x")).toBeTruthy();
    });

    it("l-agent-collegue: an internal connector says it runs inside, and shows no connection", async () => {
        m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [] } });
        const Interne = () => {
            const connecteurs = useConnecteurs();
            const [valeur, setValeur] = useState<ConfigIntegration | null>(null);
            if (connecteurs.catalogue && !valeur) setValeur(configParDefaut(connecteurs.catalogue, "equipe"));
            if (!valeur) return null;
            return <ConfigOutilIntegration connecteurs={connecteurs} valeur={valeur} onChange={setValeur} onValide={() => undefined} />;
        };
        const { container } = render(
            <FournisseurLangue>
                <Interne />
            </FournisseurLangue>,
        );
        await waitFor(() => expect(container.querySelector("#connecteur-interne")).not.toBeNull());
        expect(container.querySelector("#connecteur-interne")!.textContent).toMatch(/Rien à connecter/);
        expect(screen.queryByText("Non connecté")).toBeNull();
        // E8: the deadline, the two phrases and the anticipation play no role for it.
        for (const id of ["#integration-delai", "#integration-phrase-attente", "#integration-phrase-repli", "#integration-anticipable"])
            expect(container.querySelector(id), id).toBeNull();
        expect(container.querySelector("#integration-reglages")).not.toBeNull();
        expect(screen.queryByText("Team (internal)", { selector: "span.font-medium" })).toBeNull();
    });

    it("reads the rules typed", () => {
        expect(lireReglages("")).toEqual({});
        expect(lireReglages("[1]")).toBeNull();
        expect(lireReglages('{"a": 1}')).toEqual({ a: 1 });
    });
});
