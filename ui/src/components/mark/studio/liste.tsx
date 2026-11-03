"use client";

import { useState } from "react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

/**
 * La seule liste déroulante de l'écran (Evan, 02/11) : le `Select` du design system, jamais le `<select>` du
 * navigateur. `vide` : le libellé de l'option sans valeur (Radix refuse une valeur vide, d'où la sentinelle).
 */
export type OptionListe = string | { valeur: string; libelle: React.ReactNode };
export const VALEUR_VIDE = "__vide__";

export function Liste({
    valeur,
    changer,
    options,
    vide,
    defaut,
    className = "",
    taille = "sm",
    placeholder,
}: {
    valeur?: string;
    changer?: (v: string) => void;
    options: OptionListe[];
    vide?: string;
    defaut?: string;
    className?: string;
    taille?: "sm" | "default";
    placeholder?: string;
}) {
    const premiere = options[0];
    const [interne, setInterne] = useState(defaut ?? (typeof premiere === "string" ? premiere : premiere?.valeur) ?? "");
    const v = valeur ?? interne;
    const poser = (x: string) => {
        const y = x === VALEUR_VIDE ? "" : x;
        if (changer) changer(y);
        else setInterne(y);
    };
    return (
        <Select value={v === "" ? VALEUR_VIDE : v} onValueChange={poser}>
            <SelectTrigger size={taille} className={`bg-background ${className}`}>
                <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
                {vide !== undefined && <SelectItem value={VALEUR_VIDE}>{vide}</SelectItem>}
                {options.map((o) =>
                    typeof o === "string" ? (
                        <SelectItem key={o} value={o}>
                            {o}
                        </SelectItem>
                    ) : (
                        <SelectItem key={o.valeur} value={o.valeur}>
                            {o.libelle}
                        </SelectItem>
                    ),
                )}
            </SelectContent>
        </Select>
    );
}
