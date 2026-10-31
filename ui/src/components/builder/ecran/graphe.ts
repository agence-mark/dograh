/**
 * [.mark] builder-agent-vocal (lot 4): the graph while the builder works on a draft.
 *
 * Three jobs, all pure (no React):
 *  - apply the builder's construction operations to a graph, one by one, so the canvas draws them live (Vercel's
 *    "operations" method, plan Q8); this MIRRORS `api/services/builder/brouillon.py` (the server stays the judge:
 *    nothing is saved from here);
 *  - compare the graph before and after: new, modified, removed nodes and edges, and which fields changed
 *    (Sim's highlighting, Apache 2.0: the idea of colouring a diff on the canvas, written afresh here);
 *  - give the canvas the graph to show: "after" (with removed items kept, struck through) or "before".
 */
import type { FlowEdge, FlowNode } from "@/components/flow/types";

export interface OperationDuBuilder {
    op:
        | "ajouter_noeud"
        | "modifier_noeud"
        | "modifier_prompt"
        | "supprimer_noeud"
        | "ajouter_liaison"
        | "modifier_liaison"
        | "supprimer_liaison";
    id?: string | null;
    type?: string | null;
    nom?: string | null;
    prompt?: string | null;
    donnees?: Record<string, unknown> | null;
    source?: string | null;
    target?: string | null;
    label?: string | null;
    condition?: string | null;
}

/** What the canvas adds to a node or an edge to draw a change (React Flow reads these; the editor's types do not list them). */
export type NoeudAffiche = FlowNode & { className?: string; domAttributes?: Record<string, string>; draggable?: boolean; selectable?: boolean };
export type LiaisonAffichee = FlowEdge & { style?: Record<string, string | number>; sourceHandle?: string | null; targetHandle?: string | null };

export interface GrapheDuBuilder {
    nodes: FlowNode[];
    edges: FlowEdge[];
}

export type EtatDuChangement = "nouveau" | "modifie" | "supprime";
export type Bascule = "apres" | "avant";

export interface ChangementDElement {
    etat: EtatDuChangement;
    /** The fields whose value changed (modified items only). */
    champs: string[];
}

export interface Comparaison {
    noeuds: Record<string, ChangementDElement>;
    liaisons: Record<string, ChangementDElement>;
}

export interface Resume {
    noeudsCrees: number;
    noeudsModifies: number;
    noeudsSupprimes: number;
    liaisonsCreees: number;
    liaisonsModifiees: number;
    liaisonsSupprimees: number;
    total: number;
}

// What React Flow or the editor adds for its own use: not a change of the agent.
const CHAMPS_VISUELS = new Set([
    "selected",
    "dragging",
    "invalid",
    "validationMessage",
    "selected_through_edge",
    "hovered_through_edge",
    "runtime_active",
]);

const ESPACE_ENTRE_NOEUDS = 180;
const X_PAR_DEFAUT = 175;

function copie<T>(valeur: T): T {
    return JSON.parse(JSON.stringify(valeur)) as T;
}

function plusBas(noeuds: FlowNode[]): number {
    return noeuds.reduce((max, n) => Math.max(max, n.position?.y ?? 0), -ESPACE_ENTRE_NOEUDS);
}

function identifiantLibre(noeuds: FlowNode[]): string {
    const pris = new Set(noeuds.map((n) => n.id));
    let n = pris.size + 1;
    while (pris.has(String(n))) n += 1;
    return String(n);
}

