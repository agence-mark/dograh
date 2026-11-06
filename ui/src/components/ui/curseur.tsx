"use client";

import type { CSSProperties, InputHTMLAttributes } from "react";

/**
 * [.mark] T5 (Evan, 05/11) : le curseur à glisser COMMUN. Rail fin sans bordure, partie remplie de la même finesse,
 * petit point cerclé du fond de page, anneau de focus au clavier. Le style vit dans `globals.css` (classe `curseur`) ;
 * ce composant calcule seulement la part remplie. Tout curseur de l'écran passe ici (un test refuse `type="range"` ailleurs).
 */
export function Curseur({
    min = 0,
    max = 100,
    value,
    className = "",
    style,
    ...reste
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "min" | "max"> & { min?: number; max?: number; value: number }) {
    const pct = max > min ? ((Math.min(Math.max(Number(value), min), max) - min) / (max - min)) * 100 : 0;
    return (
        <input
            type="range"
            min={min}
            max={max}
            value={value}
            data-curseur
            className={`curseur ${className}`}
            style={{ ...style, "--pct": `${pct}%` } as CSSProperties}
            {...reste}
        />
    );
}
