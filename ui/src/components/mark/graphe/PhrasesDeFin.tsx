"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A17) : les phrases de fin du nœud de fin du principal.
 *
 * Seul le code clôt l'appel, et la phrase de fin est FIGÉE, choisie par le code d'après la fiche de
 * l'appel : une liste ordonnée « si [champ de la fiche] [est rempli / vaut …] → cette phrase », la
 * dernière ligne, sans condition, étant la phrase par défaut. Cette liste REMPLACE la zone de texte
 * du nœud (on remplace, on n'ajoute pas) ; un nœud de fin sans liste garde sa zone de texte
 * d'aujourd'hui (agent seul). Les champs proposés sont ceux de la fiche de l'agent.
 *
 * Enregistré dans ``fins`` des données du nœud : ``[{ champ?, vaut?, phrase }]`` (le même format que
 * ``FinFigeeDTO``, lu par ``services/groupe/passations.py``). Aucune ligne n'est enregistrée vide
 * (le serveur refuse une phrase vide) : une ligne sans phrase reste à l'écran, hors de ce qui part.
 */
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";

export interface FinFigee {
    champ?: string | null;
    vaut?: string | null;
    phrase: string;
}

const TEXTES = {
    libelle: { en: "Closing sentences", fr: "Phrases de fin" },
    aide: {
        en: "The code says the first sentence whose condition on the call record holds, as it is written, with no turn of the model. The last line has no condition: it is the default sentence.",
        fr: "Le code dit la première phrase dont la condition sur la fiche est vraie, telle qu'elle est écrite, sans tour de modèle. La dernière ligne n'a pas de condition : c'est la phrase par défaut.",
    },
    si: { en: "If", fr: "Si" },
    champ: { en: "Record field", fr: "Champ de la fiche" },
    estRempli: { en: "is filled in", fr: "est rempli" },
    vaut: { en: "equals", fr: "vaut" },
    valeur: { en: "Value", fr: "Valeur" },
    phrase: { en: "Sentence", fr: "Phrase" },
    defaut: { en: "Otherwise (default sentence)", fr: "Sinon (phrase par défaut)" },
    ajouter: { en: "Add a condition", fr: "Ajouter une condition" },
    retirer: { en: "Remove this line", fr: "Retirer cette ligne" },
    monter: { en: "Move up", fr: "Monter" },
    descendre: { en: "Move down", fr: "Descendre" },
    phraseVide: { en: "A sentence cannot be empty: this line is not saved.", fr: "Une phrase ne peut pas être vide : cette ligne n'est pas enregistrée." },
    champInconnu: { en: "This field is not in the agent's record.", fr: "Ce champ n'est pas dans la fiche de l'agent." },
} satisfies Record<string, Texte>;

const REMPLI = "__rempli__";

interface Ligne {
    /** Une clé stable pour la liste (jamais enregistrée). */
    cle: number;
    champ: string;
    mode: "rempli" | "vaut";
    vaut: string;
    phrase: string;
}

const depuis = (fins: FinFigee[] | null | undefined): { conditions: Ligne[]; defaut: string } => {
    const lignes = Array.isArray(fins) ? fins : [];
    const defaut = [...lignes].reverse().find((f) => !f.champ)?.phrase ?? "";
    const conditions = lignes
        .filter((f) => Boolean(f.champ))
        .map((f, i) => ({
            cle: i,
            champ: String(f.champ),
            mode: f.vaut ? ("vaut" as const) : ("rempli" as const),
            vaut: f.vaut ?? "",
            phrase: f.phrase,
        }));
    return { conditions, defaut };
};

/** Ce qui est enregistré : les lignes à phrase non vide, puis la phrase par défaut (si elle est écrite). */
export const versFins = (conditions: Ligne[], defaut: string): FinFigee[] => [
    ...conditions
        .filter((l) => l.phrase.trim() !== "" && l.champ !== "")
        .map((l) => ({ champ: l.champ, ...(l.mode === "vaut" && l.vaut.trim() !== "" ? { vaut: l.vaut.trim() } : {}), phrase: l.phrase.trim() })),
    ...(defaut.trim() !== "" ? [{ phrase: defaut.trim() }] : []),
];

export const PhrasesDeFin = ({
    fins,
    champsFiche,
    onChange,
}: {
    fins: FinFigee[] | null | undefined;
    /** Les champs de la fiche de l'agent, dans son ordre. */
    champsFiche: string[];
    onChange: (fins: FinFigee[] | undefined) => void;
}) => {
    const { t } = useLangue();
    const initial = depuis(fins);
    const [conditions, setConditions] = useState<Ligne[]>(initial.conditions);
    const [defaut, setDefaut] = useState(initial.defaut);
    const [prochaine, setProchaine] = useState(initial.conditions.length);

    // Ce qui part vers les données du nœud : la liste valide, ou rien (la zone de texte d'avant reprend).
    useEffect(() => {
        const liste = versFins(conditions, defaut);
        onChange(liste.length > 0 ? liste : undefined);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conditions, defaut]);

    const maj = (cle: number, suite: Partial<Ligne>) =>
        setConditions((avant) => avant.map((l) => (l.cle === cle ? { ...l, ...suite } : l)));
    const deplacer = (i: number, vers: number) =>
        setConditions((avant) => {
            if (vers < 0 || vers >= avant.length) return avant;
            const suite = [...avant];
            const [ligne] = suite.splice(i, 1);
            suite.splice(vers, 0, ligne);
            return suite;
        });

    return (
        <ChampReglage cle="fins" libelle={TEXTES.libelle} aides={[TEXTES.aide]}>
            <div className="space-y-3" data-liste="phrases-de-fin">
                {conditions.map((ligne, i) => (
                    <div key={ligne.cle} className="space-y-2 rounded-md border p-3" data-ligne-de-fin={i}>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="text-xs font-medium">{t(TEXTES.si)}</span>
                            <Select value={ligne.champ} onValueChange={(v: string) => maj(ligne.cle, { champ: v })}>
                                <SelectTrigger id={`fin-champ-${ligne.cle}`} className="w-48" aria-label={t(TEXTES.champ)}>
                                    <SelectValue placeholder={t(TEXTES.champ)} />
                                </SelectTrigger>
                                <SelectContent>
                                    {[...new Set([...champsFiche, ...(ligne.champ && !champsFiche.includes(ligne.champ) ? [ligne.champ] : [])])].map(
                                        (nom) => (
                                            <SelectItem key={nom} value={nom}>
                                                {nom}
                                            </SelectItem>
                                        ),
                                    )}
                                </SelectContent>
                            </Select>
                            <Select value={ligne.mode === "vaut" ? "vaut" : REMPLI} onValueChange={(v: string) => maj(ligne.cle, { mode: v === "vaut" ? "vaut" : "rempli" })}>
                                <SelectTrigger id={`fin-mode-${ligne.cle}`} className="w-36" aria-label={t(TEXTES.estRempli)}>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value={REMPLI}>{t(TEXTES.estRempli)}</SelectItem>
                                    <SelectItem value="vaut">{t(TEXTES.vaut)}</SelectItem>
                                </SelectContent>
                            </Select>
                            {ligne.mode === "vaut" && (
                                <Input
                                    id={`fin-vaut-${ligne.cle}`}
                                    className="w-40"
                                    aria-label={t(TEXTES.valeur)}
                                    value={ligne.vaut}
                                    onChange={(e) => maj(ligne.cle, { vaut: e.target.value })}
                                />
                            )}
                            <span className="ml-auto flex items-center gap-1">
                                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(TEXTES.monter)} onClick={() => deplacer(i, i - 1)}>
                                    <ArrowUp className="h-3.5 w-3.5" />
                                </Button>
                                <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(TEXTES.descendre)} onClick={() => deplacer(i, i + 1)}>
                                    <ArrowDown className="h-3.5 w-3.5" />
                                </Button>
                                <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    aria-label={t(TEXTES.retirer)}
                                    onClick={() => setConditions((avant) => avant.filter((l) => l.cle !== ligne.cle))}
                                >
                                    <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                            </span>
                        </div>
                        {ligne.champ !== "" && champsFiche.length > 0 && !champsFiche.includes(ligne.champ) && (
                            <p className="text-xs text-destructive">{t(TEXTES.champInconnu)}</p>
                        )}
                        <Input
                            id={`fin-phrase-${ligne.cle}`}
                            aria-label={t(TEXTES.phrase)}
                            maxLength={1000}
                            value={ligne.phrase}
                            onChange={(e) => maj(ligne.cle, { phrase: e.target.value })}
                        />
                        {ligne.phrase.trim() === "" && <p className="text-xs text-destructive">{t(TEXTES.phraseVide)}</p>}
                    </div>
                ))}
                <div className="space-y-2 rounded-md border border-dashed p-3" data-ligne-de-fin="defaut">
                    <span className="text-xs font-medium">{t(TEXTES.defaut)}</span>
                    <Input
                        id="fin-phrase-defaut"
                        aria-label={t(TEXTES.defaut)}
                        maxLength={1000}
                        value={defaut}
                        onChange={(e) => setDefaut(e.target.value)}
                    />
                </div>
                <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                        setConditions((avant) => [...avant, { cle: prochaine, champ: champsFiche[0] ?? "", mode: "rempli", vaut: "", phrase: "" }]);
                        setProchaine((n) => n + 1);
                    }}
                >
                    <Plus className="mr-2 h-3.5 w-3.5" />
                    {t(TEXTES.ajouter)}
                </Button>
            </div>
        </ChampReglage>
    );
};
