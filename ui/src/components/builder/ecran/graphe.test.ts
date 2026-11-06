import { describe, expect, it } from "vitest";

import type { FlowEdge, FlowNode } from "@/components/flow/types";

import {
    appliquerLesOperations,
    comparer,
    grapheAAfficher,
    type GrapheDuBuilder,
    type LiaisonAffichee,
    type NoeudAffiche,
    type OperationDuBuilder,
    resumer,
    retirerLeSurlignage,
} from "./graphe";

const noeud = (id: string, data: Record<string, unknown> = {}, y = 0): FlowNode =>
    ({ id, type: "agentNode", position: { x: 0, y }, data: { name: `n${id}`, prompt: `p${id}`, ...data } }) as unknown as FlowNode;
const liaison = (id: string, source: string, target: string, data: Record<string, unknown> = {}): FlowEdge =>
    ({ id, source, target, data: { label: "l", condition: "c", ...data } }) as unknown as FlowEdge;

const DEPART: GrapheDuBuilder = {
    nodes: [noeud("1", {}, 0), noeud("2", {}, 180)],
    edges: [liaison("1-2", "1", "2")],
};
const TEXTES = { champs: (n: number) => `${n} champs` };

describe("appliquer les opérations (miroir du serveur)", () => {
    it("ajoute un nœud sous les autres et une liaison, sans toucher au graphe d'origine", () => {
        const ops: OperationDuBuilder[] = [
            { op: "ajouter_noeud", id: "3", type: "endCall", nom: "Fin", prompt: "Au revoir" },
            { op: "ajouter_liaison", source: "2", target: "3", label: "Fini", condition: "Terminé" },
        ];
        const suite = appliquerLesOperations(DEPART, ops);
        expect(suite.nodes.map((n) => n.id)).toEqual(["1", "2", "3"]);
        expect(suite.nodes[2].position.y).toBeGreaterThan(180);
        expect(suite.edges.map((e) => e.id)).toEqual(["1-2", "2-3"]);
        expect(DEPART.nodes).toHaveLength(2); // l'original est intact
    });

    it("ignore une opération que le serveur refuserait", () => {
        const suite = appliquerLesOperations(DEPART, [
            { op: "ajouter_noeud", id: "1", type: "endCall", nom: "Doublon" },
            { op: "ajouter_liaison", source: "1", target: "9", label: "x", condition: "y" },
            { op: "modifier_prompt", id: "9", prompt: "z" },
            { op: "ajouter_noeud", nom: "Sans type" },
        ]);
        expect(suite.nodes).toHaveLength(2);
        expect(suite.edges).toHaveLength(1);
    });

    it("supprimer un nœud supprime ses liaisons", () => {
        const suite = appliquerLesOperations(DEPART, [{ op: "supprimer_noeud", id: "2" }]);
        expect(suite.nodes.map((n) => n.id)).toEqual(["1"]);
        expect(suite.edges).toEqual([]);
    });

    it("modifie un prompt, un nom et une liaison", () => {
        const suite = appliquerLesOperations(DEPART, [
            { op: "modifier_prompt", id: "1", prompt: "neuf" },
            { op: "modifier_noeud", id: "2", nom: "Renommé" },
            { op: "modifier_liaison", id: "1-2", label: "Autre" },
        ]);
        expect(suite.nodes[0].data.prompt).toBe("neuf");
        expect(suite.nodes[1].data.name).toBe("Renommé");
        expect((suite.edges[0].data as unknown as { label: string }).label).toBe("Autre");
    });
});

