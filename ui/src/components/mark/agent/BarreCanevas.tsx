"use client";

/**
 * [.mark] La barre flottante du canevas (E36), reprise de la maquette (`canevas.tsx`, K2) : Prompt général · Nœud ⌄ ·
 * Bibliothèque · zoom (− 80 % +) · Ajuster · « ! ». Le moteur (React Flow) et ses gestes ne changent pas. En lecture seule
 * (version passée), seuls le zoom et « Ajuster » restent. « Bibliothèque » mène à la bibliothèque du Labo ; elle n'est pas
 * proposée ailleurs. Le menu « Nœud » liste les types que le serveur sait poser (les mêmes que l'ancien panneau d'ajout).
 */
import { Maximize2, Minus, Plus } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { useNodeSpecs } from "@/components/flow/renderer";
import { specsDuMenu } from "@/components/flow/menu-noeuds";
import { libelleDuType } from "@/components/flow/nodes/GenericNode";
import type { FlowNode, NodeType } from "@/components/flow/types";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

const T = {
    promptGeneral: { en: "General prompt", fr: "Prompt général" },
    noeud: { en: "Node", fr: "Nœud" },
    bibliotheque: { en: "Library", fr: "Bibliothèque" },
    zoomAvant: { en: "Zoom in", fr: "Zoom avant" },
    zoomArriere: { en: "Zoom out", fr: "Zoom arrière" },
    ajuster: { en: "Fit the view", fr: "Ajuster" },
    ranger: { en: "Tidy up the nodes", fr: "Ranger les nœuds" },
    limite: { en: "limit reached for this agent", fr: "limite atteinte pour cet agent" },
    aide: {
        en: "Double-click a node to open it; click a condition to edit it. The black dot of the general prompt shows changes from the builder.",
        fr: "Double-clic sur un nœud pour l'ouvrir ; clic sur une condition de passage pour la modifier. Le point noir du prompt général signale un changement du builder.",
    },
} satisfies Record<string, Texte>;

export function BarreCanevas({
    lectureSeule,
    zoom,
    changementDuBuilder,
    noeuds,
    onPromptGeneral,
    onAjouter,
    onZoomAvant,
    onZoomArriere,
    onAjuster,
    onRanger,
    bibliothequeHref,
}: {
    lectureSeule: boolean;
    /** Le zoom en pour cent, tel que le canevas le tient. */
    zoom: number;
    /** Le builder a posé un changement non relu. */
    changementDuBuilder: boolean;
    noeuds: FlowNode[];
    onPromptGeneral: () => void;
    onAjouter: (type: NodeType) => void;
    onZoomAvant: () => void;
    onZoomArriere: () => void;
    onAjuster: () => void;
    onRanger: () => void;
    /** Présent seulement au Labo. */
    bibliothequeHref?: string;
}) {
    const { t, langue } = useLangue();
    const { specs } = useNodeSpecs();
    const comptes = useMemo(() => {
        const c = new Map<string, number>();
        noeuds.forEach((n) => c.set(n.type, (c.get(n.type) ?? 0) + 1));
        return c;
    }, [noeuds]);
    const proposes = useMemo(() => specsDuMenu(specs), [specs]);

    return (
        <div
            className="absolute bottom-5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-1 rounded-xl border bg-background p-1 shadow-sm"
            data-barre-canevas
        >
            {!lectureSeule && (
                <>
                    <Button variant="ghost" size="sm" className="h-8" onClick={onPromptGeneral}>
                        {changementDuBuilder && <span className="size-1.5 rounded-full bg-foreground" />} {t(T.promptGeneral)}
                    </Button>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm" className="h-8">
                                <Plus className="size-3.5" /> {t(T.noeud)}
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                            {proposes.map((spec) => {
                                const max = spec.graph_constraints?.max_instances;
                                const atteint = max != null && (comptes.get(spec.name) ?? 0) >= max;
                                return (
                                    <DropdownMenuItem
                                        key={spec.name}
                                        disabled={atteint}
                                        title={atteint ? `${libelleDuType(spec, langue)} : ${t(T.limite)}` : undefined}
                                        onClick={() => onAjouter(spec.name as NodeType)}
                                    >
                                        {libelleDuType(spec, langue)}
                                    </DropdownMenuItem>
                                );
                            })}
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={onRanger}>{t(T.ranger)}</DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                    {bibliothequeHref && (
                        <Button variant="ghost" size="sm" className="h-8" asChild>
                            <Link href={bibliothequeHref}>{t(T.bibliotheque)}</Link>
                        </Button>
                    )}
                    <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                </>
            )}
            <Button variant="ghost" size="icon" className="size-8" aria-label={t(T.zoomArriere)} onClick={onZoomArriere}>
                <Minus className="size-3.5" />
            </Button>
            <span className="w-10 text-center text-xs tabular-nums text-muted-foreground">{zoom} %</span>
            <Button variant="ghost" size="icon" className="size-8" aria-label={t(T.zoomAvant)} onClick={onZoomAvant}>
                <Plus className="size-3.5" />
            </Button>
            <Button variant="ghost" size="icon" className="size-8" title={t(T.ajuster)} aria-label={t(T.ajuster)} onClick={onAjuster}>
                <Maximize2 className="size-3.5" />
            </Button>
            {!lectureSeule && (
                <span className="pl-1 pr-1.5">
                    <Info>{t(T.aide)}</Info>
                </span>
            )}
        </div>
    );
}
