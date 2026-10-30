"use client";

/**
 * [.mark] agent-facon-tala (lot D3): the compact table at the top of the « To triage » page. One line per agent over the last
 * 7 or 30 days: calls, share of calls that went through a dead end, share of calls where the model was corrected and recovered
 * by itself (repeated nudges, no dead end). The nudges are only counted, never lines to triage. A click on an agent sets the
 * agent filter of the queue below. No threshold, no alert: the numbers are for reading.
 */
import { lireLesTauxDeSortieDImpasseApiV1TriTauxGet } from "@/client";
import type { LigneDeTaux } from "@/client/types.gen";
import { useCallback, useEffect, useState } from "react";

import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";

const PERIODES = [7, 30] as const;

const pourcent = (part?: number | null) => (part === null || part === undefined ? "—" : `${Math.round(part * 100)} %`);

export function TauxDeSortieDImpasse({ agentChoisi, onChoisir, onAgents }: {
    agentChoisi: number | "";
    onChoisir: (id: number | "") => void;
    onAgents?: (agents: Record<number, string>) => void;
}) {
    const { t } = useLangue();
    const [jours, setJours] = useState<number>(7);
    const [lignes, setLignes] = useState<LigneDeTaux[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const reponse = await lireLesTauxDeSortieDImpasseApiV1TriTauxGet({ query: { jours } });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The rates could not be read"));
            return;
        }
        setErreur(null);
        setLignes(reponse.data.lignes);
        onAgents?.(Object.fromEntries(reponse.data.lignes.map((l) => [l.workflow_id, l.workflow_nom])));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [jours]);

    useEffect(() => {
        void charger();
    }, [charger]);

    return (
        <section className="space-y-2 rounded border p-3" data-testid="taux-impasse" aria-label={t({ en: "Dead-end rates by agent", fr: "Taux d'impasse par agent" })}>
            <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-sm font-medium">{t({ en: "Dead ends by agent", fr: "Impasses par agent" })}</h2>
                <div className="flex gap-1" role="group" aria-label={t({ en: "Period", fr: "Période" })}>
                    {PERIODES.map((p) => (
                        <button
                            key={p}
                            type="button"
                            aria-pressed={jours === p}
                            className={`h-7 rounded-md border px-2 text-xs ${jours === p ? "bg-muted font-medium" : "bg-background"}`}
                            onClick={() => setJours(p)}
                        >
                            {p} {t({ en: "days", fr: "jours" })}
                        </button>
                    ))}
                </div>
            </div>
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {lignes !== null && lignes.length === 0 && (
                <p className="text-sm text-muted-foreground" data-testid="taux-vide">
                    {t({ en: "No call over this period.", fr: "Aucun appel sur cette période." })}
                </p>
            )}
            {lignes !== null && lignes.length > 0 && (
                <table className="w-full text-sm">
                    <thead>
                        <tr className="text-left text-xs text-muted-foreground">
                            <th className="py-1 font-normal">{t({ en: "Agent", fr: "Agent" })}</th>
                            <th className="py-1 font-normal">{t({ en: "Calls", fr: "Appels" })}</th>
                            <th className="py-1 font-normal">{t({ en: "With a dead end", fr: "Avec impasse" })}</th>
                            <th className="py-1 font-normal">{t({ en: "Recovered by itself", fr: "Repris, sans impasse" })}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {lignes.map((l) => (
                            <tr key={l.workflow_id} className="border-t" data-testid={`taux-${l.workflow_id}`}>
                                <td className="py-1">
                                    <button
                                        type="button"
                                        className={`underline ${agentChoisi === l.workflow_id ? "font-medium" : ""}`}
                                        aria-pressed={agentChoisi === l.workflow_id}
                                        onClick={() => onChoisir(agentChoisi === l.workflow_id ? "" : l.workflow_id)}
                                    >
                                        {l.workflow_nom}
                                    </button>
                                </td>
                                <td className="py-1">{l.appels}</td>
                                <td className="py-1" data-testid={`part-impasse-${l.workflow_id}`}>
                                    {pourcent(l.part_impasse)} <span className="text-xs text-muted-foreground">({l.avec_impasse})</span>
                                </td>
                                <td className="py-1" data-testid={`part-reprise-${l.workflow_id}`}>
                                    {pourcent(l.part_reprise)}{" "}
                                    <span className="text-xs text-muted-foreground">
                                        ({l.avec_reprise_sans_impasse} / {l.appels_avec_compteur}{" "}
                                        {t({ en: "calls with the counter", fr: "appels avec le compteur" })})
                                    </span>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </section>
    );
}