describe("comparer avant et après", () => {
    const apres = appliquerLesOperations(DEPART, [
        { op: "ajouter_noeud", id: "3", type: "endCall", nom: "Fin" },
        { op: "modifier_prompt", id: "1", prompt: "neuf" },
        { op: "supprimer_noeud", id: "2" },
        { op: "ajouter_liaison", source: "1", target: "3", label: "a", condition: "b" },
    ]);

    it("classe nouveau, modifié, supprimé et nomme les champs modifiés", () => {
        const c = comparer(DEPART, apres);
        expect(c.noeuds["3"]).toEqual({ etat: "nouveau", champs: [] });
        expect(c.noeuds["1"]).toEqual({ etat: "modifie", champs: ["prompt"] });
        expect(c.noeuds["2"]).toEqual({ etat: "supprime", champs: [] });
        expect(c.liaisons["1-2"].etat).toBe("supprime");
        expect(c.liaisons["1-3"].etat).toBe("nouveau");
        expect(resumer(c)).toMatchObject({ noeudsCrees: 1, noeudsModifies: 1, noeudsSupprimes: 1, liaisonsCreees: 1, liaisonsSupprimees: 1, total: 5 });
    });

    it("ne compte pas ce que l'éditeur ajoute pour lui (sélection, validation)", () => {
        const sali: GrapheDuBuilder = { nodes: [noeud("1", { selected: true, invalid: true, validationMessage: "x" }), noeud("2")], edges: DEPART.edges };
        expect(comparer(DEPART, sali).noeuds).toEqual({});
    });

    it("deux graphes identiques ne montrent aucun changement", () => {
        expect(resumer(comparer(DEPART, DEPART)).total).toBe(0);
    });
});

describe("le graphe à afficher", () => {
    const apres = appliquerLesOperations(DEPART, [
        { op: "ajouter_noeud", id: "3", type: "endCall", nom: "Fin" },
        { op: "modifier_prompt", id: "1", prompt: "neuf" },
        { op: "supprimer_noeud", id: "2" },
    ]);

    it("après : vert pour le nouveau, orange avec le nombre de champs pour le modifié, rouge barré pour le supprimé gardé à l'écran", () => {
        const g = grapheAAfficher(DEPART, apres, "apres", TEXTES);
        const par = Object.fromEntries((g.nodes as NoeudAffiche[]).map((n) => [n.id, n]));
        expect(par["3"].className).toContain("ring-(--signal-ok)");
        expect(par["1"].className).toContain("ring-(--signal-warn)");
        expect(par["1"].domAttributes!["data-builder-badge"]).toBe("1 champs");
        expect(par["2"].className).toContain("ring-(--signal-danger)");
        expect(par["2"].className).toContain("line-through");
        const liaisonSupprimee = (g.edges as LiaisonAffichee[]).find((e) => e.id === "1-2");
        expect(liaisonSupprimee?.style?.strokeDasharray).toBe("6 4");
    });

    it("avant : le graphe tel qu'il était, sans surlignage", () => {
        const g = grapheAAfficher(DEPART, apres, "avant", TEXTES);
        expect(g).toBe(DEPART);
        expect((g.nodes as NoeudAffiche[]).every((n) => !n.className)).toBe(true);
    });

    it("un nœud inchangé garde son objet : pas de rendu inutile", () => {
        const g = grapheAAfficher(DEPART, apres, "apres", TEXTES);
        expect(g.nodes.find((n) => n.id === "1")).not.toBe(apres.nodes.find((n) => n.id === "1")); // modifié : enveloppé
        const intact = appliquerLesOperations(DEPART, [{ op: "ajouter_noeud", id: "3", type: "endCall", nom: "Fin" }]);
        const g2 = grapheAAfficher(DEPART, intact, "apres", TEXTES);
        expect(g2.nodes.find((n) => n.id === "1")).toBe(intact.nodes.find((n) => n.id === "1"));
    });
});

describe("ce que l'éditeur garde", () => {
    it("retire la classe et les attributs du surlignage, pas le reste du nœud", () => {
        const surligne = { ...noeud("1", { prompt: "p" }), className: "ring-2 ring-(--signal-ok)", domAttributes: { "data-builder-badge": "1 champ" } } as unknown as FlowNode;
        const propre = retirerLeSurlignage(surligne) as unknown as Record<string, unknown>;
        expect(propre.className).toBeUndefined();
        expect(propre.domAttributes).toBeUndefined();
        expect(propre.id).toBe("1");
        expect((propre.data as { prompt: string }).prompt).toBe("p");
    });

    it("le graphe affiché n'enveloppe jamais les nœuds du graphe d'origine (rien à nettoyer côté éditeur)", () => {
        const apres = appliquerLesOperations(DEPART, [{ op: "modifier_prompt", id: "1", prompt: "neuf" }]);
        grapheAAfficher(DEPART, apres, "apres", TEXTES);
        expect((apres.nodes[0] as unknown as { className?: string }).className).toBeUndefined();
    });
});
