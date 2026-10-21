"use client";

/**
 * [.mark] Chantier fiabilite-orchestration, lot 4 ter (F24): the card « Sentences said by the code » of a
 * call's page. Each sentence the code said by itself (cause, agent, step, where its text came from, when,
 * the text), read from `phrases_du_code` in the call's record. A call without one shows nothing.
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useLangue } from "../langue/langue";
import { MOTIFS_DE_PHRASES } from "../reglages-agent/phrases/modele";

export interface PhraseDite {
    motif: string;
    agent?: number | null;
    etape?: string | null;
    niveau?: string | null;
    texte?: string | null;
    tour?: number | null;
    moment_s?: number | null;
}

const NIVEAUX: Record<string, { en: string; fr: string }> = {
    etape: { en: "step", fr: "étape" },
    agent: { en: "agent", fr: "agent" },
    principal: { en: "main agent", fr: "principal" },
    defaut: { en: "default", fr: "défaut" },
};

/** The entries of `phrases_du_code`, the unreadable ones left out. */
export const lirePhrasesDites = (contexte: Record<string, unknown> | null | undefined): PhraseDite[] => {
    const brutes = contexte?.phrases_du_code;
    if (!Array.isArray(brutes)) return [];
    return brutes.filter((e): e is PhraseDite => typeof e === "object" && e !== null && typeof (e as PhraseDite).motif === "string");
};

export const PhrasesDuCode = ({ contexte }: { contexte: Record<string, unknown> | null | undefined }) => {
    const { t } = useLangue();
    const phrases = lirePhrasesDites(contexte);
    if (phrases.length === 0) return null;
    return (
        <Card className="border-border" data-carte="phrases-du-code">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg">{t({ en: "Sentences said by the code", fr: "Phrases dites par le code" })}</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
                <table className="w-full">
                    <thead className="text-left text-muted-foreground">
                        <tr>
                            <th className="py-1 pr-3">{t({ en: "When (s)", fr: "Moment (s)" })}</th>
                            <th className="py-1 pr-3">{t({ en: "Cause", fr: "Motif" })}</th>
                            <th className="py-1 pr-3">{t({ en: "Where", fr: "Où" })}</th>
                            <th className="py-1">{t({ en: "Sentence", fr: "Phrase" })}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {phrases.map((phrase, i) => {
                            const motif = MOTIFS_DE_PHRASES.find((m) => m.id === phrase.motif);
                            const niveau = phrase.niveau ? NIVEAUX[phrase.niveau] : undefined;
                            return (
                                <tr key={i} data-phrase-dite={phrase.motif} className="align-top">
                                    <td className="py-1 pr-3 tabular-nums">{phrase.moment_s ?? "–"}</td>
                                    <td className="py-1 pr-3">{motif ? t(motif.libelle) : phrase.motif}</td>
                                    <td className="py-1 pr-3">
                                        {[phrase.agent != null ? `#${phrase.agent}` : null, phrase.etape, niveau ? t(niveau) : null]
                                            .filter(Boolean)
                                            .join(" · ")}
                                    </td>
                                    <td className="py-1">{phrase.texte ?? ""}</td>
                                </tr>
                            );
                        })}
                    </tbody>
                </table>
            </CardContent>
        </Card>
    );
};
