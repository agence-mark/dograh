/**
 * [.mark] A theme saves its parts in an order that never loses a rename
 * (review of 26/09, B1).
 *
 * Dograh's variables save sends the agent's name as it was at the last render
 * (`useWorkflowState`, `saveTemplateContextVariables`), and the server writes
 * any name it receives. Renaming the agent and adding a variable, then one
 * click on « Save Agent », must leave the NEW name on the server.
 */
import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import { useEnregistrementTheme } from "./enregistrement";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe("[.mark] the order of a theme's saves", () => {
    it("keeps the new name when the name and the variables are saved together", async () => {
        const serveur = { nom: "Ancien nom", ordre: [] as string[] };
        const nomAuDernierRendu = "Ancien nom";
        // Like Dograh's: the name it sends is the one it closed over.
        const enregistrerVariables = vi.fn(async () => {
            serveur.ordre.push("variables");
            serveur.nom = nomAuDernierRendu;
        });
        const onSave = vi.fn(async (_config: unknown, nom: string) => {
            serveur.ordre.push("configuration");
            serveur.nom = nom;
        });

        const { result } = renderHook(() =>
            useEnregistrementTheme({
                titre: { en: "Agent", fr: "Agent" },
                resolue: resolveWorkflowConfigurations({} as never),
                workflowName: nomAuDernierRendu,
                onSave,
                parties: [
                    { nom: { en: "Name", fr: "Nom" }, modifie: true, nomAgent: () => "Nouveau nom" },
                    { nom: { en: "Variables", fr: "Variables" }, modifie: true, enregistrerAutrement: enregistrerVariables },
                ],
            }),
        );
        await act(() => result.current.enregistrer());

        expect(serveur.ordre).toEqual(["variables", "configuration"]);
        expect(serveur.nom).toBe("Nouveau nom");
    });
});
