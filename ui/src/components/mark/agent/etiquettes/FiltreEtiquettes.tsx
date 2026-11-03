"use client";

/**
 * [.mark] Le filtre « Étiquettes » de la liste des agents (U3, E30) : une pastille qui ouvre la liste des étiquettes
 * portées par au moins un agent actif (une étiquette sans agent disparaît du filtre). Plusieurs étiquettes cochées =
 * les agents qui portent AU MOINS UNE d'entre elles. Sans étiquette dans l'organisation, la pastille n'est pas dessinée.
 */
import { Tag } from "lucide-react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { basculer } from "./logique";

const T = {
    etiquettes: { en: "Labels", fr: "Étiquettes" },
    effacer: { en: "Clear", fr: "Effacer" },
} satisfies Record<string, Texte>;

export function FiltreEtiquettes({
    proposees,
    choisies,
    onChange,
}: {
    proposees: string[];
    choisies: string[];
    onChange: (choisies: string[]) => void;
}) {
    const { t } = useLangue();
    if (proposees.length === 0) return null;
    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="cursor-pointer gap-1.5 rounded-full hover:font-medium" data-filtre-etiquettes>
                    <Tag className="size-3.5" aria-hidden />
                    {t(T.etiquettes)}
                    {choisies.length > 0 && <span className="text-muted-foreground">{choisies.length}</span>}
                </Button>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-60 p-2">
                <ul className="max-h-64 overflow-auto">
                    {proposees.map((nom) => (
                        <li key={nom}>
                            <label className="flex cursor-pointer items-center gap-3 rounded px-2 py-2 text-sm hover:font-medium">
                                <Checkbox
                                    checked={choisies.includes(nom)}
                                    onCheckedChange={() => onChange(basculer(choisies, nom))}
                                    aria-label={nom}
                                />
                                {nom}
                            </label>
                        </li>
                    ))}
                </ul>
                {choisies.length > 0 && (
                    <Button variant="ghost" size="sm" className="mt-1 w-full cursor-pointer" onClick={() => onChange([])}>
                        {t(T.effacer)}
                    </Button>
                )}
            </PopoverContent>
        </Popover>
    );
}
