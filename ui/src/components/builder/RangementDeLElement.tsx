"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): where an element sits. Its sub-folder (one of the family, or none) and its labels
 * (existing ones, or « + Label » to create one on the spot). The cross only removes the label from THIS element. Filing never
 * makes a new version and never changes the status.
 */
import { useState } from "react";

import { ChoixEtiquettes } from "./ChoixEtiquettes";

import { rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost } from "@/client";
import type { Element as ElementBibliotheque, VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { detailFromError } from "@/lib/apiError";

interface Props {
    element: ElementBibliotheque;
    dossiers: string[];
    etiquettes: VueEtiquette[];
    onChange: (element: ElementBibliotheque) => void;
}

export function RangementDeLElement({ element, dossiers, etiquettes, onChange }: Props) {
    const { t } = useLangue();
    const [erreur, setErreur] = useState<string | null>(null);
    const posees = element.etiquettes ?? [];

    const ranger = async (corps: { dossier?: string; etiquettes?: string[] }) => {
        const reponse = await rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost({
            path: { famille: element.famille, slug: element.slug },
            body: corps,
        });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The element was not filed"));
            return;
        }
        setErreur(null);
        onChange(reponse.data);
    };

    return (
        <section className="space-y-2 text-sm" data-testid="rangement">
            <div className="flex flex-wrap items-center gap-3">
                <span className="text-muted-foreground">{t({ en: "Sub-folder", fr: "Sous-dossier" })}</span>
                <Liste
                    valeur={element.dossier ?? ""}
                    changer={(v) => void ranger({ dossier: v })}
                    vide={t({ en: "None", fr: "Aucun" })}
                    options={dossiers}
                    className="w-56"
                />
            </div>
            <ChoixEtiquettes posees={posees} existantes={etiquettes} changer={(liste) => void ranger({ etiquettes: liste })} />
            {erreur && (
                <p role="alert" className="text-destructive">
                    {erreur}
                </p>
            )}
        </section>
    );
}
