/**
 * [.mark] builder-agent-vocal (lot 4): the builder's stream (SSE) as events, and the events as assistant-ui parts.
 *
 * The server (`api/services/builder/moteur.py`) sends, one `data: {...}` line per event: `texte`, `action`,
 * `resultat`, `carte`, `operation`, `depense`, `erreur`, `fin`. Nothing here talks to a provider: this is the
 * screen's side of the builder's own route.
 */
import type { OperationDuBuilder } from "./graphe";

export type EvenementDuBuilder =
    | { type: "texte"; texte: string }
    | { type: "action"; id: string; nom: string; arguments: Record<string, unknown> }
    | { type: "resultat"; id: string; nom: string; ok: boolean; resultat: Record<string, unknown> }
    | { type: "carte"; carte: { type: string; [cle: string]: unknown } }
    | { type: "operation"; operation: OperationDuBuilder }
    | { type: "depense"; jetons: number; cout: number; plafond_jetons: number; plafond_depense: number }
    | { type: "erreur"; code: string; message: string }
    | { type: "fin"; raison: string };

/** Splits a text stream into events. A chunk may hold half a line: the rest waits for the next one. */
export async function* lireLeFlux(flux: ReadableStream<Uint8Array>): AsyncGenerator<EvenementDuBuilder> {
    const lecteur = flux.getReader();
    const decodeur = new TextDecoder();
    let reste = "";
    try {
        for (;;) {
            const { done, value } = await lecteur.read();
            if (done) break;
            reste += decodeur.decode(value, { stream: true });
            let coupure = reste.indexOf("\n\n");
            while (coupure !== -1) {
                const bloc = reste.slice(0, coupure);
                reste = reste.slice(coupure + 2);
                const evenement = lireUnBloc(bloc);
                if (evenement) yield evenement;
                coupure = reste.indexOf("\n\n");
            }
        }
        const dernier = lireUnBloc(reste);
        if (dernier) yield dernier;
    } finally {
        lecteur.releaseLock();
    }
}

export function lireUnBloc(bloc: string): EvenementDuBuilder | null {
    const ligne = bloc.split("\n").find((l) => l.startsWith("data: "));
    if (!ligne) return null;
    try {
        const evenement = JSON.parse(ligne.slice(6)) as EvenementDuBuilder;
        return evenement && typeof evenement.type === "string" ? evenement : null;
    } catch {
        return null;
    }
}

// --- the parts of an assistant message ---------------------------------------------------------------------------

export type PartieTexte = { type: "text"; text: string };
export type PartieAction = {
    type: "tool-call";
    toolCallId: string;
    toolName: string;
    args: Record<string, never> | Record<string, unknown>;
    argsText: string;
    result?: Record<string, unknown>;
    isError?: boolean;
};
export type PartieDuMessage = PartieTexte | PartieAction;

/** Adds an event to the parts of the message being written (text is joined, an action waits for its result). */
export function ajouterAuxParties(parties: PartieDuMessage[], evenement: EvenementDuBuilder): PartieDuMessage[] {
    if (evenement.type === "texte") {
        const dernier = parties[parties.length - 1];
        if (dernier?.type === "text") {
            return [...parties.slice(0, -1), { type: "text", text: dernier.text + evenement.texte }];
        }
        return [...parties, { type: "text", text: evenement.texte }];
    }
    if (evenement.type === "action") {
        return [
            ...parties,
            {
                type: "tool-call",
                toolCallId: evenement.id,
                toolName: evenement.nom,
                args: evenement.arguments as Record<string, unknown>,
                argsText: JSON.stringify(evenement.arguments),
            },
        ];
    }
    if (evenement.type === "resultat") {
        return parties.map((p) =>
            p.type === "tool-call" && p.toolCallId === evenement.id
                ? { ...p, result: evenement.resultat, isError: !evenement.ok }
                : p,
        );
    }
    if (evenement.type === "erreur") {
        return [...parties, { type: "text", text: `\n${evenement.message}` }];
    }
    return parties;
}
