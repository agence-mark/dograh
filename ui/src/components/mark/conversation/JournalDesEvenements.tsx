"use client";

/**
 * [.mark] V1b : le journal des événements d'un appel, à la forme de la maquette : une heure (depuis le premier
 * événement), une phrase. Tout vient de `workflow_runs.logs` (événements horodatés enregistrés pendant l'appel).
 */
import type { RealtimeFeedbackEvent } from '@/components/workflow/conversation/types';

import { type Texte, useLangue } from '../langue/langue';

/** « 00:04.2 » : minutes, secondes et dixièmes depuis le premier événement. */
export function heureDuJournal(secondes: number) {
    const total = Math.max(0, secondes);
    const minutes = Math.floor(total / 60);
    const reste = total - minutes * 60;
    return `${String(minutes).padStart(2, '0')}:${reste.toFixed(1).padStart(4, '0')}`;
}

const GENRES_DE_MESURE: Record<string, Texte> = {
    stt: { en: 'transcription', fr: 'transcription' },
    llm: { en: 'model', fr: 'modèle' },
    tts: { en: 'voice', fr: 'voix' },
};

/** La phrase d'un événement, dans la langue de l'écran ; `null` = événement sans intérêt pour le journal (parole non finale). */
export function phraseDeLEvenement(evenement: RealtimeFeedbackEvent, t: (texte: Texte) => string): string | null {
    const p = evenement.payload ?? {};
    const nom = p.function_name ?? '?';
    switch (evenement.type) {
        case 'rtf-user-transcription':
            if (!p.final) return null;
            return t({ en: `caller speaks: « ${p.text ?? ''} »`, fr: `parole de l'appelant : « ${p.text ?? ''} »` });
        case 'rtf-bot-text':
            return t({ en: `agent says: « ${p.text ?? ''} »`, fr: `l'agent dit : « ${p.text ?? ''} »` });
        case 'rtf-function-call-start':
            return t({ en: `tool ${nom}: start`, fr: `outil ${nom} : début` });
        case 'rtf-function-call-end':
            return t({ en: `tool ${nom}: end`, fr: `outil ${nom} : fin` });
        case 'rtf-node-transition': {
            const vers = p.node_name ?? p.node_id ?? '?';
            const depuis = p.previous_node_name ?? p.previous_node ?? null;
            return depuis
                ? t({ en: `step: ${depuis} → ${vers}`, fr: `étape : ${depuis} → ${vers}` })
                : t({ en: `step: ${vers}`, fr: `étape : ${vers}` });
        }
        case 'rtf-ttfb-metric': {
            const genre = GENRES_DE_MESURE[p.kind ?? ''];
            const valeur = typeof p.ttfb_seconds === 'number' ? `${p.ttfb_seconds.toFixed(2)} s` : '–';
            return t({
                en: `first output (${genre ? genre.en : 'service'}): ${valeur}`,
                fr: `première sortie (${genre ? genre.fr : 'service'}) : ${valeur}`,
            });
        }
        case 'rtf-interrupt-warning':
            return t({ en: 'the caller interrupted the agent', fr: "l'appelant a coupé l'agent" });
        case 'rtf-pipeline-error':
            // Jamais le texte brut d'une erreur technique à l'écran : on dit où, pas quoi.
            return t({
                en: `incident in the call pipeline${p.processor ? ` (${p.processor})` : ''}`,
                fr: `incident dans le circuit de l'appel${p.processor ? ` (${p.processor})` : ''}`,
            });
        default:
            return null;
    }
}

export function JournalDesEvenements({ evenements }: { evenements: RealtimeFeedbackEvent[] | null | undefined }) {
    const { t } = useLangue();
    const datees = (evenements ?? []).filter((e) => e.timestamp);
    const origine = datees.length ? Date.parse(datees[0].timestamp as string) : NaN;
    const lignes = (evenements ?? [])
        .map((e) => {
            const phrase = phraseDeLEvenement(e, t);
            if (!phrase) return null;
            const instant = e.timestamp ? Date.parse(e.timestamp) : NaN;
            return { heure: Number.isNaN(origine) || Number.isNaN(instant) ? null : (instant - origine) / 1000, phrase };
        })
        .filter((l): l is { heure: number | null; phrase: string } => l !== null);
    if (lignes.length === 0)
        return (
            <p className="py-6 text-sm text-muted-foreground" data-testid="journal-vide">
                {t({ en: 'No event recorded for this call.', fr: "Aucun événement enregistré pour cet appel." })}
            </p>
        );
    return (
        <div className="divide-y divide-border" data-testid="journal-des-evenements">
            {lignes.map((l, i) => (
                <div key={i} className="flex gap-4 py-3 text-sm" data-testid="evenement-du-journal">
                    <span className="w-44 shrink-0 tabular-nums text-muted-foreground">{l.heure == null ? '–' : heureDuJournal(l.heure)}</span>
                    <span className="min-w-0 flex-1 break-words">{l.phrase}</span>
                </div>
            ))}
        </div>
    );
}
