"use client";

/**
 * [.mark] The step's field labels (chantier agent-leger-greffier, lot E, P1).
 *
 * The record fields this step gathers, in order of priority: added from the agent's record,
 * removed, and reordered by drag and drop (or the arrows, for the keyboard). Saved as one
 * string, names separated by commas (`champs_etape` on the node), which the SDK and the MCP
 * validator read unchanged. Read by the code only when « Show the model what is known and what
 * is expected » is on in the agent's settings (fiabilite-orchestration, F19): then, at each turn,
 * the model reads « Still expected: … » and the step's tools wait until the list is complete. The graph editor is never translated (T3). ⛔ No trade word here: the names come from the agent's record.
 */
import { ArrowDown, ArrowUp, Filter, GripVertical, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { type Texte, useLangue } from "../langue/langue";

/**
 * Lot 7 de correctifs-apres-banc-commun (D-8) : la condition d'un champ de l'étape, sur la fiche. La forme des
 * conditions des phrases de fin figées : un champ de la fiche, rempli (``vaut`` absent) ou qui vaut une valeur.
 * Enregistrée dans ``conditions_de_champs`` des données de l'étape, lue par ``champs_conditionnels.py``.
 */
export interface ConditionDeChamp {
    champ: string;
    si: string;
    vaut?: string | null;
}

const TEXTES_CONDITION = {
    ouvrir: { en: "Expect this field only if…", fr: "N'attendre ce champ que si…" },
    retirer: { en: "Remove this condition", fr: "Retirer cette condition" },
    seulement: { en: "only if", fr: "seulement si" },
    champ: { en: "Record field", fr: "Champ de la fiche" },
    estRempli: { en: "is filled in", fr: "est rempli" },
    vaut: { en: "equals", fr: "vaut" },
    valeur: { en: "Value", fr: "Valeur" },
    inconnu: { en: "This field is not in the agent's record.", fr: "Ce champ n'est pas dans la fiche de l'agent." },
    aide: {
        en: "A field with a condition is expected, and waited for by the step's tools, only while its condition holds.",
        fr: "Un champ avec condition n'est attendu, et les outils de l'étape ne l'attendent, que tant que sa condition est tenue.",
    },
} satisfies Record<string, Texte>;

const REMPLI = "__rempli__";

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
    conditions,
    onConditionsChange,
}: {
    valeur: unknown;
    /** The fields of the agent's record, in its order. */
    champsFiche: string[];
    onChange: (valeur: string) => void;
    /** Lot 7: the conditions of the step's fields. Without the callback, the labels carry no condition control. */
    conditions?: ConditionDeChamp[];
    onConditionsChange?: (conditions: ConditionDeChamp[] | undefined) => void;
}) {
    const { t } = useLangue();
    // « vaut » choisi mais valeur pas encore écrite : le mode ne vit que dans l'écran, rien n'est enregistré.
    const [modeVaut, setModeVaut] = useState<string[]>(() => (conditions ?? []).filter((c) => c.vaut).map((c) => c.champ));
    const choisis = lireEtiquettes(valeur);
    const liste = conditions ?? [];
    const poserConditions = (suite: ConditionDeChamp[]) => onConditionsChange?.(suite.length > 0 ? suite : undefined);
    const majCondition = (champ: string, suite: Partial<ConditionDeChamp>) =>
        poserConditions(liste.map((c) => (c.champ === champ ? { ...c, ...suite } : c)));
    const ouvrirCondition = (champ: string) => {
        const autre = champsFiche.find((c) => c !== champ);
        if (autre === undefined || liste.some((c) => c.champ === champ)) return;
        poserConditions([...liste, { champ, si: autre }]);
    };
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
                        {onConditionsChange && (
                            <button
                                type="button"
                                aria-label={`${t(TEXTES_CONDITION.ouvrir)} (${nom})`}
                                className={liste.some((c) => c.champ === nom) ? "text-primary" : undefined}
                                onClick={() => ouvrirCondition(nom)}
                            >
                                <Filter className="h-3 w-3" />
                            </button>
                        )}
                        <button
                            type="button"
                            aria-label={`Remove ${nom}`}
                            onClick={() => {
                                poser(choisis.filter((c) => c !== nom));
                                if (liste.some((c) => c.champ === nom)) poserConditions(liste.filter((c) => c.champ !== nom));
                            }}
                        >
                            <X className="h-3 w-3" />
                        </button>
                    </li>
                ))}
            </ol>
            {onConditionsChange && liste.some((c) => choisis.includes(c.champ)) && (
                <div className="space-y-2" data-conditions-de-champs>
                    {liste
                        .filter((c) => choisis.includes(c.champ))
                        .map((c) => (
                            <div key={c.champ} className="flex flex-wrap items-center gap-2 rounded border p-2 text-xs" data-condition-du-champ={c.champ}>
                                <code>{c.champ}</code>
                                <span>{t(TEXTES_CONDITION.seulement)}</span>
                                <Select value={c.si} onValueChange={(v: string) => majCondition(c.champ, { si: v })}>
                                    <SelectTrigger id={`condition-si-${c.champ}`} className="w-44" aria-label={t(TEXTES_CONDITION.champ)}>
                                        <SelectValue placeholder={t(TEXTES_CONDITION.champ)} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {[...new Set([...champsFiche.filter((n) => n !== c.champ), c.si])].map((nom) => (
                                            <SelectItem key={nom} value={nom}>
                                                {nom}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <Select
                                    value={c.vaut || modeVaut.includes(c.champ) ? "vaut" : REMPLI}
                                    onValueChange={(v: string) => {
                                        setModeVaut((avant) => (v === "vaut" ? [...avant, c.champ] : avant.filter((n) => n !== c.champ)));
                                        if (v !== "vaut") majCondition(c.champ, { vaut: undefined });
                                    }}
                                >
                                    <SelectTrigger id={`condition-mode-${c.champ}`} className="w-32" aria-label={t(TEXTES_CONDITION.estRempli)}>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value={REMPLI}>{t(TEXTES_CONDITION.estRempli)}</SelectItem>
                                        <SelectItem value="vaut">{t(TEXTES_CONDITION.vaut)}</SelectItem>
                                    </SelectContent>
                                </Select>
                                {c.vaut || modeVaut.includes(c.champ) ? (
                                    <Input
                                        id={`condition-vaut-${c.champ}`}
                                        className="h-8 w-36"
                                        aria-label={t(TEXTES_CONDITION.valeur)}
                                        value={c.vaut ?? ""}
                                        onChange={(e) => majCondition(c.champ, { vaut: e.target.value.trim() === "" ? undefined : e.target.value })}
                                    />
                                ) : null}
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="ml-auto h-6 w-6"
                                    aria-label={`${t(TEXTES_CONDITION.retirer)} (${c.champ})`}
                                    onClick={() => poserConditions(liste.filter((x) => x.champ !== c.champ))}
                                >
                                    <X className="h-3 w-3" />
                                </Button>
                                {champsFiche.length > 0 && !champsFiche.includes(c.si) && (
                                    <p className="w-full text-destructive" role="alert">
                                        {t(TEXTES_CONDITION.inconnu)}
                                    </p>
                                )}
                            </div>
                        ))}
                    <p className="text-xs text-muted-foreground">{t(TEXTES_CONDITION.aide)}</p>
                </div>
            )}
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
