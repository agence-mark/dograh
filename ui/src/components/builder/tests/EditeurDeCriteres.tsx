"use client";

/**
 * [.mark] U3 (E47): the criteria of a test, one line each. Every list is READ in the agent or the library (steps, tools,
 * outcomes, sheet fields); the type list is the one of the code (`CRITERES`). No `<select>` of the browser (E48).
 */
import { Plus, X } from "lucide-react";

import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

import { type ChampDeCritere, CHAMPS, CRITERES } from "./libelles";
import type { LigneDeCritere } from "./NouveauTest";
import type { RessourcesDeTest } from "./types";

const liste = (v: unknown) =>
    Array.isArray(v) ? v.map(String).join(", ") : String(v ?? "");

/** A criterion of the server, as a form line (the way back of `critereDeLaLigne`). */
export function ligneDuCritere(c: Record<string, unknown> & { type: string }): LigneDeCritere {
    const valeurs: LigneDeCritere["valeurs"] = {};
    for (const champ of CRITERES[c.type]?.champs ?? []) {
        if (champ === "ne_doit_pas_etre_appele") valeurs[champ] = c.appele === false;
        else valeurs[champ] = liste(c[champ]);
    }
    return { type: c.type, valeurs };
}

export const ligneVide = (type = "texte_absent"): LigneDeCritere => ({
    type,
    valeurs: Object.fromEntries((CRITERES[type]?.champs ?? []).map((ch) => [ch, ch === "ne_doit_pas_etre_appele" ? false : ""])),
});

/** The list that suits a field, when the agent knows its values. */
function optionsDuChamp(champ: ChampDeCritere, type: string, r: RessourcesDeTest | null): string[] | null {
    if (!r) return null;
    if (champ === "nom") return r.outils;
    if (champ === "attendue") return type === "etape" ? r.etapes : type === "issue" ? r.issues : null;
    return null;
}

/** « Dans cet ordre » : les outils attendus, un par ligne, numérotés (d'autres outils peuvent s'intercaler entre eux). */
function OrdreDesOutils({ noms, outils, changer }: { noms: string[]; outils: string[]; changer: (noms: string[]) => void }) {
    const { t } = useLangue();
    const lignes = noms.length >= 2 ? noms : [...noms, ...Array(2 - noms.length).fill("")];
    return (
        <ol className="space-y-1.5" data-testid="ordre-des-outils" aria-label={t({ en: "Tools, in order", fr: "Outils, dans l'ordre" })}>
            {lignes.map((nom, k) => (
                <li key={k} className="flex items-center gap-2">
                    <span className="w-5 text-xs text-muted-foreground">{k + 1}.</span>
                    {outils.length > 0 ? (
                        <Liste
                            className="flex-1"
                            valeur={nom}
                            placeholder={t({ en: "Tool name", fr: "Nom de l'outil" })}
                            changer={(v) => changer(lignes.map((x, j) => (j === k ? v : x)))}
                            options={nom && !outils.includes(nom) ? [nom, ...outils] : outils}
                        />
                    ) : (
                        <Input
                            className="h-8"
                            aria-label={`${t({ en: "Tool", fr: "Outil" })} ${k + 1}`}
                            value={nom}
                            onChange={(e) => changer(lignes.map((x, j) => (j === k ? e.target.value : x)))}
                        />
                    )}
                    {lignes.length > 2 && (
                        <button
                            type="button"
                            aria-label={t({ en: "Remove this tool", fr: "Retirer cet outil" })}
                            onClick={() => changer(lignes.filter((_, j) => j !== k))}
                            className="cursor-pointer text-muted-foreground hover:text-foreground"
                        >
                            <X className="size-3.5" />
                        </button>
                    )}
                </li>
            ))}
            {lignes.length < 10 && (
                <li>
                    <Button variant="ghost" size="sm" className="-ml-2" onClick={() => changer([...lignes, ""])}>
                        <Plus className="size-3.5" /> {t({ en: "Next tool", fr: "Outil suivant" })}
                    </Button>
                </li>
            )}
        </ol>
    );
}

