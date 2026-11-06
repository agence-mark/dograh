/**
 * [.mark] K3 : le thème « Sécurité » de l'onglet Réglages d'un agent (U3 quinquies, E68), rendu.
 *
 *   - tout est éteint par défaut, les phrases n'apparaissent qu'une fois la consigne allumée ;
 *   - ce qui s'enregistre est la clé `securite_conversation` complète, au format du schéma serveur ;
 *   - une valeur que le serveur refuserait (mots récités hors 6 à 60) est dite et bloque l'enregistrement ;
 *   - les réglages du classifieur n'apparaissent qu'une fois l'écoute allumée.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UnsavedChangesProvider } from "@/context/UnsavedChangesContext";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { FournisseurLangue } from "../langue/langue";
import { completerSecurite, erreurMots, ThemeSecurite } from "./ThemeSecurite";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
});

const monter = (securite?: WorkflowConfigurations["securite_conversation"]) => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
        <FournisseurLangue>
            <UnsavedChangesProvider>
            <ThemeSecurite
                resolue={{ securite_conversation: securite } as WorkflowConfigurations}
                workflowName="Agent"
                onSave={onSave}
                ouvert
                onBasculer={() => undefined}
                ouvrir={() => undefined}
            />
            </UnsavedChangesProvider>
        </FournisseurLangue>,
    );
    return onSave;
};

describe("[.mark] le thème Sécurité", () => {
    it("complète les défauts du serveur : tout éteint, 12 mots, normale, marquer allumé", () => {
        const c = completerSecurite(undefined);
        expect([c.manipulation.actif, c.confidentialite.actif, c.role.actif, c.urgence.actif, c.jamais.outils, c.jamais.recitation, c.ecoute.actif]).toEqual(
            [false, false, false, false, false, false, false],
        );
        expect(c.jamais.mots).toBe(12);
        expect(c.ecoute.sensibilite).toBe("normale");
        expect(c.urgence.transfert).toBe(true);
        expect(c.marquer).toBe(true);
    });

    it("montre la phrase d'une consigne seulement une fois allumée, et enregistre la clé complète", async () => {
        const onSave = monter();
        expect(document.getElementById("securite-manipulation-phrase")).toBeNull();
        fireEvent.click(document.getElementById("securite-manipulation") as HTMLElement);
        fireEvent.change(document.getElementById("securite-manipulation-phrase") as HTMLInputElement, { target: { value: "Je reste dans mon rôle." } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer Sécurité/ }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const envoye = (onSave.mock.calls[0][0] as WorkflowConfigurations).securite_conversation;
        expect(envoye?.manipulation).toEqual({ actif: true, phrase: "Je reste dans mon rôle." });
        expect(envoye?.jamais).toEqual({ outils: false, recitation: false, mots: 12, phrase: "" });
        expect(envoye?.ecoute?.actif).toBe(false);
    });

    it("dit et bloque une valeur de mots hors des bornes du serveur", () => {
        expect(erreurMots(5)).not.toBeNull();
        expect(erreurMots(61)).not.toBeNull();
        expect(erreurMots(6)).toBeNull();
        monter({ jamais: { recitation: true, mots: 12 } });
        fireEvent.change(document.getElementById("securite-mots") as HTMLInputElement, { target: { value: "3" } });
        expect(screen.getByRole("alert").textContent).toMatch(/Entre 6 et 60/);
        expect((screen.getByRole("button", { name: /Enregistrer Sécurité/ }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("n'affiche les réglages du classifieur qu'une fois l'écoute allumée", () => {
        monter();
        expect(document.getElementById("securite-sensibilite")).toBeNull();
        fireEvent.click(document.getElementById("securite-ecoute") as HTMLElement);
        expect(document.getElementById("securite-sensibilite")).not.toBeNull();
        expect(document.getElementById("securite-consigne")).not.toBeNull();
    });

    it("garde-fou urgence : éteint par défaut, numéro et mots seulement une fois allumé, enregistré dans la clé", async () => {
        const onSave = monter();
        expect(completerSecurite(undefined).garde_urgence).toEqual({ actif: false, numero: "112", mots_en_plus: [] });
        expect(document.getElementById("securite-garde-urgence-numero")).toBeNull();
        fireEvent.click(document.getElementById("securite-garde-urgence") as HTMLElement);
        fireEvent.change(document.getElementById("securite-garde-urgence-numero") as HTMLInputElement, { target: { value: "15" } });
        fireEvent.change(document.getElementById("securite-garde-urgence-mots") as HTMLInputElement, { target: { value: "chèvre, brebis" } });
        fireEvent.click(screen.getByRole("button", { name: /Enregistrer Sécurité/ }));
        await waitFor(() => expect(onSave).toHaveBeenCalled());
        const envoye = (onSave.mock.calls[0][0] as WorkflowConfigurations).securite_conversation;
        expect(envoye?.garde_urgence).toEqual({ actif: true, numero: "15", mots_en_plus: ["chèvre", "brebis"] });
    });

    it("garde-fou urgence : un numéro que le serveur refuserait est dit sous le champ et bloque l'enregistrement", () => {
        monter({ garde_urgence: { actif: true, numero: "112" } });
        fireEvent.change(document.getElementById("securite-garde-urgence-numero") as HTMLInputElement, { target: { value: "abc" } });
        expect(screen.getByRole("alert").textContent).toMatch(/Des chiffres seulement/);
        expect((screen.getByRole("button", { name: /Enregistrer Sécurité/ }) as HTMLButtonElement).disabled).toBe(true);
    });
});
