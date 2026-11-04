/**
 * [.mark] R3 mineur 4 : « Télécharger (JSON) » retire les champs de secret des nœuds, sans toucher au reste.
 */
import { describe, expect, it } from "vitest";

import { definitionSansSecrets } from "./definition-sans-secrets";

describe("definitionSansSecrets", () => {
    const definition = {
        nodes: [
            { id: "1", type: "qa", data: { name: "QA", qa_model: "m", qa_api_key: "valeur-factice-a-retirer" } },
            { id: "2", type: "agentNode", data: { name: "Accueil", prompt: "Bonjour" } },
        ],
        edges: [{ id: "e1" }],
    };

    it("retire la clé du nœud d'analyse et garde tout le reste", () => {
        const propre = definitionSansSecrets(definition);
        expect(propre.nodes[0].data).toEqual({ name: "QA", qa_model: "m" });
        expect(propre.nodes[1].data).toEqual({ name: "Accueil", prompt: "Bonjour" });
        expect(propre.edges).toEqual([{ id: "e1" }]);
    });

    it("ne modifie pas la définition de l'éditeur", () => {
        definitionSansSecrets(definition);
        expect(definition.nodes[0].data.qa_api_key).toBe("valeur-factice-a-retirer");
    });
});