export function EditeurDeCriteres({
    lignes,
    changer,
    ressources,
    types,
}: {
    lignes: LigneDeCritere[];
    changer: (l: LigneDeCritere[]) => void;
    ressources: RessourcesDeTest | null;
    /** The criterion types offered (a tool-call test offers only the tool). */
    types?: string[];
}) {
    const { t } = useLangue();
    const offerts = types ?? Object.keys(CRITERES).filter((k) => !CRITERES[k].ancien);
    const maj = (i: number, l: LigneDeCritere) => changer(lignes.map((x, k) => (k === i ? l : x)));
    // K3 (maquette `LigneCritere`) : un critère = son titre avec son « ! » et sa croix, ses paramètres dessous, pleine largeur ;
    // « + Ajouter un critère » ouvre la liste des types (12 au plus).
    return (
        <div data-testid="criteres-du-test">
            <div className="divide-y border-y">
                {lignes.map((c, i) => (
                    <div key={i} className="space-y-2 py-3">
                        <div className="flex items-center gap-2 text-sm">
                            <span className="flex flex-1 items-center gap-1.5 font-medium">{t(CRITERES[c.type]?.libelle ?? { en: c.type, fr: c.type })}</span>
                            <button
                                type="button"
                                aria-label={t({ en: "Remove the criterion", fr: "Retirer le critère" })}
                                onClick={() => changer(lignes.filter((_, k) => k !== i))}
                                className="cursor-pointer text-muted-foreground hover:text-foreground"
                            >
                                <X className="size-4" />
                            </button>
                        </div>
                        {(CRITERES[c.type]?.champs ?? []).map((ch) => {
                            const options = optionsDuChamp(ch, c.type, ressources);
                            if (ch === "ne_doit_pas_etre_appele")
                                return (
                                    <label key={ch} className="flex items-center gap-2 text-sm">
                                        <Switch
                                            checked={Boolean(c.valeurs[ch])}
                                            onCheckedChange={(v) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: v } })}
                                            aria-label={t(CHAMPS[ch])}
                                        />
                                        {t(CHAMPS[ch])}
                                    </label>
                                );
                            if (ch === "noms" && c.type === "outils_dans_l_ordre")
                                return (
                                    <OrdreDesOutils
                                        key={ch}
                                        noms={String(c.valeurs[ch] ?? "") === "" ? [] : String(c.valeurs[ch]).split(",").map((x) => x.trim())}
                                        outils={ressources?.outils ?? []}
                                        changer={(noms) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: noms.join(", ") } })}
                                    />
                                );
                            const valeur = String(c.valeurs[ch] ?? "");
                            if (options && options.length > 0)
                                return (
                                    <Liste
                                        key={ch}
                                        className="w-full"
                                        valeur={valeur}
                                        placeholder={t(CHAMPS[ch])}
                                        changer={(v) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: v } })}
                                        options={valeur && !options.includes(valeur) ? [valeur, ...options] : options}
                                    />
                                );
                            return (
                                <Input
                                    key={ch}
                                    className="h-8"
                                    aria-label={t(CHAMPS[ch])}
                                    placeholder={t(CHAMPS[ch])}
                                    value={valeur}
                                    onChange={(e) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: e.target.value } })}
                                />
                            );
                        })}
                    </div>
                ))}
            </div>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="outline" size="sm" className="mt-2" disabled={lignes.length >= 12}>
                        <Plus className="size-3.5" /> {t({ en: "Add a criterion", fr: "Ajouter un critère" })}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start" className="w-72">
                    {offerts.map((k) => (
                        <DropdownMenuItem key={k} onSelect={() => changer([...lignes, ligneVide(k)])}>
                            {t(CRITERES[k]?.libelle ?? { en: k, fr: k })}
                        </DropdownMenuItem>
                    ))}
                </DropdownMenuContent>
            </DropdownMenu>
        </div>
    );
}
