/**
 * [.mark] Partie 3, lot 15 (SE-25, L-1) : l'état remonté dans la ligne d'un thème, au lieu de « Dans la fenêtre ».
 *
 *   - Développeurs : clés d'API (nombre lu sur la route), serveur MCP (prêt avec une clé), traçage Langfuse (configuré ou non) ;
 *   - une lecture qui échoue dit « illisible », jamais un état inventé ;
 *   - Intégrations : le repli en cas de panne dit si une adresse de secours est réglée ; l'agenda dit le logiciel branché.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FormeMaquette } from "../ecran/forme-maquette";
import { ContexteLignes } from "../ecran/Theme";
import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ cles: vi.fn(), langfuse: vi.fn(), panne: vi.fn(), connexions: vi.fn(), catalogue: vi.fn() }));
vi.mock("@/client/sdk.gen", async (importOriginal) =>
    (await import("../sdk-factice")).sdkFactice(await importOriginal(), {
        getApiKeysApiV1UserApiKeysGet: (...a: unknown[]) => m.cles(...a),
        getLangfuseCredentialsApiV1OrganizationsLangfuseCredentialsGet: (...a: unknown[]) => m.langfuse(...a),
        getPanneApiV1OrganizationsPanneGet: (...a: unknown[]) => m.panne(...a),
        getConnexionsApiV1ConnecteursConnexionsGet: (...a: unknown[]) => m.connexions(...a),
        getCatalogueApiV1ConnecteursCatalogueGet: (...a: unknown[]) => m.catalogue(...a),
    }),
);
vi.mock("@/lib/auth", () => ({ useAuth: () => SESSION }));
const SESSION = vi.hoisted(() => ({ user: { id: 1 }, loading: false }));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => null }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => null }));
vi.mock("./BlocSecoursPanne", () => ({ BlocSecoursPanne: () => null }));

import { ThemeDeveloppeurs, ThemeIntegrations } from "./ThemesOrganisation";

afterEach(() => {
    cleanup();
    Object.values(m).forEach((f) => f.mockReset());
});

const commun = { ouvert: false, onBasculer: vi.fn(), ouvrir: vi.fn(), signaler: vi.fn() };
const ligne = (nom: string) => screen.getByText(nom).closest("li, div, tr")!;

describe("[.mark] lot 15 : les lignes disent leur état (L-1)", () => {
    it("Développeurs : clés d'API comptées, serveur MCP prêt avec une clé, Langfuse configuré", async () => {
        m.cles.mockResolvedValue({ data: [{ is_active: true }, { is_active: true }, { is_active: false }] });
        m.langfuse.mockResolvedValue({ data: { configured: true } });
        render(
            <FournisseurLangue>
                <FormeMaquette>
                    <ContexteLignes.Provider value={{ annuler: vi.fn() }}>
                        <ThemeDeveloppeurs {...commun} />
                    </ContexteLignes.Provider>
                </FormeMaquette>
            </FournisseurLangue>,
        );
        await waitFor(() => expect(document.body.textContent).toContain("2 clés"));
        expect(document.body.textContent).toContain("Prêt (clé d'API)");
        expect(document.body.textContent).toContain("Configuré");
        expect(document.body.textContent).not.toContain("Dans la fenêtre");
        expect(ligne("Clés d'API de Dograh")).toBeTruthy();
    });

    it("sans clé : le serveur MCP le dit ; Langfuse non configuré ; une lecture en échec dit « illisible »", async () => {
        m.cles.mockResolvedValue({ data: [] });
        m.langfuse.mockResolvedValue({ error: { detail: "x" } });
        render(
            <FournisseurLangue>
                <FormeMaquette>
                    <ContexteLignes.Provider value={{ annuler: vi.fn() }}>
                        <ThemeDeveloppeurs {...commun} />
                    </ContexteLignes.Provider>
                </FormeMaquette>
            </FournisseurLangue>,
        );
        await waitFor(() => expect(document.body.textContent).toContain("Aucune clé"));
        expect(document.body.textContent).toContain("Sans clé d'API : injoignable");
        expect(document.body.textContent).toContain("illisible");
        expect(document.body.textContent).not.toContain("Configuré");
    });

    it("Intégrations : le repli dit s'il a une adresse de secours, l'agenda dit le logiciel branché", async () => {
        m.panne.mockResolvedValue({ data: { reglages: { url_secours: "https://secours.example.test" }, texte_du_bin: "", texte_du_bin_promesse: "" } });
        m.catalogue.mockResolvedValue({ data: [{ nom: "google_agenda", libelle: "Google Agenda", integration: "google-calendar", categorie: "Agenda", etat: "a_essayer", actions: [] }] });
        m.connexions.mockResolvedValue({ data: { nango_configure: true, connexions: [{ integration: "google-calendar", connection_id: "c1", erreurs: 0 }] } });
        const preferences = { chargement: false, enCours: false, enregistrees: {}, enregistrer: vi.fn() };
        render(
            <FournisseurLangue>
                <FormeMaquette>
                    <ContexteLignes.Provider value={{ annuler: vi.fn() }}>
                        <ThemeIntegrations {...commun} preferences={preferences as never} />
                    </ContexteLignes.Provider>
                </FormeMaquette>
            </FournisseurLangue>,
        );
        await waitFor(() => expect(document.body.textContent).toContain("Adresse de secours réglée"));
        await waitFor(() => expect(document.body.textContent).toContain("Google Agenda"));
        expect(document.body.textContent).not.toContain("Dans la fenêtre");
    });
});
