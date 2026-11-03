"use client";

/**
 * [.mark] K5 : les étiquettes d'un élément, comme la maquette (`ChoixEtiquettes`) : les posées avec leur croix, puis
 * « + Étiquette » qui propose les existantes ou crée. Sert à la fiche d'un élément (rangement) et à « Nouvel élément ».
 */
import { useState } from "react";

import type { VueEtiquette } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Etiquette } from "@/components/mark/studio/marques";
import { Input } from "@/components/ui/input";

export function ChoixEtiquettes({
    posees,
    existantes,
    changer,
}: {
    posees: string[];
    existantes: VueEtiquette[];
    changer: (etiquettes: string[]) => void;
}) {
    const { t } = useLangue();
    const [ajout, setAjout] = useState<string | null>(null);

    const poser = (nom: string) => {
        const propre = nom.trim();
        setAjout(null);
        if (!propre || posees.some((p) => p.toLowerCase() === propre.toLowerCase())) return;
        changer([...posees, propre]);
    };
    const proposees = existantes.filter((e) => !posees.includes(e.nom) && (ajout ?? "") !== "" && e.nom.toLowerCase().includes((ajout ?? "").toLowerCase()));

    return (
        <div className="flex flex-wrap items-center gap-2 text-sm">
            {posees.map((nom) => (
                <Etiquette key={nom} retirer={() => changer(posees.filter((p) => p !== nom))}>
                    {nom}
                </Etiquette>
            ))}
            {ajout === null ? (
                <button
                    type="button"
                    className="inline-flex h-6 cursor-pointer items-center rounded-full border border-dashed px-2 text-xs text-muted-foreground hover:font-medium hover:text-foreground"
                    onClick={() => setAjout("")}
                >
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
                        {ajout.trim() !== "" && !existantes.some((e) => e.nom.toLowerCase() === ajout.trim().toLowerCase()) && (
                            <button type="button" className="cursor-pointer px-3 py-1 text-left text-(--acc) hover:font-medium" onMouseDown={() => poser(ajout)}>
                                {t({ en: `Create « ${ajout.trim()} »`, fr: `Créer « ${ajout.trim()} » ` })}
                            </button>
                        )}
                    </span>
                </span>
            )}
        </div>
    );
}
