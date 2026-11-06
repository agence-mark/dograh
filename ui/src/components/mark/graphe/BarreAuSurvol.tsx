"use client";

/**
 * [.mark] Partie 3, sous-lot 20 : la petite barre au survol d'une étape (façon ElevenLabs, maquette `canevas.tsx`) : modifier,
 * dupliquer, relier, supprimer. La suppression passe toujours par une confirmation (`ConfirmerSuppression`) ; « Annuler » de la
 * barre du haut remet l'étape. La barre reste là tant que la souris est sur l'étape ou sur elle, et quand l'étape est choisie.
 */
import { NodeToolbar, Position } from "@xyflow/react";
import { Copy, Edit, Link2, Trash2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { ConfirmerSuppression } from "@/components/mark/studio/suppression-confirmee";
import { Button } from "@/components/ui/button";

const T = {
    modifier: { en: "Edit the step", fr: "Modifier l'étape" },
    dupliquer: { en: "Duplicate the step", fr: "Dupliquer l'étape" },
    relier: { en: "Link to another step", fr: "Relier à une autre étape" },
    supprimer: { en: "Delete the step", fr: "Supprimer l'étape" },
    titreSuppression: (nom: string): Texte => ({ en: `Delete "${nom}"?`, fr: `Supprimer « ${nom} » ?` }),
    descriptionSuppression: {
        en: "The step and its transitions leave the draft. « Undo » in the toolbar puts it back.",
        fr: "L'étape et ses transitions sortent du brouillon. « Annuler » dans la barre d'outils la remet.",
    },
} satisfies Record<string, Texte | ((nom: string) => Texte)>;

/** Le survol d'une étape : vrai tant que la souris est sur elle ou sur sa barre (un court délai évite le clignotement). */
export function useSurvolDeLEtape() {
    const [survol, setSurvol] = useState(false);
    const minuteur = useRef<ReturnType<typeof setTimeout> | null>(null);
    useEffect(() => () => void (minuteur.current && clearTimeout(minuteur.current)), []);
    const entrer = () => {
        if (minuteur.current) clearTimeout(minuteur.current);
        setSurvol(true);
    };
    const sortir = () => {
        if (minuteur.current) clearTimeout(minuteur.current);
        minuteur.current = setTimeout(() => setSurvol(false), 150);
    };
    return { survol, entrer, sortir };
}

export function BarreAuSurvol({
    visible,
    nom,
    peutDupliquer,
    peutSupprimer,
    lectureSeule = false,
    onModifier,
    onDupliquer,
    onRelier,
    onSupprimer,
    onEntrer,
    onSortir,
}: {
    visible: boolean;
    nom: string;
    peutDupliquer: boolean;
    peutSupprimer: boolean;
    lectureSeule?: boolean;
    onModifier: () => void;
    onDupliquer: () => void;
    onRelier: () => void;
    onSupprimer: () => void;
    onEntrer: () => void;
    onSortir: () => void;
}) {
    const { t } = useLangue();
    const [confirmer, setConfirmer] = useState(false);
    const bouton = "size-8 cursor-pointer";
    return (
        <>
            <NodeToolbar isVisible={visible || confirmer} position={Position.Right}>
                <div data-barre-au-survol className="nodrag flex flex-col gap-1" onMouseEnter={onEntrer} onMouseLeave={onSortir}>
                    <Button variant="outline" size="icon" className={bouton} title={t(T.modifier)} aria-label={t(T.modifier)} onClick={onModifier}>
                        <Edit />
                    </Button>
                    {!lectureSeule && peutDupliquer && (
                        <Button variant="outline" size="icon" className={bouton} title={t(T.dupliquer)} aria-label={t(T.dupliquer)} onClick={onDupliquer}>
                            <Copy />
                        </Button>
                    )}
                    {!lectureSeule && (
                        <Button variant="outline" size="icon" className={bouton} title={t(T.relier)} aria-label={t(T.relier)} onClick={onRelier}>
                            <Link2 />
                        </Button>
                    )}
                    {!lectureSeule && peutSupprimer && (
                        <Button variant="outline" size="icon" className={`${bouton} hover:text-destructive`} title={t(T.supprimer)} aria-label={t(T.supprimer)} onClick={() => setConfirmer(true)}>
                            <Trash2 />
                        </Button>
                    )}
                </div>
            </NodeToolbar>
            <ConfirmerSuppression
                ouvert={confirmer}
                titre={t(T.titreSuppression(nom))}
                description={t(T.descriptionSuppression)}
                onFermer={() => setConfirmer(false)}
                onConfirmer={() => {
                    setConfirmer(false);
                    onSupprimer();
                }}
            />
        </>
    );
}
