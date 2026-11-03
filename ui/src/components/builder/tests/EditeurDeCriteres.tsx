"use client";

/**
 * [.mark] U3 (E47): the criteria of a test, one line each. Every list is READ in the agent or the library (steps, tools,
 * outcomes, sheet fields); the type list is the one of the code (`CRITERES`). No `<select>` of the browser (E48).
 */
import { useLangue } from "@/components/mark/langue/langue";
import { Liste } from "@/components/mark/studio/liste";
import { Button } from "@/components/ui/button";
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
    return (
        <div className="space-y-2" data-testid="criteres-du-test">
            {lignes.map((c, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2">
                    <Liste
                        className="w-64"
                        valeur={c.type}
                        changer={(type) => maj(i, ligneVide(type))}
                        options={[
                            ...(offerts.includes(c.type) ? [] : [c.type]),
                            ...offerts,
                        ].map((k) => ({ valeur: k, libelle: t(CRITERES[k]?.libelle ?? { en: k, fr: k }) }))}
                    />
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
                        const valeur = String(c.valeurs[ch] ?? "");
                        if (options && options.length > 0)
                            return (
                                <Liste
                                    key={ch}
                                    className="w-48"
                                    valeur={valeur}
                                    placeholder={t(CHAMPS[ch])}
                                    changer={(v) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: v } })}
                                    options={valeur && !options.includes(valeur) ? [valeur, ...options] : options}
                                />
                            );
                        return (
                            <Input
                                key={ch}
                                className="h-8 w-48"
                                aria-label={t(CHAMPS[ch])}
                                placeholder={t(CHAMPS[ch])}
                                value={valeur}
                                onChange={(e) => maj(i, { ...c, valeurs: { ...c.valeurs, [ch]: e.target.value } })}
                            />
                        );
                    })}
                    {lignes.length > 1 && (
                        <Button variant="ghost" size="sm" onClick={() => changer(lignes.filter((_, k) => k !== i))}>
                            {t({ en: "Remove", fr: "Retirer" })}
                        </Button>
                    )}
                </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => changer([...lignes, ligneVide(offerts[0])])}>
                {t({ en: "Add a criterion", fr: "Ajouter un critère" })}
            </Button>
        </div>
    );
}