/** Applies ONE operation to `graphe` (modified in place). An invalid operation is ignored, as the server would refuse it. */
export function appliquerUneOperation(graphe: GrapheDuBuilder, op: OperationDuBuilder): void {
    const trouver = (id?: string | null) => graphe.nodes.find((n) => n.id === id);
    switch (op.op) {
        case "ajouter_noeud": {
            if (!op.type || !op.nom) return;
            const id = op.id ?? identifiantLibre(graphe.nodes);
            if (trouver(id)) return;
            const data: Record<string, unknown> = { name: op.nom, ...(op.donnees ?? {}) };
            if (op.prompt != null) data.prompt = op.prompt;
            graphe.nodes.push({
                id,
                type: op.type,
                position: { x: X_PAR_DEFAUT, y: plusBas(graphe.nodes) + ESPACE_ENTRE_NOEUDS },
                data,
            } as unknown as FlowNode);
            return;
        }
        case "modifier_noeud": {
            const noeud = trouver(op.id);
            if (!noeud) return;
            const data: Record<string, unknown> = { ...(noeud.data as unknown as Record<string, unknown>), ...(op.donnees ?? {}) };
            if (op.nom != null) data.name = op.nom;
            if (op.prompt != null) data.prompt = op.prompt;
            noeud.data = data as unknown as FlowNode["data"];
            return;
        }
        case "modifier_prompt": {
            const noeud = trouver(op.id);
            if (!noeud || op.prompt == null) return;
            noeud.data = { ...noeud.data, prompt: op.prompt };
            return;
        }
        case "supprimer_noeud": {
            if (!trouver(op.id)) return;
            graphe.nodes = graphe.nodes.filter((n) => n.id !== op.id);
            graphe.edges = graphe.edges.filter((e) => e.source !== op.id && e.target !== op.id);
            return;
        }
        case "ajouter_liaison": {
            if (!(op.source && op.target && op.label && op.condition)) return;
            if (!trouver(op.source) || !trouver(op.target)) return;
            let id = op.id ?? `${op.source}-${op.target}`;
            while (graphe.edges.some((e) => e.id === id)) id += "'";
            graphe.edges.push({
                id,
                source: op.source,
                target: op.target,
                data: { label: op.label, condition: op.condition },
            } as unknown as FlowEdge);
            return;
        }
        case "modifier_liaison":
        case "supprimer_liaison": {
            const liaison = graphe.edges.find((e) => e.id === op.id);
            if (!liaison) return;
            if (op.op === "supprimer_liaison") {
                graphe.edges = graphe.edges.filter((e) => e !== liaison);
                return;
            }
            if (op.source && trouver(op.source)) liaison.source = op.source;
            if (op.target && trouver(op.target)) liaison.target = op.target;
            const data = { ...(liaison.data as unknown as Record<string, unknown>) };
            if (op.label != null) data.label = op.label;
            if (op.condition != null) data.condition = op.condition;
            liaison.data = data as unknown as FlowEdge["data"];
        }
    }
}

/** A copy of `graphe` with every operation applied in order. */
export function appliquerLesOperations(graphe: GrapheDuBuilder, operations: OperationDuBuilder[]): GrapheDuBuilder {
    const suite = copie(graphe);
    for (const op of operations) appliquerUneOperation(suite, op);
    return suite;
}

function champsDifferents(avant: unknown, apres: unknown): string[] {
    const a = (avant ?? {}) as Record<string, unknown>;
    const b = (apres ?? {}) as Record<string, unknown>;
    const noms = new Set([...Object.keys(a), ...Object.keys(b)]);
    const differents: string[] = [];
    for (const nom of noms) {
        if (CHAMPS_VISUELS.has(nom)) continue;
        if (JSON.stringify(a[nom] ?? null) !== JSON.stringify(b[nom] ?? null)) differents.push(nom);
    }
    return differents.sort();
}

function comparerLesElements<T extends { id: string; data?: unknown }>(avant: T[], apres: T[]): Record<string, ChangementDElement> {
    const sortie: Record<string, ChangementDElement> = {};
    const avantParId = new Map(avant.map((e) => [e.id, e]));
    const apresParId = new Map(apres.map((e) => [e.id, e]));
    for (const [id, element] of apresParId) {
        const ancien = avantParId.get(id);
        if (!ancien) {
            sortie[id] = { etat: "nouveau", champs: [] };
            continue;
        }
        let champs = champsDifferents(ancien.data, element.data);
        // An edge that moved from one node to another is a change too.
        const a = ancien as unknown as { source?: string; target?: string };
        const b = element as unknown as { source?: string; target?: string };
        if (a.source !== b.source) champs = [...champs, "source"];
        if (a.target !== b.target) champs = [...champs, "target"];
        if (champs.length) sortie[id] = { etat: "modifie", champs };
    }
    for (const id of avantParId.keys()) {
        if (!apresParId.has(id)) sortie[id] = { etat: "supprime", champs: [] };
    }
    return sortie;
}

export function comparer(avant: GrapheDuBuilder, apres: GrapheDuBuilder): Comparaison {
    return {
        noeuds: comparerLesElements(avant.nodes, apres.nodes),
        liaisons: comparerLesElements(avant.edges, apres.edges),
    };
}

