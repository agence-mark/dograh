"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 (plan 4.7, maquette `maquette/phrases-du-code`) : une CARTE par règle.
 * Cliquable (elle ouvre la modale de la règle) ; montre le motif, l'outil, l'endroit, les phrases (flèche = dans
 * l'ordre, « ou » = tournées), le délai, les redites, la sortie, la fin d'attente lue ailleurs, l'interrupteur
 * (qui n'ouvre PAS la modale), l'origine et la dernière fois dite. Éteinte, la carte est grisée et dit ce qui se
 * passe à la place ; orange quand l'étape visée n'existe plus (la règle est sans effet).
 */
import {
    AlertTriangle,
    ArrowRight,
    ChevronRight,
    Clock,
    Hourglass,
    LogOut,
    MessageSquareText,
    PhoneForwarded,
    Repeat,
    Timer,
    UserRound,
    Wrench,
} from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import type { ReglePhrase } from "@/types/workflow-configurations";

import { useLangue } from "../../langue/langue";
import { type ContextePhrases, type Moment, type MotifDePhrase, normaliserRegle, type Origine, ORIGINES, type Puce,puces } from "./modele";

export const TONS: Record<Moment, string> = {
    attente: "bg-(--acc-soft) text-(--acc-text)",
    probleme: "bg-(--signal-warn)/10 text-(--signal-warn)",
    action: "bg-(--signal-ok)/10 text-(--signal-ok)",
};

/** L'icône d'un motif, rangée par identifiant (un motif inconnu garde l'icône de son moment). */
export const iconeDuMotif = (motif: MotifDePhrase) => {
    switch (motif.id) {
        case "outil_tarde":
            return Wrench;
        case "travail_dure":
            return Hourglass;
        case "passation_tarde":
        case "transfert_echoue":
            return PhoneForwarded;
        case "modele_tarde":
            return Timer;
        case "appelant_se_tait":
            return UserRound;
        case "reponse_perdue":
            return MessageSquareText;
        case "mise_en_relation":
            return LogOut;
        default:
            return motif.moment === "probleme" ? AlertTriangle : Clock;
    }
};

const ICONES_PUCES = { horloge: Clock, redite: Repeat, sortie: LogOut, fin: Hourglass, fait: AlertTriangle } as const;

export const PucesDeLaRegle = ({ liste }: { liste: Puce[] }) => (
    <div className="flex flex-wrap gap-1.5">
        {liste.map((p, i) => {
            const Icone = ICONES_PUCES[p.icone];
            return (
                <span
                    key={i}
                    className={`inline-flex items-center gap-1 rounded-md border bg-background px-1.5 py-0.5 text-[11px] ${p.discret ? "text-muted-foreground" : ""}`}
                >
                    <Icone className="h-3 w-3" />
                    {p.texte}
                </span>
            );
        })}
    </div>
);

export interface ProprietesCarte {
    id: string;
    regle: ReglePhrase;
    motif: MotifDePhrase;
    origine: Origine;
    contexte: ContextePhrases;
    /** Le nom de l'étape visée, quand la règle en cible une. */
    etape?: string;
    /** L'étape visée n'existe plus : la règle est sans effet. */
    supprimee?: boolean;
    /** Allumée, au sens du catalogue pour un défaut. */
    active: boolean;
    derniere: string;
    /** Une règle héritée du principal : lecture, pas d'interrupteur ni d'ouverture. */
    lecture?: boolean;
    onOuvrir?: () => void;
    onBasculer?: (active: boolean) => void;
    /** Sous la carte, pour les gestes d'une règle héritée. */
    pied?: ReactNode;
}

export const CartePhrase = ({ id, regle: brute, motif, origine, contexte: c, etape, supprimee, active, derniere, lecture, onOuvrir, onBasculer, pied }: ProprietesCarte) => {
    const { t } = useLangue();
    const regle = normaliserRegle(brute);
    const Icone = iconeDuMotif(motif);
    const liste = puces(regle, c);
    const ouvre = !lecture && onOuvrir;
    return (
        <div
            role={ouvre ? "button" : undefined}
            tabIndex={ouvre ? 0 : undefined}
            aria-label={ouvre ? `${t(motif.libelle)}${etape ? ` : ${etape}` : ""}` : undefined}
            onClick={ouvre ? onOuvrir : undefined}
            onKeyDown={ouvre ? (e) => e.key === "Enter" && onOuvrir?.() : undefined}
            data-carte-phrase={id}
            data-motif={motif.id}
            data-origine={origine}
            data-active={active ? "oui" : "non"}
            className={`group flex items-stretch gap-4 rounded-lg border p-4 transition ${ouvre ? "cursor-pointer hover:border-foreground/30 hover:shadow-sm" : ""} ${
                supprimee ? "border-(--signal-warn) bg-(--signal-warn)/10" : active ? "bg-card" : "bg-muted/30"
            }`}
        >
            <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${TONS[motif.moment]} ${active ? "" : "opacity-50"}`}>
                <Icone className="h-4 w-4" />
            </span>

            <div className={`min-w-0 flex-1 space-y-2 ${active ? "" : "opacity-60"}`}>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm font-semibold">{t(motif.libelle)}</span>
                    {regle.outils && regle.outils.length > 0 && (
                        <span className="text-xs text-muted-foreground">
                            {t({ en: "for", fr: "pour" })} <code className="text-[11px]">{regle.outils.join(", ")}</code>
                        </span>
                    )}
                    <Badge variant="outline" className="text-[11px] font-normal">
                        {regle.portee === "etape" ? `${t({ en: "Step", fr: "Étape" })} : ${etape ?? ""}` : regle.portee === "groupe" ? t({ en: "The whole group", fr: "Tout le groupe" }) : origine === "defaut" ? t({ en: "Default", fr: "Défaut" }) : t({ en: "This agent", fr: "Cet agent" })}
                    </Badge>
                </div>

                {(regle.variantes?.length ?? 0) > 0 ? (
                    <div className="flex flex-wrap items-center gap-1.5">
                        {regle.variantes!.map((p, i) => (
                            <span key={`${p}-${i}`} className="flex items-center gap-1.5">
                                {i > 0 &&
                                    (regle.ordre === "dans_l_ordre" ? (
                                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                                    ) : (
                                        <span className="text-xs text-muted-foreground">{t({ en: "or", fr: "ou" })}</span>
                                    ))}
                                <span className="rounded-md bg-muted px-2 py-1 text-[13px]">« {p} »</span>
                            </span>
                        ))}
                        {regle.texte_de_l_agent && (
                            <span className="text-[11px] text-muted-foreground">{t({ en: "(or the sentence the agent writes)", fr: "(ou la phrase écrite par l'agent)" })}</span>
                        )}
                    </div>
                ) : (
                    <span className="text-xs text-muted-foreground">
                        {regle.texte_de_l_agent
                            ? t({ en: "The sentence the agent writes.", fr: "La phrase écrite par l'agent." })
                            : t({ en: "No sentence: the code says nothing.", fr: "Aucune phrase : le code ne dit rien." })}
                    </span>
                )}

                <PucesDeLaRegle liste={liste} />

                {supprimee && (
                    <p className="text-xs font-medium" data-note="etape-supprimee">
                        {t({ en: "Step deleted: this rule has no effect. Reassign or delete it.", fr: "Étape supprimée : règle sans effet. À réattribuer ou supprimer." })}
                    </p>
                )}
                {!active && !supprimee && (
                    <p className="text-xs text-muted-foreground">
                        {t({ en: "Off:", fr: "Éteinte :" })} {t(motif.eteinte)}
                    </p>
                )}
                {pied}
            </div>

            <div className="flex shrink-0 flex-col items-end justify-between gap-2">
                {/* L'interrupteur n'ouvre pas la modale. */}
                {!lecture && onBasculer && (
                    <span onClick={(e) => e.stopPropagation()} onKeyDown={(e) => e.stopPropagation()} className="flex items-center gap-2 text-xs text-muted-foreground">
                        {active ? t({ en: "On", fr: "Activée" }) : t({ en: "Off", fr: "Éteinte" })}
                        <Switch
                            aria-label={`${t({ en: "On", fr: "Activée" })} : ${t(motif.libelle)}${etape ? ` (${etape})` : ""}`}
                            checked={active}
                            onCheckedChange={onBasculer}
                        />
                    </span>
                )}
                <span className="text-[11px] text-muted-foreground">{t(ORIGINES[origine])}</span>
                <span className="text-[11px] text-muted-foreground">{derniere}</span>
                {ouvre && <ChevronRight className="h-4 w-4 text-muted-foreground transition group-hover:translate-x-0.5" />}
            </div>
        </div>
    );
};
