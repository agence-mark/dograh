"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): « Create a test » on the page of a call. The person picks the reply at fault among the
 * caller's replies of THIS call (counted from 1, final transcriptions only), then fills the criteria. The server cuts the call just
 * before that reply and replaces the personal data by fake ones.
 */
import Link from "next/link";
import { useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";

import { NouveauTest } from "./NouveauTest";

interface EvenementDuJournal {
    type?: string;
    payload?: { final?: boolean; text?: string };
}

/** The caller's final replies of a call, in order (the same reading as the server's: `rtf-user-transcription`, final). */
export function repliquesDeLaPersonne(evenements: EvenementDuJournal[] | null | undefined): string[] {
    return (evenements ?? [])
        .filter((e) => e.type === "rtf-user-transcription" && e.payload?.final && String(e.payload?.text ?? "").trim())
        .map((e) => String(e.payload?.text).trim());
}

interface Props {
    workflowId: number;
    runId: number;
    evenements: EvenementDuJournal[] | null | undefined;
    /** Opens on this reply (the « To triage » page passes the turn of the flag). */
    rangInitial?: number;
}

export function BoutonCreerUnTest({ workflowId, runId, evenements, rangInitial }: Props) {
    const { t } = useLangue();
    const repliques = repliquesDeLaPersonne(evenements);
    const [ouvert, setOuvert] = useState(rangInitial !== undefined);
    const [rang, setRang] = useState(Math.min(Math.max(rangInitial ?? 1, 1), Math.max(repliques.length, 1)));
    const [cree, setCree] = useState<string | null>(null);

    if (repliques.length === 0) return null;
    return (
        <div className="space-y-2 rounded border p-3 text-sm" data-testid="creer-un-test-depuis-l-appel">
            {!ouvert && (
                <Button variant="outline" size="sm" onClick={() => setOuvert(true)}>
                    {t({ en: "Create a test from a reply", fr: "Créer un test depuis une réplique" })}
                </Button>
            )}
            {ouvert && !cree && (
                <>
                    <label className="block space-y-1">
                        <span>{t({ en: "The reply at fault", fr: "La réplique fautive" })}</span>
                        <select
                            aria-label={t({ en: "Reply", fr: "Réplique" })}
                            className="w-full rounded-md border bg-background px-2 py-1.5"
                            value={rang}
                            onChange={(e) => setRang(Number(e.target.value))}
                        >
                            {repliques.map((r, i) => (
                                <option key={i} value={i + 1}>
                                    {i + 1}. {r.slice(0, 80)}
                                </option>
                            ))}
                        </select>
                    </label>
                    <NouveauTest workflowId={workflowId} source={{ runId, rang, extrait: repliques[rang - 1]?.slice(0, 80) }} onCree={(slug) => setCree(slug || "ok")} onFermer={() => setOuvert(false)} />
                </>
            )}
            {cree && (
                <p data-testid="test-cree">
                    {t({ en: "Test created.", fr: "Test créé." })}{" "}
                    <Link className="underline" href={`/workflow/${workflowId}/tests`}>
                        {t({ en: "Open the tests", fr: "Ouvrir les tests" })}
                    </Link>
                </p>
            )}
        </div>
    );
}
