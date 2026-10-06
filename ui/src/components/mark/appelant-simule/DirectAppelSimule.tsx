"use client";

/**
 * [.mark] A simulated call followed live (chantier direct-et-passe-muette, lot A, P2, P4, P5).
 *
 * Read every second from `GET /appel-simule/runs/{run}/direct`, from the last event seen, until the
 * call ends. The events have the shape of a run's log, so they are drawn with Dograh's own
 * conversation timeline (`conversationItemsFromRealtimeFeedbackEvents`): what the simulated caller
 * says, what the agent answers, the tools, the steps. Once the call ends, the run window keeps its
 * saved transcript. A live view that cannot be read says so; the call goes on.
 */
import { useEffect, useRef, useState } from "react";

import { directAppelSimuleApiV1AppelSimuleRunsWorkflowRunIdDirectGet } from "@/client";
import type { DirectAppelSimule as Direct } from "@/client/types.gen";
import { conversationItemsFromRealtimeFeedbackEvents } from "@/components/workflow/conversation/adapters/fromRealtimeFeedback";
import { ConversationContainer } from "@/components/workflow/conversation/ConversationContainer";
import { ConversationTimeline } from "@/components/workflow/conversation/ConversationTimeline";
import type { RealtimeFeedbackEvent } from "@/components/workflow/conversation/types";
import { countConversationMessages } from "@/components/workflow/conversation/utils";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";

export const INTERVALLE_DIRECT_MS = 1000;

const PROPRES_AU_DIRECT = new Set(["rtf-user-mute-started", "rtf-user-mute-stopped"]);

/**
 * The live channel carries what the saved log does not: the caller's interim transcriptions, then
 * one final per segment, and the agent's text piece by piece. Consecutive pieces of the caller are
 * folded into one line (the finals, then what is being said); the agent's pieces already fold into
 * one bubble in Dograh's timeline. Mute signals, which would split a bubble, are left out.
 */
export function regrouperLeDirect(evenements: RealtimeFeedbackEvent[]): RealtimeFeedbackEvent[] {
    const sortie: RealtimeFeedbackEvent[] = [];
    let finals: string[] = [];
    let enCours: string | null = null;
    let premier: RealtimeFeedbackEvent | null = null;
    const vider = () => {
        if (!premier) return;
        const texte = [...finals, ...(enCours ? [enCours] : [])].join(" ").trim();
        if (texte) sortie.push({ ...premier, payload: { ...premier.payload, text: texte, final: enCours === null } });
        finals = [];
        enCours = null;
        premier = null;
    };
    for (const evenement of evenements) {
        if (PROPRES_AU_DIRECT.has(evenement.type)) continue;
        if (evenement.type === "rtf-user-transcription") {
            premier = premier ?? evenement;
            const texte = (evenement.payload.text ?? "").trim();
            if (evenement.payload.final) {
                if (texte) finals.push(texte);
                enCours = null;
            } else {
                enCours = texte || enCours;
            }
            continue;
        }
        vider();
        sortie.push(evenement);
    }
    vider();
    return sortie;
}

export function DirectAppelSimule({ runId, workflowId }: { runId: number; workflowId: number }) {
    const { t } = useLangue();
    const [evenements, setEvenements] = useState<RealtimeFeedbackEvent[]>([]);
    const [fini, setFini] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);
    const suivant = useRef(0);

    useEffect(() => {
        suivant.current = 0;
        setEvenements([]);
        setFini(false);
        setErreur(null);
        let arrete = false;
        let minuteur: ReturnType<typeof setTimeout> | undefined;
        const lire = async () => {
            const reponse = await directAppelSimuleApiV1AppelSimuleRunsWorkflowRunIdDirectGet({
                path: { workflow_run_id: runId },
                query: { depuis: suivant.current },
            });
            if (arrete) return;
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Live view unavailable"));
            } else {
                const direct = reponse.data as Direct;
                setErreur(null);
                suivant.current = direct.suivant;
                if (direct.evenements.length > 0) {
                    setEvenements((avant) => [...avant, ...(direct.evenements as unknown as RealtimeFeedbackEvent[])]);
                }
                if (direct.fini) {
                    setFini(true);
                    return;
                }
            }
            minuteur = setTimeout(() => void lire(), INTERVALLE_DIRECT_MS);
        };
        void lire();
        return () => {
            arrete = true;
            if (minuteur) clearTimeout(minuteur);
        };
    }, [runId]);

    const elements = conversationItemsFromRealtimeFeedbackEvents(regrouperLeDirect(evenements));
    return (
        <div className="space-y-1" data-testid="direct-appel-simule">
            {erreur && (
                <p className="text-xs text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            <div className="h-80 min-h-0">
                <ConversationContainer
                    title={fini ? t({ en: "Call transcript", fr: "Transcription de l'appel" }) : t({ en: "Live transcript", fr: "Transcription en direct" })}
                    status={fini ? "ended" : "live"}
                    messageCount={countConversationMessages(elements) || undefined}
                >
                    <ConversationTimeline
                        items={elements}
                        autoScroll
                        emptyState={{
                            title: t({ en: "Waiting for the first words", fr: "En attente des premiers mots" }),
                            subtitle: t({
                                en: "The simulated caller and the agent appear here as they speak.",
                                fr: "L'appelant simulé et l'agent apparaissent ici au fil de la conversation.",
                            }),
                        }}
                    />
                </ConversationContainer>
            </div>
            {fini && (
                <a className="text-xs underline" href={`/workflow/${workflowId}/run/${runId}`} target="_blank" rel="noreferrer">
                    {t({ en: "Saved transcript and verdict: run window", fr: "Transcription enregistrée et verdict : fenêtre du run" })}
                </a>
            )}
        </div>
    );
}
