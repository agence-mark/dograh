/**
 * [.mark] Plays a reference case on whatever the settings page renders, and
 * turns what the save functions received into a comparable record.
 *
 * Shared by the step-1 test (the OLD cards) and the step-4 test (the themes):
 * the gestures and the record are the same code, so two records can only
 * differ because the screens differ.
 */
import { fireEvent, screen } from "@testing-library/react";
import type { Mock } from "vitest";

import type { Geste } from "./cas-agent";

export const element = (id: string): HTMLElement => {
    const trouve = document.getElementById(id);
    if (!trouve) throw new Error(`No element with id "${id}" on screen.`);
    return trouve;
};

export const jouerGeste = (geste: Geste) => {
    switch (geste.type) {
        case "interrupteur":
            fireEvent.click(element(geste.id));
            return;
        case "saisir": {
            const cible = geste.id
                ? element(geste.id)
                : geste.libelle
                  ? screen.getByLabelText(geste.libelle)
                  : screen.getByPlaceholderText(geste.indication ?? "");
            fireEvent.change(cible, { target: { value: geste.valeur } });
            return;
        }
        case "choisir":
            fireEvent.change(element(geste.id), { target: { value: geste.valeur } });
            return;
        case "etiquette": {
            const champ = element(geste.id);
            fireEvent.change(champ, { target: { value: geste.valeur } });
            fireEvent.keyDown(champ, { key: "Enter" });
            return;
        }
        case "cliquer":
            fireEvent.click(screen.getByRole("button", { name: geste.nom }));
            return;
        case "radio":
            fireEvent.click(screen.getByRole("radio", { name: geste.nom }));
            return;
    }
};

/** What the network would carry: `undefined` dropped, dates as strings. */
export const commeEnvoye = <T,>(valeur: T): T =>
    valeur === undefined ? valeur : (JSON.parse(JSON.stringify(valeur)) as T);

/** The keys of `charge` that differ from `base`, and the keys it dropped. */
export const difference = (
    base: Record<string, unknown>,
    charge: Record<string, unknown>,
) => {
    const modifiees: Record<string, unknown> = {};
    const retirees: string[] = [];
    for (const cle of new Set([...Object.keys(base), ...Object.keys(charge)])) {
        if (!(cle in charge)) {
            retirees.push(cle);
        } else if (JSON.stringify(base[cle]) !== JSON.stringify(charge[cle])) {
            modifiees[cle] = charge[cle];
        }
    }
    return { modifiees, retirees: retirees.sort() };
};

export interface Enregistreurs {
    saveWorkflowConfigurations: Mock;
    saveTemplateContextVariables: Mock;
    saveDictionary: Mock;
}

export type Appel =
    | { fonction: "saveWorkflowConfigurations"; nom: string; modifiees: Record<string, unknown>; retirees: string[] }
    | { fonction: "saveTemplateContextVariables"; variables: unknown }
    | { fonction: "saveDictionary"; dictionnaire: unknown };

/** Every save call, in the order the functions were first called. */
export const relever = (
    enregistreurs: Enregistreurs,
    base: Record<string, unknown>,
): Appel[] => {
    const appels: Array<{ ordre: number; appel: Appel }> = [];
    enregistreurs.saveWorkflowConfigurations.mock.calls.forEach((args, i) => {
        const { modifiees, retirees } = difference(base, commeEnvoye(args[0]) as Record<string, unknown>);
        appels.push({
            ordre: enregistreurs.saveWorkflowConfigurations.mock.invocationCallOrder[i],
            appel: { fonction: "saveWorkflowConfigurations", nom: args[1], modifiees, retirees },
        });
    });
    enregistreurs.saveTemplateContextVariables.mock.calls.forEach((args, i) => {
        appels.push({
            ordre: enregistreurs.saveTemplateContextVariables.mock.invocationCallOrder[i],
            appel: { fonction: "saveTemplateContextVariables", variables: commeEnvoye(args[0]) },
        });
    });
    enregistreurs.saveDictionary.mock.calls.forEach((args, i) => {
        appels.push({
            ordre: enregistreurs.saveDictionary.mock.invocationCallOrder[i],
            appel: { fonction: "saveDictionary", dictionnaire: commeEnvoye(args[0]) },
        });
    });
    return appels.sort((a, b) => a.ordre - b.ordre).map((a) => a.appel);
};
