"use client";

/**
 * [.mark] Chantier fiabilite-orchestration, lot 4 ter (F24): the card « Sentences said by the code » of a
 * call's page. Each sentence the code said by itself (cause, agent, step, where its text came from, when,
 * the text), read from `phrases_du_code` in the call's record. A call without one says so (point 8 of correctifs-ecran-production).
 */
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

/** « 00:31.6 » : le moment en minutes, secondes et dixièmes, comme la maquette. */
export const momentDit = (secondes: number | null | undefined) => {
    if (typeof secondes !== "number" || Number.isNaN(secondes)) return "–";
    const m = Math.floor(secondes / 60);
    const reste = (secondes - m * 60).toFixed(1).padStart(4, "0");
    return `${String(m).padStart(2, "0")}:${reste}`;
};

/** Correctif écran point 8 : une ligne par phrase (moment, motif → phrase) ; sans phrase, un état vide (plus de page blanche). */
export const PhrasesDuCode = ({ contexte }: { contexte: Record<string, unknown> | null | undefined }) => {
    const { t } = useLangue();
    const phrases = lirePhrasesDites(contexte);
    if (phrases.length === 0) {
        return (
            <p className="py-3 text-sm text-muted-foreground" data-testid="phrases-du-code-vide">
                {t({
                    en: "The code said no sentence by itself during this call.",
                    fr: "Le code n'a dit aucune phrase de lui-même pendant cet appel.",
                })}
            </p>
        );
    }
    return (
        <section data-carte="phrases-du-code">
            <p className="pb-1 text-base font-semibold">{t({ en: "Sentences said by the code", fr: "Phrases dites par le code" })}</p>
            <div className="divide-y divide-border">
                {phrases.map((phrase, i) => {
                    const motif = MOTIFS_DE_PHRASES.find((m) => m.id === phrase.motif);
                    const niveau = phrase.niveau ? NIVEAUX[phrase.niveau] : undefined;
                    const ou = [phrase.agent != null ? `#${phrase.agent}` : null, phrase.etape, niveau ? t(niveau) : null].filter(Boolean).join(" · ");
                    return (
                        <div key={i} data-phrase-dite={phrase.motif} className="flex gap-4 py-2.5 text-sm">
                            <span className="w-24 shrink-0 tabular-nums text-muted-foreground">{momentDit(phrase.moment_s)}</span>
                            <span className="min-w-0 flex-1">
                                {motif ? t(motif.libelle) : phrase.motif} → « {phrase.texte ?? ""} »
                                {ou && <span className="block text-xs text-muted-foreground">{ou}</span>}
                            </span>
                        </div>
                    );
                })}
            </div>
        </section>
    );
};
