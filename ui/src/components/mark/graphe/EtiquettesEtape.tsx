"use client";

/**
 * [.mark] The step's field labels (chantier agent-leger-greffier, lot E, P1).
 *
 * The record fields this step gathers, in order of priority: added from the agent's record,
 * removed, and reordered by drag and drop (or the arrows, for the keyboard). Saved as one
 * string, names separated by commas (`champs_etape` on the node), which the SDK and the MCP
 * validator read unchanged. Read by the code only when « Step field labels » is on in the
 * agent's settings: then, at each turn, the model is reminded of the next missing ones, as a
 * suggestion. The graph editor is never translated (T3). ⛔ No trade word here: the names come from the agent's record.
 */
import { ArrowDown, ArrowUp, GripVertical, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";

export const lireEtiquettes = (valeur: unknown): string[] =>
    String(valeur ?? "")
        .split(",")
        .map((c) => c.trim())
        .filter((c) => c !== "");

export const ecrireEtiquettes = (noms: string[]): string => noms.join(", ");

export function EtiquettesEtape({
    valeur,
    champsFiche,
    onChange,
}: {
    valeur: unknown;
    /** The fields of the agent's record, in its order. */
    champsFiche: string[];
    onChange: (valeur: string) => void;
}) {
    const choisis = lireEtiquettes(valeur);
    const [deplace, setDeplace] = useState<number | null>(null);
    const poser = (noms: string[]) => onChange(ecrireEtiquettes(noms));
    const deplacer = (de: number, vers: number) => {
        if (vers < 0 || vers >= choisis.length || de === vers) return;
        const suite = [...choisis];
        const [nom] = suite.splice(de, 1);
        suite.splice(vers, 0, nom);
        poser(suite);
    };
    const disponibles = champsFiche.filter((c) => !choisis.includes(c));
    const inconnus = choisis.filter((c) => champsFiche.length > 0 && !champsFiche.includes(c));

    return (
        <div className="space-y-2" data-testid="etiquettes-etape">
            <ol className="flex flex-wrap gap-2">
                {choisis.map((nom, i) => (
                    <li
                        key={nom}
                        draggable
                        onDragStart={() => setDeplace(i)}
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={() => {
                            if (deplace !== null) deplacer(deplace, i);
                            setDeplace(null);
                        }}
                        data-etiquette={nom}
                        className="flex items-center gap-1 rounded border bg-muted/40 px-2 py-1 text-xs"
                    >
                        <GripVertical className="h-3 w-3 cursor-grab text-muted-foreground" aria-hidden />
                        <span className="font-medium">{i + 1}.</span>
                        <code>{nom}</code>
                        <button type="button" aria-label={`Move ${nom} up`} onClick={() => deplacer(i, i - 1)}>
                            <ArrowUp className="h-3 w-3" />
                        </button>
                        <button type="button" aria-label={`Move ${nom} down`} onClick={() => deplacer(i, i + 1)}>
                            <ArrowDown className="h-3 w-3" />
                        </button>
                        <button type="button" aria-label={`Remove ${nom}`} onClick={() => poser(choisis.filter((c) => c !== nom))}>
                            <X className="h-3 w-3" />
                        </button>
                    </li>
                ))}
            </ol>
            {disponibles.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {disponibles.map((nom) => (
                        <Button
                            key={nom}
                            type="button"
                            variant="outline"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() => poser([...choisis, nom])}
                        >
                            + {nom}
                        </Button>
                    ))}
                </div>
            )}
            {champsFiche.length === 0 && (
                <p className="text-xs text-muted-foreground">
                    {"The agent's record has no field yet (agent settings, Call data)."}
                </p>
            )}
            {inconnus.length > 0 && (
                <p className="text-xs text-destructive" role="alert">
                    {`Not a field of the record, ignored by the code: ${inconnus.join(", ")}.`}
                </p>
            )}
        </div>
    );
}
