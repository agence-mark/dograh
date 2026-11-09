"use client";

/**
 * [.mark] Clôture, SA-3 (D18) : une suite de champs numériques bornés, le niveau « avancé » d'un thème (valeurs d'avant par défaut,
 * mêmes bornes que le serveur). Même forme que les champs avancés de l'après-appel : libellé, aide, bornes et défaut dans le « ! »,
 * unité à côté de la valeur, faute de frappe dite sous le champ.
 */
import { Input } from "@/components/ui/input";

import { type Texte, useLangue } from "../langue/langue";
import { ChampReglage } from "./ChampReglage";

export type ChampNumerique = {
    cle: string;
    id: string;
    libelle: Texte;
    aide: Texte;
    min: number;
    max: number;
    pas: number;
    defaut: number;
    unite: Texte;
};

export const SECONDES: Texte = { en: "s", fr: "s" };
export const SANS_UNITE: Texte = { en: "", fr: "" };

export const horsBornes = (c: Pick<ChampNumerique, "min" | "max">, v: number | undefined) => !(typeof v === "number" && Number.isFinite(v) && v >= c.min && v <= c.max);

export const texteBornesNumerique = (c: ChampNumerique): Texte => ({
    en: `${c.min} to ${c.max}, default ${c.defaut}`,
    fr: `${c.min} à ${c.max}, ${c.defaut} par défaut`,
});

export function ChampsNumeriques({
    champs,
    valeur,
    poser,
}: {
    champs: ChampNumerique[];
    valeur: (cle: string) => number | undefined;
    poser: (cle: string, valeur: number) => void;
}) {
    const { t } = useLangue();
    return (
        <>
            {champs.map((c) => {
                const v = valeur(c.cle) ?? c.defaut;
                return (
                    <ChampReglage
                        key={c.cle}
                        cle={c.cle}
                        idControle={c.id}
                        libelle={c.libelle}
                        aides={[c.aide]}
                        bornes={texteBornesNumerique(c)}
                        erreur={horsBornes(c, v) ? { en: `a number from ${c.min} to ${c.max}.`, fr: `un nombre de ${c.min} à ${c.max}.` } : null}
                    >
                        <span className="inline-flex items-center gap-2">
                            <Input
                                id={c.id}
                                type="number"
                                min={c.min}
                                max={c.max}
                                step={c.pas}
                                value={Number.isNaN(v) ? "" : v}
                                className="w-28"
                                onChange={(e) => poser(c.cle, e.target.value === "" ? Number.NaN : Number(e.target.value))}
                            />
                            {t(c.unite) && <span className="text-xs text-muted-foreground">{t(c.unite)}</span>}
                        </span>
                    </ChampReglage>
                );
            })}
        </>
    );
}
