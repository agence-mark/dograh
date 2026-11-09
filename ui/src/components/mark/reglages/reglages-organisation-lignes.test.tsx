/**
 * [.mark] K1b (décision d'Evan, 04/11) : Réglages › Organisation comme la maquette. Chaque section se lit en lignes, un
 * bouton « Modifier » ouvre la fenêtre du thème (tous ses réglages, son enregistrement) ; aucune fonction en moins.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";
import { ReglagesOrganisation } from "./ReglagesOrganisation";

const m = vi.hoisted(() => ({ enregistrer: vi.fn() }));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("react-timezone-select", () => ({
    default: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
        <select aria-label="Fuseau" value={value} onChange={(e) => onChange(e.target.value)}>
            <option value="Europe/Paris">Europe/Paris</option>
            <option value="America/New_York">America/New_York</option>
        </select>
    ),
}));
vi.mock("@/components/mark/cles/SectionClesApi", () => ({ SectionClesApi: () => <div data-testid="cles-api" /> }));
vi.mock("@/components/MCPSection", () => ({ MCPSection: () => <div data-testid="mcp" /> }));
vi.mock("@/components/TelemetrySection", () => ({ TelemetrySection: () => <div data-testid="telemetrie" /> }));
vi.mock("@/components/mark/parametres-organisation/ModaleFenetreDuRun", () => ({ ModaleFenetreDuRun: () => null }));
vi.mock("@/components/mark/parametres-organisation/ThemeApresAppel", () => ({ useApresAppel: () => ({ ecran: null }) }));
vi.mock("@/components/mark/parametres-organisation/preferences", async () => {
    const { useState } = await import("react");
    return {
        usePreferencesOrganisation: () => {
            const [enregistrees, setEnregistrees] = useState({
                test_phone_number: "+33344000000",
                timezone: "Europe/Paris",
                adresses_notification: ["evan@exemple.fr", "pierre@exemple.fr"],
                external_pbx_integrations_enabled: false,
                disposition_mapping_enabled: false,
                disposition_mapping: {},
                adresse_etablissement: null,
            });
            return {
                chargement: false,
                enCours: false,
                enregistrees,
                enregistrer: async (brouillon: Record<string, unknown>) => {
                    m.enregistrer(brouillon);
                    setEnregistrees((avant) => ({ ...avant, ...brouillon }));
                    return { ok: true, refusAdresse: null };
                },
            };
        },
    };
});

beforeEach(() => window.history.replaceState(null, "", "/labo/reglages"));
afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const monter = () =>
    render(
        <FournisseurLangue>
            <ReglagesOrganisation />
        </FournisseurLangue>,
    );

describe("Réglages › Organisation en lignes (K1b)", () => {
    it("se lit en lignes, sans champ de saisie, avec un bouton Modifier", () => {
        monter();
        expect(screen.getByText("Numéro de test")).toBeTruthy();
        expect(screen.getByText("+33344000000")).toBeTruthy();
        expect(screen.getByText("evan@exemple.fr, pierre@exemple.fr")).toBeTruthy();
        expect(screen.getByText("Fuseau horaire")).toBeTruthy();
        expect(screen.queryByRole("textbox")).toBeNull();
        expect(screen.getByRole("button", { name: "Modifier" })).toBeTruthy();
    });

    it("Modifier ouvre la fenêtre du thème avec tous ses réglages ; l'explication est dans le « ! », pas sous le titre", () => {
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        const fenetre = screen.getByRole("dialog");
        expect(within(fenetre).getByDisplayValue("+33344000000")).toBeTruthy();
        expect(within(fenetre).getByLabelText("Fuseau")).toBeTruthy();
        expect(within(fenetre).getByRole("button", { name: "Enregistrer Général" })).toBeTruthy();
        expect(within(fenetre).getByRole("button", { name: "Précision" })).toBeTruthy();
        expect(within(fenetre).queryByText(/Réglages communs utilisés par les tests/)).toBeNull();
    });

    it("Enregistrer envoie le brouillon, ferme la fenêtre et met la ligne à jour", async () => {
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        fireEvent.change(screen.getByDisplayValue("+33344000000"), { target: { value: "+33344111111" } });
        fireEvent.click(screen.getByRole("button", { name: "Enregistrer Général" }));
        await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
        expect(m.enregistrer).toHaveBeenCalledWith(expect.objectContaining({ test_phone_number: "+33344111111", timezone: "Europe/Paris" }));
        expect(screen.getByText("+33344111111")).toBeTruthy();
    });

    it("Annuler ferme la fenêtre et oublie le brouillon", () => {
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        fireEvent.change(screen.getByDisplayValue("+33344000000"), { target: { value: "+33399" } });
        fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
        expect(screen.queryByRole("dialog")).toBeNull();
        expect(m.enregistrer).not.toHaveBeenCalled();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        expect(screen.getByDisplayValue("+33344000000")).toBeTruthy();
    });

    it("changer de section avec un brouillon non enregistré prévient, et reste si on refuse", () => {
        const confirmer = vi.spyOn(window, "confirm").mockReturnValue(false);
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        fireEvent.change(screen.getByDisplayValue("+33344000000"), { target: { value: "+33399" } });
        fireEvent.click(screen.getByRole("button", { name: "Développeurs" }));
        expect(confirmer).toHaveBeenCalled();
        expect(screen.getByDisplayValue("+33399")).toBeTruthy();
        confirmer.mockRestore();
    });

    it("Développeurs : MCP, traçage et clés d'API de Dograh restent atteignables, dans la fenêtre", () => {
        monter();
        fireEvent.click(screen.getByRole("button", { name: "Développeurs" }));
        expect(screen.getByText("Serveur MCP")).toBeTruthy();
        expect(screen.queryByTestId("mcp")).toBeNull();
        fireEvent.click(screen.getByRole("button", { name: "Modifier" }));
        expect(screen.getByTestId("mcp")).toBeTruthy();
        expect(screen.getByTestId("telemetrie")).toBeTruthy();
        expect(screen.getByTestId("cles-api")).toBeTruthy();
    });
});
