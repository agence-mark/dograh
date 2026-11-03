"use client";

/**
 * [.mark] La barre flottante du canevas (E36) : Prompt général · + Nœud · Bibliothèque · zoom · Ajuster · Ranger.
 * Elle remplace les deux groupes de boutons dans les coins ; le moteur (React Flow) et ses gestes ne changent pas.
 * En lecture seule (version passée), seuls le zoom et « Ajuster » restent. « Bibliothèque » mène à la bibliothèque du
 * Labo ; il n'est pas proposé ailleurs (un client ne la modifie pas).
 */
import { BookOpen, BrushCleaning, Maximize2, Minus, Plus, ScrollText } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const T = {
    promptGeneral: { en: "General prompt", fr: "Prompt général" },
    noeud: { en: "Node", fr: "Nœud" },
    ajouterNoeud: { en: "Add a node", fr: "Ajouter un nœud" },
    bibliotheque: { en: "Library", fr: "Bibliothèque" },
    zoomAvant: { en: "Zoom in", fr: "Zoom avant" },
    zoomArriere: { en: "Zoom out", fr: "Zoom arrière" },
    ajuster: { en: "Fit the view", fr: "Ajuster" },
    ranger: { en: "Tidy up", fr: "Ranger" },
} satisfies Record<string, Texte>;

export function BarreCanevas({
    lectureSeule,
    onPromptGeneral,
    onAjouter,
    onZoomAvant,
    onZoomArriere,
    onAjuster,
    onRanger,
    bibliothequeHref,
}: {
    lectureSeule: boolean;
    onPromptGeneral: () => void;
    onAjouter: () => void;
    onZoomAvant: () => void;
    onZoomArriere: () => void;
    onAjuster: () => void;
    onRanger: () => void;
    /** Présent seulement au Labo. */
    bibliothequeHref?: string;
}) {
    const { t } = useLangue();
    const bouton = (libelle: string, icone: React.ReactNode, onClick: () => void, avecTexte = false) => (
        <Tooltip>
            <TooltipTrigger asChild>
                <Button
                    type="button"
                    variant="ghost"
                    size={avecTexte ? "sm" : "icon"}
                    className={`cursor-pointer hover:font-medium ${avecTexte ? "gap-1.5" : "size-8"}`}
                    aria-label={libelle}
                    onClick={onClick}
                >
                    {icone}
                    {avecTexte && <span>{libelle}</span>}
                </Button>
            </TooltipTrigger>
            <TooltipContent side="top">{libelle}</TooltipContent>
        </Tooltip>
    );
    return (
        <TooltipProvider>
            <div
                className="absolute bottom-6 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-full border bg-background px-2 py-1 shadow-md"
                data-barre-canevas
            >
                {!lectureSeule && (
                    <>
                        {bouton(t(T.promptGeneral), <ScrollText className="size-4" aria-hidden />, onPromptGeneral, true)}
                        {bouton(t(T.noeud), <Plus className="size-4" aria-hidden />, onAjouter, true)}
                        {bibliothequeHref && (
                            <Button asChild variant="ghost" size="sm" className="cursor-pointer gap-1.5 hover:font-medium">
                                <Link href={bibliothequeHref} aria-label={t(T.bibliotheque)}>
                                    <BookOpen className="size-4" aria-hidden />
                                    {t(T.bibliotheque)}
                                </Link>
                            </Button>
                        )}
                        <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                    </>
                )}
                {bouton(t(T.zoomArriere), <Minus className="size-4" aria-hidden />, onZoomArriere)}
                {bouton(t(T.zoomAvant), <Plus className="size-4" aria-hidden />, onZoomAvant)}
                {bouton(t(T.ajuster), <Maximize2 className="size-4" aria-hidden />, onAjuster)}
                {!lectureSeule && bouton(t(T.ranger), <BrushCleaning className="size-4" aria-hidden />, onRanger)}
            </div>
        </TooltipProvider>
    );
}
