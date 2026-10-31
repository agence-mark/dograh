"use client";

/**
 * [.mark] builder-agent-vocal (lot 4, B27): the « Knowledge base » card. The documents the agent will consult to
 * answer (large, rarely asked: FAQ, catalogue, conditions) proposed from the audit; each carries the passages it
 * comes from. A person validates (the document then enters the existing knowledge base) or rejects.
 */
import { useState } from "react";

import { rejeterUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdRejeterPost, validerUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdValiderPost } from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { useBuilderEcran } from "../store";
import { Carte } from "./Carte";

const T = {
    titre: { en: "Knowledge base", fr: "Base de connaissances" },
    aide: {
        en: "What the agent can answer. Proposed from the audit, never a price or a promise it does not hold.",
        fr: "Ce que l'agent peut répondre. Proposé depuis l'audit, jamais un tarif ni une promesse qu'il ne contient pas.",
    },
    aucun: { en: "No document proposed.", fr: "Aucun document proposé." },
    valider: { en: "Validate", fr: "Valider" },
    rejeter: { en: "Reject", fr: "Rejeter" },
    propose: { en: "proposed", fr: "proposé" },
    valide: { en: "in the knowledge base", fr: "dans la base de connaissances" },
    rejete: { en: "rejected", fr: "rejeté" },
    sources: { en: "Sources", fr: "Sources" },
    rattache: { en: "Attached to", fr: "Rattaché à" },
    echec: { en: "The request failed.", fr: "La demande a échoué." },
} satisfies Record<string, Texte>;

interface DocumentDeBase {
    id: string;
    titre: string;
    contenu: string;
    etat: "propose" | "valide" | "rejete";
    sources: { document: string; page?: number | null; extrait: string }[];
    rattache_a: string[];
}

export function CarteBase({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const documents = ((useBuilderEcran((s) => s.contexte?.base)) ?? []) as unknown as DocumentDeBase[];
    const rafraichir = useBuilderEcran((s) => s.rafraichirLeContexte);
    const [erreur, setErreur] = useState<string | null>(null);

    const agir = async (id: string, valider: boolean) => {
        setErreur(null);
        const reponse = valider
            ? await validerUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdValiderPost({ path: { workflow_id: workflowId, document_id: id } })
            : await rejeterUnDocumentDeBaseApiV1BuilderBaseWorkflowIdDocumentIdRejeterPost({ path: { workflow_id: workflowId, document_id: id }, body: {} });
        if (reponse.error) setErreur(detailFromError(reponse.error, t(T.echec)));
        await rafraichir(workflowId);
    };

    return (
        <Carte type="base" titre={t(T.titre)} aide={t(T.aide)}>
            {documents.length === 0 && <p className="text-xs text-muted-foreground">{t(T.aucun)}</p>}
            <ul className="space-y-2">
                {documents.map((d) => (
                    <li key={d.id} className="rounded-md border p-2 text-xs" data-document-base={d.titre}>
                        <div className="flex items-center gap-2">
                            <span className="font-medium">{d.titre}</span>
                            <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-muted-foreground">{t(T[d.etat])}</span>
                        </div>
                        <p className="mt-1 whitespace-pre-wrap">{d.contenu}</p>
                        <details className="mt-1 text-muted-foreground">
                            <summary>{t(T.sources)}</summary>
                            <ul className="list-disc pl-4">
                                {d.sources.map((s) => (
                                    <li key={`${s.document}-${s.extrait}`}>
                                        {s.document}
                                        {s.page ? `, p. ${s.page}` : ""} : « {s.extrait} »
                                    </li>
                                ))}
                            </ul>
                        </details>
                        {d.rattache_a.length > 0 && <p className="mt-1 text-muted-foreground">{t(T.rattache)} {d.rattache_a.join(", ")}</p>}
                        {d.etat === "propose" && (
                            <div className="mt-2 flex gap-2">
                                <Button type="button" size="sm" onClick={() => void agir(d.id, true)}>{t(T.valider)}</Button>
                                <Button type="button" size="sm" variant="outline" onClick={() => void agir(d.id, false)}>{t(T.rejeter)}</Button>
                            </div>
                        )}
                    </li>
                ))}
            </ul>
            {erreur && <p role="alert" className="mt-2 text-xs text-destructive">{erreur}</p>}
        </Carte>
    );
}
