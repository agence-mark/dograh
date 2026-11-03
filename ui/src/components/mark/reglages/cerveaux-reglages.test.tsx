/**
 * [.mark] K6 : les onglets « Builder IA » et « Appelant simulé » des Réglages du Labo. Questions : un champ quitté s'enregistre-t-il
 * (et une valeur inchangée n'écrit-elle rien) ? la clé n'est-elle jamais relue ? les sous-agents s'écrivent-ils par leur route ?
 * chaque écriture dit-elle son résultat par une notification ?
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { OngletAppelantOuJuge, OngletBuilderIA } from "./CerveauxReglages";

const m = vi.hoisted(() => ({
    cerveauPut: vi.fn(),
    sousPut: vi.fn(),
    notifier: { suivre: vi.fn() },
}));

vi.mock("@/lib/auth", () => ({ useAuth: () => ({ user: { id: 1 }, loading: false }) }));
vi.mock("next/link", () => ({ default: ({ href, children, ...r }: { href: string; children: React.ReactNode }) => <a href={href} {...r}>{children}</a> }));
vi.mock("@/components/mark/notifications/notifier", () => ({ notifier: m.notifier }));
vi.mock("@/components/mark/sources/useSources", () => ({ useSources: () => ({ sources: { builder: "cle_api", appelant: "claude_code" } }) }));
vi.mock("@/components/builder/ecran/OptionsDeConstruction", () => ({ OptionsDeConstruction: () => null }));
vi.mock("@/components/mark/appelant-simule/ModaleReglagesAppelantSimule", () => ({ ModaleReglagesAppelantSimule: ({ ouverte }: { ouverte: boolean }) => (ouverte ? <div>fenetre-reglages</div> : null) }));
vi.mock("@/client", () => ({
    lireLeCerveauApiV1BuilderCerveauGet: async () => ({ data: { format: "anthropic", modele: "claude-x", adresse: "", cle_posee: true, plafond_depense: 2, plafond_jetons: 1500000 } }),
    lireLesPreferencesApiV1BuilderPreferencesGet: async () => ({ data: { texte: "" } }),
    ecrireLesPreferencesApiV1BuilderPreferencesPut: async () => ({}),
    lireLesReglagesDesSousAgentsApiV1BuilderSousAgentsReglagesGet: async () => ({ data: { actif: true, usages: ["analyser", "tester"], modele: "m", en_meme_temps: 3, plafond_delegation: 1 } }),
    listerLesActionsApiV1BuilderActionsGet: async () => ({ data: [{ nom: "agent_lire", description: "d", groupe: "g", ecriture: false, disponible: true, mcp: true }] }),
    reglerLeCerveauApiV1BuilderCerveauPut: (...a: unknown[]) => (m.cerveauPut(...a), Promise.resolve({ data: {} })),
    reglerLesSousAgentsApiV1BuilderSousAgentsReglagesPut: (...a: unknown[]) => (m.sousPut(...a), Promise.resolve({})),
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet: async () => ({ data: { appelant: { modele: "mistral/a", source: "cle_api" }, juge: { modele: "mistral/j", source: "cle_api" }, simultanes: 2 } }),
}));

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

describe("Réglages du Labo, onglet Builder IA", () => {
    it("enregistre le modèle en quittant le champ, avec sa notification, et n'écrit rien s'il n'a pas changé", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const champ = (await screen.findByLabelText(/^(Modèle|Model)$/)) as HTMLInputElement;
        fireEvent.blur(champ);
        expect(m.cerveauPut).not.toHaveBeenCalled();
        fireEvent.change(champ, { target: { value: "claude-y" } });
        fireEvent.blur(champ);
        await waitFor(() => expect(m.cerveauPut).toHaveBeenCalledTimes(1));
        expect(m.cerveauPut.mock.calls[0][0].body.modele).toBe("claude-y");
        expect(m.notifier.suivre).toHaveBeenCalled();
    });

    it("ne relit jamais la clé et l'envoie seulement quand elle est saisie", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        const cle = (await screen.findByLabelText(/^(Clé|Key)$/)) as HTMLInputElement;
        expect(cle.value).toBe("");
        fireEvent.blur(cle);
        expect(m.cerveauPut).not.toHaveBeenCalled();
        fireEvent.change(cle, { target: { value: "secret-de-test" } });
        fireEvent.blur(cle);
        await waitFor(() => expect(m.cerveauPut.mock.calls[0][0].body.cle).toBe("secret-de-test"));
    });

    it("écrit les sous-agents par leur route", async () => {
        render(<OngletBuilderIA aller={vi.fn()} />);
        fireEvent.click(await screen.findByRole("switch", { name: /Comparer|Compare/ }));
        await waitFor(() => expect(m.sousPut).toHaveBeenCalledTimes(1));
        expect(m.sousPut.mock.calls[0][0].body.usages).toContain("comparer");
    });

    it("liste les outils du registre et renvoie vers Sources", async () => {
        const aller = vi.fn();
        render(<OngletBuilderIA aller={aller} />);
        expect(await screen.findByText("agent_lire")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: "Sources" }));
        expect(aller).toHaveBeenCalled();
    });
});

describe("Réglages du Labo, onglet Appelant simulé", () => {
    it("lit ses réglages réels et ouvre la fenêtre de réglage", async () => {
        render(<OngletAppelantOuJuge role="appelant" aller={vi.fn()} />);
        expect(await screen.findByText("mistral/a")).toBeTruthy();
        expect(screen.getByText("2")).toBeTruthy();
        fireEvent.click(screen.getByRole("button", { name: /Régler|Settings/ }));
        expect(screen.getByText("fenetre-reglages")).toBeTruthy();
    });
});
