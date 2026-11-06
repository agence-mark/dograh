"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): « Create a test » on the page of a call. The person picks the reply at fault among the
 * caller's replies of THIS call (counted from 1, final transcriptions only), then fills the criteria. The server cuts the call just
 * before that reply and replaces the personal data by fake ones.
 */
import Link from "next/link";
import { useState } from "react";

import { creerDepuisUneConversationApiV1BuilderTestsWorkflowIdDepuisUneConversationPost } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { notifier } from "@/components/mark/notifications/notifier";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
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
    // Partie 3, sous-lot 5 : « Depuis une conversation entière » : l'appel entier devient un test de conversation simulée.
    const [entiere, setEntiere] = useState(false);
    const [nomEntier, setNomEntier] = useState("");
    const [envoi, setEnvoi] = useState(false);
    const [erreurEntiere, setErreurEntiere] = useState<string | null>(null);

    const creerLEntiere = async () => {
        setEnvoi(true);
        setErreurEntiere(null);
        const r = await creerDepuisUneConversationApiV1BuilderTestsWorkflowIdDepuisUneConversationPost({
            path: { workflow_id: workflowId },
            body: { run_id: runId, nom: nomEntier.trim() },
        });
        setEnvoi(false);
        if (r.error) {
            setErreurEntiere(echecAffiche(r.error, ECHECS.testDepuisConversation));
            return;
        }
        notifier.succes({ en: "Test created from the whole conversation. Personal data was replaced.", fr: "Test créé depuis la conversation entière. Les données personnelles ont été remplacées." });
        setCree((r.data as { test?: { slug?: string } }).test?.slug || "ok");
    };

    if (repliques.length === 0) return null;
    return (
        <div className="space-y-2 text-sm" data-testid="creer-un-test-depuis-l-appel">
            {!ouvert && !entiere && !cree && (
                <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={() => setOuvert(true)}>
                        {t({ en: "Create a test from a reply", fr: "Créer un test depuis une réplique" })}
                    </Button>
                    <Button variant="outline" size="sm" onClick={() => setEntiere(true)}>
                        {t({ en: "Create a test from the whole conversation", fr: "Créer un test depuis la conversation entière" })}
                    </Button>
                </div>
            )}
            {entiere && !cree && (
                <div className="space-y-2" data-testid="creer-un-test-depuis-la-conversation-entiere">
                    <label className="block space-y-1">
                        <span>{t({ en: "Test name", fr: "Nom du test" })}</span>
                        <input
                            className="w-full rounded-md border bg-background px-2 py-1.5"
                            value={nomEntier}
                            onChange={(e) => setNomEntier(e.target.value)}
                            aria-label={t({ en: "Test name", fr: "Nom du test" })}
                        />
                    </label>
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: "The caller's words become the scenario of a simulated conversation; the outcome and the order of the tools called become criteria. Personal data is replaced.",
                            fr: "Les paroles de l'appelant deviennent le scénario d'une conversation simulée ; la fin d'appel et l'ordre des outils appelés deviennent des critères. Les données personnelles sont remplacées.",
                        })}
                    </p>
                    {erreurEntiere && (
                        <p role="alert" className="text-destructive">
                            {erreurEntiere}
                        </p>
                    )}
                    <div className="flex gap-2">
                        <Button size="sm" disabled={!nomEntier.trim() || envoi} onClick={() => void creerLEntiere()}>
                            {t({ en: "Create the test", fr: "Créer le test" })}
                        </Button>
                        <Button variant="outline" size="sm" onClick={() => setEntiere(false)}>
                            {t({ en: "Cancel", fr: "Annuler" })}
                        </Button>
                    </div>
                </div>
            )}
            {ouvert && !cree && (
                <>
                    <label className="block space-y-1">
                        <span>{t({ en: "The reply at fault", fr: "La réplique fautive" })}</span>
                        <ListeDeroulante
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
                        </ListeDeroulante>
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
