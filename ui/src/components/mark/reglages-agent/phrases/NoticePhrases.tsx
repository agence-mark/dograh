"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.6, 4.7) : la NOTICE en tête du thème Phrases. Le chemin d'une phrase
 * (motif → phrase → redites → sortie), l'ordre de priorité (étape, agent, groupe, défaut) et, dépliable, ce qui est
 * FIXE et jamais réglé (« Comment le code parle »).
 */
import { ArrowRight, Info } from "lucide-react";

import { type Texte, useLangue } from "../../langue/langue";

const ETAPES: Array<{ titre: Texte; texte: Texte }> = [
    {
        titre: { en: "A cause", fr: "Un motif" },
        texte: { en: "What the code detects: a wait (tool, background work, colleague, caller) or a problem (a failure).", fr: "Ce que le code détecte : une attente (outil, fond, collègue, silence) ou un problème (échec)." },
    },
    {
        titre: { en: "A sentence", fr: "Une phrase" },
        texte: { en: "1 to 3 variants, rotated or in order, after a delay for a wait.", fr: "1 à 3 variantes, tournées ou dans l'ordre, après un délai pour une attente." },
    },
    {
        titre: { en: "Repeats", fr: "Des redites" },
        texte: { en: "As long as the wait lasts, or up to the cap of incidents in the call.", fr: "Tant que l'attente dure, ou jusqu'au plafond d'incidents dans l'appel." },
    },
    {
        titre: { en: "An exit", fr: "Une sortie" },
        texte: { en: "Continue, the model takes over with a report, transfer or hang up.", fr: "Continuer, le modèle reprend avec un compte rendu, transférer ou raccrocher." },
    },
];

const FIXES: Texte[] = [
    { en: "Never while the caller speaks; they can cut a sentence, it stops dead.", fr: "Jamais pendant que l'appelant parle ; il peut couper la phrase, elle s'arrête net." },
    { en: "One waiting sentence at a time, then the minimum pause.", fr: "Une seule phrase d'attente à la fois, puis la pause minimale." },
    { en: "The time only counts while the system waits; it restarts from zero when the caller speaks.", fr: "Le temps ne compte que quand le système attend ; il repart de zéro quand l'appelant parle." },
    { en: "The sentence enters the model's history as said by the agent; every sentence said is traced.", fr: "La phrase entre dans l'historique du modèle comme dite par l'agent ; chaque phrase dite est tracée." },
    { en: "If the result arrives during a sentence, it finishes, then the agent answers.", fr: "Si le résultat arrive pendant une phrase, elle finit, puis l'agent répond." },
    { en: "On the keyboard, the sentences of the code show in grey in the transcript.", fr: "Au clavier, les phrases du code s'affichent en gris dans la transcription." },
];

export const NoticePhrases = () => {
    const { t } = useLangue();
    return (
        <div className="space-y-3 rounded-lg border bg-muted/30 p-4" data-notice-phrases>
            <div className="flex items-start gap-2">
                <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <div className="text-sm">
                    <p className="font-semibold">{t({ en: "How fixed sentences work", fr: "Comment marchent les phrases fixes" })}</p>
                    <p className="text-muted-foreground">
                        {t({
                            en: "The voice says these sentences by itself, without the model, so the caller is never left in silence when something waits, and so it reacts at once when something fails. The rest of the conversation belongs to the model.",
                            fr: "La voix dit ces phrases d'elle-même, sans le modèle, pour ne jamais laisser l'appelant dans le silence quand on attend, et pour réagir tout de suite quand quelque chose échoue. Le reste de la conversation appartient au modèle.",
                        })}
                    </p>
                </div>
            </div>
            <div className="flex flex-col gap-2 md:flex-row md:items-stretch">
                {ETAPES.map((e, i) => (
                    <div key={i} className="flex flex-1 items-stretch gap-2">
                        {i > 0 && <ArrowRight className="hidden h-4 w-4 self-center text-muted-foreground md:block" />}
                        <div className="flex-1 rounded-md border bg-background p-3">
                            <div className="flex items-center gap-2">
                                <span className="flex h-5 w-5 items-center justify-center rounded-full bg-primary text-[11px] font-semibold text-primary-foreground">{i + 1}</span>
                                <span className="text-sm font-semibold">{t(e.titre)}</span>
                            </div>
                            <p className="mt-1 text-xs text-muted-foreground">{t(e.texte)}</p>
                        </div>
                    </div>
                ))}
            </div>
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "The most precise rule wins: step, then agent, then group, then default. A rule that is off says what happens instead.",
                    fr: "La règle la plus précise gagne : étape, puis agent, puis groupe, puis défaut. Une règle éteinte dit ce qui se passe à la place.",
                })}
            </p>
            <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer font-medium text-foreground">{t({ en: "How the code speaks (fixed, not adjustable)", fr: "Comment le code parle (fixe, non réglable)" })}</summary>
                <ol className="mt-2 list-decimal space-y-0.5 pl-5">
                    {FIXES.map((f, i) => (
                        <li key={i}>{t(f)}</li>
                    ))}
                </ol>
            </details>
        </div>
    );
};
