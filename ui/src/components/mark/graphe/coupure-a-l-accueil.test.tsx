/**
 * [.mark] Clôture, SA-3 (D14) : « Couper l'agent à l'accueil » sur la fenêtre de l'étape de départ.
 *
 * Questions : les quatre réglages de l'agent se lisent-ils (valeurs d'avant par défaut) ? Ce qui est saisi est-il exactement ce
 * qui part, par les réglages de l'agent ? Une faute de frappe bloque-t-elle ? La note « sans effet » se dit-elle ? Rien n'est
 * montré sans le contexte de l'agent, et une version passée est en lecture seule.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FournisseurLangue } from "../langue/langue";

const m = vi.hoisted(() => ({ ctx: { reglagesDeLAgent: undefined as unknown, readOnly: false }, succes: vi.fn(), echec: vi.fn() }));
vi.mock("@/app/workflow/[workflowId]/contexts/WorkflowContext", () => ({ useWorkflow: () => m.ctx }));
vi.mock("../notifications", () => ({ notifier: { succes: m.succes, echec: m.echec } }));

const { CoupureALAccueil } = await import("./CoupureALAccueil");

afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    m.ctx = { reglagesDeLAgent: undefined, readOnly: false };
});

const monter = (configuration: Record<string, unknown>, enregistrer = vi.fn(async (_partie: Record<string, unknown>) => undefined), readOnly = false) => {
    m.ctx = { reglagesDeLAgent: { configuration, enregistrer }, readOnly };
    render(
        <FournisseurLangue>
            <CoupureALAccueil />
        </FournisseurLangue>,
    );
    return enregistrer;
};
const bouton = () => screen.getByRole("button", { name: /^(Save|Enregistrer)$/ }) as HTMLButtonElement;

describe("coupure à l'accueil sur l'étape de départ", () => {
    it("ne montre rien sans le contexte des réglages de l'agent", () => {
        render(
            <FournisseurLangue>
                <CoupureALAccueil />
            </FournisseurLangue>,
        );
        expect(document.querySelector("[data-bloc='coupure-a-l-accueil']")).toBeNull();
    });

    it("lit les valeurs d'avant et envoie exactement ce qui est saisi, avec la notification", async () => {
        const enregistrer = monter({});
        expect(document.querySelector("[data-bloc='coupure-a-l-accueil']")).not.toBeNull();
        expect(bouton().disabled).toBe(true);
        expect((document.getElementById("accueil_interruptible") as HTMLElement).getAttribute("aria-checked")).toBe("false");
        fireEvent.click(document.getElementById("accueil_interruptible") as HTMLElement);
        fireEvent.click(bouton());
        await waitFor(() => expect(enregistrer).toHaveBeenCalledTimes(1));
        expect(enregistrer.mock.calls[0][0]).toEqual({
            mute_until_first_bot_complete: true,
            accueil_interruptible: true,
            accueil_mots_minimum: 2,
            mute_first_speech: false,
        });
        await waitFor(() => expect(m.succes).toHaveBeenCalled());
    });

    it("dit l'échec par une notification et garde la saisie", async () => {
        const enregistrer = vi.fn(async (_partie: Record<string, unknown>) => {
            throw new Error("protégée");
        });
        monter({}, enregistrer);
        fireEvent.click(document.getElementById("mute_first_speech") as HTMLElement);
        fireEvent.click(bouton());
        await waitFor(() => expect(m.echec).toHaveBeenCalled());
        expect((document.getElementById("mute_first_speech") as HTMLElement).getAttribute("aria-checked")).toBe("true");
    });

    it("bloque une faute de frappe sur le nombre de mots (1 à 10)", () => {
        monter({ accueil_interruptible: true });
        fireEvent.change(document.getElementById("accueil_mots_minimum") as HTMLInputElement, { target: { value: "99" } });
        expect(bouton().disabled).toBe(true);
        expect(screen.getByRole("alert")).toBeTruthy();
    });

    it("dit « sans effet » quand « ne jamais couper » de l'agent l'emporte", () => {
        monter({ accueil_interruptible: true, mute_always: true });
        expect(document.querySelector("[data-note='accueil-annule']")?.textContent).toMatch(/Sans effet|No effect/);
    });

    it("une version passée est en lecture seule", () => {
        monter({}, vi.fn(async (_partie: Record<string, unknown>) => undefined), true);
        expect(bouton().disabled).toBe(true);
        expect((document.getElementById("accueil_interruptible") as HTMLButtonElement).disabled).toBe(true);
    });
});
