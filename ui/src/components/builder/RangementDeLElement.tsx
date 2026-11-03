"use client";

/**
 * [.mark] builder partie 2, E1 (U7, E49): where an element sits. Its sub-folder (one of the family, or none) and its labels
 * (existing ones, or « + Label » to create one on the spot). The cross only removes the label from THIS element. Filing never
 * makes a new version and never changes the status.
 */
import { useState } from "react";

import { rangerUnElementApiV1BuilderBibliothequeFamilleSlugRangementPost } from "@/client";
import type { Element as ElementBibliotheque, VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Etiquette } from "@/components/mark/studio/marques";
import { Input } from "@/components/ui/input";
import { detailFromError } from "@/lib/apiError";

interface Props {
    element: ElementBibliotheque;
    dossiers: string[];
    etiquettes: VueEtiquette[];
    onChange: (element: ElementBibliotheque) => void;
}

export function RangementDeLElement({ element, dossiers, etiquettes, onChange }: Props) {
    const { t } = useLangue();
    const [ajout, setAjout] = useState<string | null>(null);
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

    const poser = (nom: string) => {
        const propre = nom.trim();
        setAjout(null);
        if (!propre || posees.some((p) => p.toLowerCase() === propre.toLowerCase())) return;
        void ranger({ etiquettes: [...posees, propre] });
    };
    const proposees = etiquettes.filter((e) => !posees.includes(e.nom) && (ajout ?? "") !== "" && e.nom.toLowerCase().includes((ajout ?? "").toLowerCase()));

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
            <div className="flex flex-wrap items-center gap-2">
                <span className="text-muted-foreground">{t({ en: "Labels", fr: "Étiquettes" })}</span>
                {posees.map((nom) => (
                    <Etiquette key={nom} retirer={() => void ranger({ etiquettes: posees.filter((p) => p !== nom) })}>
                        {nom}
                    </Etiquette>
                ))}
                {ajout === null ? (
                    <button type="button" className="cursor-pointer text-(--acc) hover:font-medium" onClick={() => setAjout("")}>
                        + {t({ en: "Label", fr: "Étiquette" })}
                    </button>
                ) : (
                    <span className="relative">
                        <Input
                            autoFocus
                            value={ajout}
                            aria-label={t({ en: "Label to add", fr: "Étiquette à poser" })}
                            className="h-7 w-44"
                            onChange={(e) => setAjout(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") poser(ajout);
                                if (e.key === "Escape") setAjout(null);
                            }}
                        />
                        <span className="absolute top-8 left-0 z-10 flex flex-col rounded-md border bg-background text-left shadow-sm">
                            {proposees.slice(0, 6).map((e) => (
                                <button key={e.nom} type="button" className="cursor-pointer px-3 py-1 text-left hover:font-medium" onMouseDown={() => poser(e.nom)}>
                                    {e.nom}
                                </button>
                            ))}
                            {ajout.trim() !== "" && !etiquettes.some((e) => e.nom.toLowerCase() === ajout.trim().toLowerCase()) && (
                                <button type="button" className="cursor-pointer px-3 py-1 text-left text-(--acc) hover:font-medium" onMouseDown={() => poser(ajout)}>
                                    {t({ en: `Create « ${ajout.trim()} »`, fr: `Créer « ${ajout.trim()} »` })}
                                </button>
                            )}
                        </span>
                    </span>
                )}
            </div>
            {erreur && (
                <p role="alert" className="text-destructive">
                    {erreur}
                </p>
            )}
        </section>
    );
}