export function resumer(comparaison: Comparaison): Resume {
    const compte = (m: Record<string, ChangementDElement>, etat: EtatDuChangement) =>
        Object.values(m).filter((c) => c.etat === etat).length;
    const r = {
        noeudsCrees: compte(comparaison.noeuds, "nouveau"),
        noeudsModifies: compte(comparaison.noeuds, "modifie"),
        noeudsSupprimes: compte(comparaison.noeuds, "supprime"),
        liaisonsCreees: compte(comparaison.liaisons, "nouveau"),
        liaisonsModifiees: compte(comparaison.liaisons, "modifie"),
        liaisonsSupprimees: compte(comparaison.liaisons, "supprime"),
    };
    return { ...r, total: Object.values(r).reduce((s, n) => s + n, 0) };
}

const CLASSE_NOEUD: Record<EtatDuChangement, string> = {
    nouveau: "ring-2 ring-(--signal-ok) ring-offset-2 rounded-lg",
    modifie: "ring-2 ring-(--signal-warn) ring-offset-2 rounded-lg",
    supprime: "ring-2 ring-(--signal-danger) ring-offset-2 rounded-lg opacity-60 [&_*]:line-through",
};

const STYLE_LIAISON: Record<EtatDuChangement, Record<string, string | number>> = {
    nouveau: { stroke: "var(--signal-ok)", strokeWidth: 3 },
    modifie: { stroke: "var(--signal-warn)", strokeWidth: 3 },
    supprime: { stroke: "var(--signal-danger)", strokeWidth: 3, strokeDasharray: "6 4" },
};

export interface TextesDuBadge {
    champs: (n: number) => string;
}

/**
 * The graph the canvas shows while the builder has changes to review.
 * "apres": the new graph, plus the removed nodes and edges kept (struck through) so they can be seen going.
 * "avant": the graph as it was, untouched. The element objects are shared with the inputs wherever nothing changes.
 */
export function grapheAAfficher(
    avant: GrapheDuBuilder,
    apres: GrapheDuBuilder,
    bascule: Bascule,
    textes: TextesDuBadge,
    comparaison: Comparaison = comparer(avant, apres),
): GrapheDuBuilder {
    if (bascule === "avant") return avant;
    const noeuds: NoeudAffiche[] = apres.nodes.map((noeud: NoeudAffiche) => {
        const c = comparaison.noeuds[noeud.id];
        if (!c) return noeud;
        const domAttributes = c.champs.length ? { "data-builder-badge": textes.champs(c.champs.length) } : undefined;
        return {
            ...noeud,
            className: [noeud.className, CLASSE_NOEUD[c.etat]].filter(Boolean).join(" "),
            ...(domAttributes ? { domAttributes } : {}),
        } as NoeudAffiche;
    });
    for (const ancien of avant.nodes) {
        if (comparaison.noeuds[ancien.id]?.etat === "supprime") {
            noeuds.push({ ...ancien, className: CLASSE_NOEUD.supprime, draggable: false, selectable: false } as NoeudAffiche);
        }
    }
    const liaisons: LiaisonAffichee[] = apres.edges.map((liaison: LiaisonAffichee) => {
        const c = comparaison.liaisons[liaison.id];
        return c ? ({ ...liaison, style: { ...liaison.style, ...STYLE_LIAISON[c.etat] } } as LiaisonAffichee) : liaison;
    });
    for (const ancienne of avant.edges) {
        if (comparaison.liaisons[ancienne.id]?.etat === "supprime") {
            liaisons.push({ ...(ancienne as LiaisonAffichee), style: { ...(ancienne as LiaisonAffichee).style, ...STYLE_LIAISON.supprime } } as LiaisonAffichee);
        }
    }
    return { nodes: noeuds, edges: liaisons };
}

/** The graph as plain data (what the editor saves), without React Flow's runtime-only fields (size, selection, classes). */
export function instantane(noeuds: FlowNode[], liaisons: FlowEdge[]): GrapheDuBuilder {
    return copie({
        nodes: noeuds.map(({ id, type, position, data }) => ({ id, type, position, data }) as FlowNode),
        edges: liaisons.map(
            (liaison) => {
                const { id, source, target, type, data } = liaison;
                const { sourceHandle, targetHandle } = liaison as LiaisonAffichee;
                return { id, source, target, sourceHandle, targetHandle, type, data } as FlowEdge;
            },
        ),
    });
}

/** A node without what the highlighting added (class, DOM attributes): what the editor may keep and save. */
export function retirerLeSurlignage<T extends FlowNode>(noeud: T): T {
    const { className: _classe, domAttributes: _attributs, ...reste } = noeud as T & NoeudAffiche;
    void _classe;
    void _attributs;
    return reste as unknown as T;
}
