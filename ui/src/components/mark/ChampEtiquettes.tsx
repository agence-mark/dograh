"use client";

import { X } from "lucide-react";
import { useState } from "react";

import { Input } from "@/components/ui/input";

/**
 * [.mark] A list of strings, entered one value at a time.
 *
 * Why this exists rather than a text box: several Deepgram settings take
 * values that CONTAIN separators — `replace` takes `poil:poele`, `redact`
 * takes multi-word categories. "Type them comma-separated" is ambiguous the
 * moment a value has a colon or a space in it, and the client has no way to
 * find out which reading the server took.
 *
 * One entry per pastille removes the guess: what is on screen is what will be
 * sent, term by term.
 *
 * ⛔ Lives in a file of ours, imported in one line, like
 * `PerServiceModelOverride`. A conflict on an import line resolves itself; a
 * conflict inside their component does not.
 */

export interface ChampEtiquettesProps {
    valeurs: string[];
    onChange: (valeurs: string[]) => void;
    placeholder?: string;
    id?: string;
}

export function ChampEtiquettes({
    valeurs,
    onChange,
    placeholder,
    id,
}: ChampEtiquettesProps) {
    const [saisie, setSaisie] = useState("");

    const ajouter = (texte: string) => {
        // A paste of "a, b, c" becomes three entries: pasting a list is the
        // natural gesture, and splitting it here is what keeps the tag field
        // from being slower than the text box it replaces.
        const nouvelles = texte
            .split(",")
            .map(v => v.trim())
            .filter(v => v.length > 0)
            .filter(v => !valeurs.includes(v));
        if (nouvelles.length === 0) {
            setSaisie("");
            return;
        }
        onChange([...valeurs, ...nouvelles]);
        setSaisie("");
    };

    const retirer = (valeur: string) => {
        onChange(valeurs.filter(v => v !== valeur));
    };

    return (
        <div className="space-y-2">
            <Input
                id={id}
                type="text"
                value={saisie}
                placeholder={placeholder}
                onChange={e => setSaisie(e.target.value)}
                onKeyDown={e => {
                    if (e.key !== "Enter") return;
                    // Enter inside a form submits it. The whole configuration
                    // would be saved on the way to adding one term.
                    e.preventDefault();
                    ajouter(e.currentTarget.value);
                }}
                onBlur={e => {
                    // A term typed and left without pressing Enter is a term
                    // the client believes they added. Losing it silently is
                    // worse than adding it.
                    if (e.target.value.trim().length > 0) ajouter(e.target.value);
                }}
            />
            {valeurs.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                    {valeurs.map(valeur => (
                        <span
                            key={valeur}
                            data-etiquette={valeur}
                            className="inline-flex items-center gap-1 rounded-md border bg-muted/50 px-2 py-0.5 text-xs"
                        >
                            {valeur}
                            <button
                                type="button"
                                aria-label={`Remove ${valeur}`}
                                className="text-muted-foreground hover:text-foreground"
                                onClick={() => retirer(valeur)}
                            >
                                <X className="h-3 w-3" />
                            </button>
                        </span>
                    ))}
                </div>
            )}
        </div>
    );
}
