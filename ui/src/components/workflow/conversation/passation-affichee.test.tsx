/**
 * [.mark] Chantier agents-specialises, lot 12 : au clavier et à l'essai, la passation à un autre agent
 * se lit dans la conversation : « Passé à l'agent X › étape » (le texte anglais « Handed over to » est
 * traduit par le dictionnaire des écrans d'origine). Le moteur du clavier met l'agent dans l'événement
 * de changement d'étape (``payload.agent``, lot 2) ; l'adaptateur le porte jusqu'au marqueur.
 *
 * Ce test lit le dictionnaire pour que le texte français que voit l'utilisateur soit celui du plan.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import dictionnaire from "@/components/mark/langue/dictionnaire-dograh.json";

import { conversationItemsFromTextChatTurns } from "./adapters/fromTextChatTurns";
import { NodeTransitionMarker } from "./NodeTransitionMarker";

afterEach(cleanup);

describe("[.mark] « Passé à l'agent X » dans la conversation du clavier", () => {
    it("montre l'agent qui prend la main, puis l'étape où il arrive", () => {
        render(<NodeTransitionMarker nodeName="Qualification" agentName="Spécialisé un" />);
        const texte = document.body.textContent ?? "";
        expect(texte).toContain("Handed over to");
        expect(texte).toContain("Spécialisé un");
        expect(texte.indexOf("Spécialisé un")).toBeLessThan(texte.indexOf("Qualification"));
        expect(screen.getByText("Qualification")).toBeTruthy();
    });

    it("n'ajoute rien à un simple changement d'étape (un agent seul garde son marqueur)", () => {
        render(<NodeTransitionMarker nodeName="Coordonnées" />);
        expect(document.body.textContent).not.toContain("Handed over to");
    });

    it("se traduit « Passé à l'agent » par le dictionnaire", () => {
        expect((dictionnaire as Record<string, string>)["Handed over to"]).toBe("Passé à l'agent");
    });

    it("l'adaptateur du clavier porte l'agent de l'événement jusqu'au marqueur", () => {
        const items = conversationItemsFromTextChatTurns([
            {
                id: "t1",
                status: "completed",
                created_at: "2026-10-16T08:00:00Z",
                events: [
                    {
                        type: "node_transition",
                        created_at: "2026-10-16T08:00:01Z",
                        payload: { node_id: "2", node_name: "Qualification", previous_node_id: "9", previous_node_name: "Accueil", agent: "Spécialisé un" },
                    },
                    {
                        type: "node_transition",
                        created_at: "2026-10-16T08:00:02Z",
                        payload: { node_id: "3", node_name: "Coordonnées", previous_node_id: "2", previous_node_name: "Qualification" },
                    },
                ],
            },
        ]);
        const marqueurs = items.filter((i) => i.kind === "node-transition") as Array<{ nodeName: string; agentName?: string }>;
        expect(marqueurs.map((i) => [i.nodeName, i.agentName])).toEqual([
            ["Qualification", "Spécialisé un"],
            ["Coordonnées", undefined],
        ]);
    });
});
