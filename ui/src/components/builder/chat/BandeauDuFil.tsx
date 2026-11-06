"use client";

/**
 * [.mark] K7 : le bandeau d'un chat, posé dans la barre du haut du cadre comme la maquette (`app/labo/builder/[id]`) : le titre du chat est
 * le dernier maillon du fil d'Ariane ; à droite l'état, la jauge de contexte en cercle, « Arrêter » (ou « Reprendre ») et « Ouvrir l'agent ».
 * Pour une conversation menée dans Claude Code : la marque « Claude Code · prénom » et « En direct » à la place de l'état.
 * La barre du haut appartient au cadre (`EnteteStudio`) ; ce composant ne fait que lui donner son contenu.
 */
import { Pause, Play } from "lucide-react";
import Link from "next/link";

import type { VueFil } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { EnDirect, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { EnteteStudio } from "@/components/mark/studio/shell-studio";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

import { useAdressesDuBuilder } from "./adresses";
import { libelleEtat } from "./SousAgents";

const T = {
    chat: { en: "Chat", fr: "Chat" },
    arreter: { en: "Stop", fr: "Arrêter" },
    reprendre: { en: "Resume", fr: "Reprendre" },
    ouvrir: { en: "Open the agent", fr: "Ouvrir l'agent" },
    contexte: { en: "Context", fr: "Contexte" },
    contexteInfo: {
        en: "Context used. At 70 %, the old turns are summarized and the real state (sheet, design document, pending changes, latest tests) is read again from disk.",
        fr: "Contexte utilisé. À 70 %, les anciens tours sont résumés et l'état réel (fiche, document de conception, changements en attente, derniers tests) est relu sur le disque.",
    },
} as const;

/** Le point de l'état : plein sombre qui pulse au travail, vert terminé, gris le reste (jetons du cadre, jamais d'orange). */
function EtatDuFil({ etat }: { etat: string }) {
    const { langue } = useLangue();
    const point = etat === "en_cours" ? "bg-foreground animate-pulse" : etat === "terminee" ? "bg-(--point-publie)" : etat === "erreur" ? "bg-(--pastille-urgente)" : "bg-foreground/25";
    return (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" data-etat-du-fil={etat}>
            <span className={`size-1.5 rounded-full ${point}`} aria-hidden />
            {libelleEtat(etat, langue)}
        </span>
    );
}

/** Le contexte du chat en cercle : la part de la fenêtre du cerveau déjà remplie (`fil.jauge`, de 0 à 1). */
export function JaugeContexte({ part, depense }: { part: number; depense?: string }) {
    const { t } = useLangue();
    const pct = Math.max(0, Math.min(100, Math.round(part * 100)));
    const r = 7;
    const tour = 2 * Math.PI * r;
    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <button type="button" aria-label={`${t(T.contexte)} ${pct} %`} className="inline-flex size-7 cursor-pointer items-center justify-center rounded-md hover:bg-muted">
                    <svg width="18" height="18" viewBox="0 0 18 18" className="-rotate-90" aria-hidden>
                        <circle cx="9" cy="9" r={r} fill="none" className="stroke-foreground/10" strokeWidth="2.2" />
                        <circle cx="9" cy="9" r={r} fill="none" className="stroke-foreground" strokeWidth="2.2" strokeLinecap="round" strokeDasharray={tour} strokeDashoffset={tour * (1 - pct / 100)} />
                    </svg>
                </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs text-xs leading-snug">
                {t(T.contexte)} : {pct} %. {t(T.contexteInfo)}
                {depense && <span className="mt-1 block text-muted-foreground">{depense}</span>}
            </TooltipContent>
        </Tooltip>
    );
}

export function BandeauDuFil({
    fil,
    enCours,
    lectureSeule,
    arreter,
    reprendre,
}: {
    fil: VueFil;
    enCours: boolean;
    lectureSeule: boolean;
    arreter: () => void;
    reprendre: () => void;
}) {
    const { t } = useLangue();
    const adresses = useAdressesDuBuilder();
    const claudeCode = fil.genre === "claude_code";
    const racine = adresses.client ? (adresses.nomDuClient ?? "") : "Labo";
    const hrefRacine = adresses.client ? adresses.liste.replace(/\/chat$/, "") : "/labo";
    return (
        <EnteteStudio
            miettes={[{ libelle: racine, href: hrefRacine }, { libelle: t(T.chat), href: adresses.liste }, { libelle: fil.titre }]}
            actions={
                <span className="flex items-center gap-2" data-bandeau-du-fil="">
                    {claudeCode ? (
                        <>
                            <MarqueClaudeCode par={fil.auteur} />
                            {fil.etat === "en_cours" ? <EnDirect /> : <EtatDuFil etat={fil.etat} />}
                        </>
                    ) : (
                        <>
                            <EtatDuFil etat={fil.etat} />
                            <JaugeContexte part={fil.jauge} depense={`${fil.jetons.toLocaleString()} · $${fil.cout.toFixed(2)}`} />
                            {!lectureSeule && fil.etat === "arretee" && (
                                <Button variant="ghost" size="sm" className="h-7 cursor-pointer" onClick={reprendre}>
                                    <Play className="size-3.5" aria-hidden /> {t(T.reprendre)}
                                </Button>
                            )}
                            {!lectureSeule && enCours && (
                                <Button variant="ghost" size="sm" className="h-7 cursor-pointer" onClick={arreter}>
                                    <Pause className="size-3.5" aria-hidden /> {t(T.arreter)}
                                </Button>
                            )}
                        </>
                    )}
                    {fil.workflow_id ? (
                        <Button variant="ghost" size="sm" className="h-7 cursor-pointer" asChild>
                            <Link href={`/agents/${fil.workflow_id}`}>{t(T.ouvrir)}</Link>
                        </Button>
                    ) : null}
                </span>
            }
        />
    );
}
