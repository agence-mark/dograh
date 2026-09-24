/**
 * [.mark] The "Call Record" card (plan fiche au fil de l'eau, lot 5).
 *
 * What these tests hold: the switch is OFF by default, the fields are edited in
 * a dialog (a long list is never shown in one block), a name the server would
 * refuse locks the Save button before the server has to, and what is typed is
 * what leaves in the save. That the card is MOUNTED on the page is asserted in
 * `section-reglages-pipecat-montee.test.tsx`, with the other cards.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveWorkflowConfigurations } from "@/types/workflow-configurations";

import {
    erreursDesChamps,
    lecteurParDefaut,
    NOMBRE_MAX_CHAMPS,
    NOMS_RESERVES,
    SectionFiche,
} from "./SectionFiche";

const toastMock = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toastMock }));

vi.mock("@/context/UnsavedChangesContext", () => ({
    useUnsavedChanges: () => undefined,
}));

vi.stubGlobal(
    "ResizeObserver",
    class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
);

beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.error.mockClear();
});

const CHAMPS = [
    { nom: "nom", type: "string", origine: "dicte", description: "Nom de famille", lecteur: null },
    { nom: "commune", type: "string", origine: "dicte", description: "", lecteur: null },
];

const ouvrir = (
    configurations: Record<string, unknown> | null,
    onSave = vi.fn().mockResolvedValue(undefined),
) => {
    render(
        <SectionFiche
            workflowConfigurations={resolveWorkflowConfigurations(configurations as never)}
            workflowName="Agent de test"
            onSave={onSave}
        />,
    );
    return onSave;
};

const interrupteur = () => document.getElementById("fiche_au_fil_de_leau") as HTMLElement;
const boutonEnregistrer = () =>
    screen.getByRole("button", { name: /save call record/i }) as HTMLButtonElement;
const ouvrirLesChamps = () => fireEvent.click(screen.getByRole("button", { name: /edit fields/i }));

describe("[.mark] Call Record card", () => {
    it("is OFF by default, with no field and the Save button asleep", () => {
        ouvrir(null);
        expect(interrupteur().getAttribute("aria-checked")).toBe("false");
        expect(document.getElementById("fiche_nombre_de_champs")?.textContent).toBe("0");
        expect(boutonEnregistrer().disabled).toBe(true);
    });

    it("shows a saved record: switch on, fields counted, not listed on the card", () => {
        ouvrir({ fiche_au_fil_de_leau: true, fiche_champs: CHAMPS });
        expect(interrupteur().getAttribute("aria-checked")).toBe("true");
        expect(document.getElementById("fiche_nombre_de_champs")?.textContent).toBe("2");
        // The list lives in the dialog, never on the card itself.
        expect(document.getElementById("fiche_nom_0")).toBeNull();
    });

    it("warns when the switch is on with no field: the tool would not be offered", () => {
        ouvrir(null);
        fireEvent.click(interrupteur());
        expect(screen.getByText(/no field: the tool will not be offered/i)).toBeTruthy();
    });

    it("edits the fields in a dialog and carries them out on save", async () => {
        const onSave = ouvrir({ fiche_champs: CHAMPS });
        fireEvent.click(interrupteur());
        ouvrirLesChamps();
        const dialogue = await screen.findByRole("dialog");
        fireEvent.click(within(dialogue).getByRole("button", { name: /add field/i }));
        fireEvent.change(document.getElementById("fiche_nom_2") as HTMLInputElement, {
            target: { value: "adresse_intervention" },
        });
        fireEvent.change(document.getElementById("fiche_description_2") as HTMLInputElement, {
            target: { value: "Numéro et rue" },
        });
        fireEvent.click(within(dialogue).getByRole("button", { name: /done/i }));
        fireEvent.click(boutonEnregistrer());
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        const enregistre = onSave.mock.calls[0][0];
        expect(enregistre.fiche_au_fil_de_leau).toBe(true);
        expect(enregistre.fiche_champs).toHaveLength(3);
        expect(enregistre.fiche_champs[2]).toEqual({
            nom: "adresse_intervention",
            type: "string",
            origine: "dicte",
            description: "Numéro et rue",
            lecteur: null,
        });
        expect(toastMock.success).toHaveBeenCalled();
    });

    it("removes a field", async () => {
        const onSave = ouvrir({ fiche_champs: CHAMPS });
        ouvrirLesChamps();
        const dialogue = await screen.findByRole("dialog");
        fireEvent.click(within(dialogue).getByRole("button", { name: /remove field nom/i }));
        fireEvent.click(within(dialogue).getByRole("button", { name: /done/i }));
        fireEvent.click(boutonEnregistrer());
        await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
        expect(onSave.mock.calls[0][0].fiche_champs.map((c: { nom: string }) => c.nom)).toEqual([
            "commune",
        ]);
    });

    it("locks the Save button on a name the server would refuse, and says why", async () => {
        ouvrir({ fiche_champs: CHAMPS });
        ouvrirLesChamps();
        const dialogue = await screen.findByRole("dialog");
        fireEvent.change(document.getElementById("fiche_nom_0") as HTMLInputElement, {
            target: { value: "commune" },
        });
        expect(within(dialogue).getByText(/used twice/i)).toBeTruthy();
        fireEvent.click(within(dialogue).getByRole("button", { name: /done/i }));
        expect(boutonEnregistrer().disabled).toBe(true);
        expect(screen.getByText(/1 field has a problem/i)).toBeTruthy();
    });

    it("follows the record the page hands back after a save, and is no longer dirty", async () => {
        // The defect of 24/09: the server filled the empty reader in, the card
        // compared it with what it had sent and kept "Unsaved changes" forever,
        // which blocked leaving the page.
        const onSave = vi.fn().mockResolvedValue(undefined);
        const configuration = { fiche_au_fil_de_leau: true, fiche_champs: CHAMPS };
        const { rerender } = render(
            <SectionFiche
                workflowConfigurations={resolveWorkflowConfigurations(null)}
                workflowName="Agent de test"
                onSave={onSave}
            />,
        );
        rerender(
            <SectionFiche
                workflowConfigurations={resolveWorkflowConfigurations(configuration as never)}
                workflowName="Agent de test"
                onSave={onSave}
            />,
        );
        // The page hands the card the saved configuration after a save; the
        // card's own state must then match it.
        expect(screen.queryByText(/unsaved changes/i)).toBeNull();
    });

    it("shows the server's refusal under the card, not only in a toast", async () => {
        ouvrir({ fiche_champs: CHAMPS }, vi.fn().mockRejectedValue(new Error("fiche field name 'x' is reserved")));
        fireEvent.click(interrupteur());
        fireEvent.click(boutonEnregistrer());
        expect(await screen.findByRole("alert")).toBeTruthy();
        expect(toastMock.error).toHaveBeenCalled();
    });
});

describe("[.mark] Call Record rules mirror the server", () => {
    const serveur = (fichier: string) =>
        readFileSync(join(__dirname, "../../../../api/schemas", fichier), "utf8");

    it("caps the fields where the server does", () => {
        const bloc = serveur("workflow_configurations.py").split("fiche_champs: list[ChampFiche]")[1];
        expect(bloc).toBeDefined();
        expect(Number(/max_length=(\d+)/.exec(bloc)?.[1])).toBe(NOMBRE_MAX_CHAMPS);
    });

    it("refuses the same reserved names as the server", () => {
        const bloc = serveur("fiche_agent.py").split("NOMS_RESERVES = frozenset(")[1].split(/\r?\n\)/)[0];
        // Comments carry backticked names too: only the quoted strings count.
        const duServeur = [...bloc.matchAll(/^\s*"([a-z_]+)",/gm)].map((m) => m[1]).sort();
        expect([...NOMS_RESERVES].sort()).toEqual(duServeur);
    });

    it.each([
        ["commune", "commune"],
        ["commune_chantier", "commune"],
        ["adresse_intervention", "rue"],
        ["rue", "rue"],
        ["nom", "aucun"],
    ])("reader from the name: %s -> %s", (nom, lecteur) => {
        expect(lecteurParDefaut(nom)).toBe(lecteur);
    });

    it("refuses bad, reserved, duplicated and INSEE names", () => {
        const champ = (nom: string, lecteur: "commune" | "aucun" | null = null) => ({
            nom,
            type: "string" as const,
            origine: "dicte" as const,
            description: "",
            lecteur,
        });
        expect(erreursDesChamps([champ("Nom")])[0]).toMatch(/lowercase/i);
        expect(erreursDesChamps([champ("nodes_visited")])[0]).toMatch(/agent itself/i);
        expect(erreursDesChamps([champ("nom"), champ("nom")])[1]).toMatch(/twice/i);
        expect(erreursDesChamps([champ("commune"), champ("commune_insee", "aucun")])[1]).toMatch(/INSEE/);
        expect(erreursDesChamps([champ("nom"), champ("commune")])).toEqual({});
    });
});
