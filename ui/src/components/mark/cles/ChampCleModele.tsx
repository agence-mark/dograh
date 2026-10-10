"use client";

/**
 * [.mark] The API key field of « Models » and of an agent's model settings (chantier
 * direct-et-passe-muette, lot 0 bis, P20 to P22).
 *
 * A key typed by hand works as before. « Keys… » picks a key of the key library instead: the
 * setting then holds `mark-cle:<uuid>`, which the server replaces by the key itself when a call
 * starts and when the provider is tested on save (`api/services/cles_reference.py`). A picked key
 * shows by its name, never by its value; a deleted one says so.
 */
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { type Texte, useLangue } from "../langue/langue";
import { FenetreCles, type Fournisseur, nomDu, useCles } from "./FenetreCles";

// Same prefix as the server (`PREFIXE`, api/services/cles_reference.py).
export const PREFIXE_REFERENCE = "mark-cle:";
export const estReference = (valeur: string | null | undefined) =>
    typeof valeur === "string" && valeur.startsWith(PREFIXE_REFERENCE);

// Same families as the server (`FAMILLES`, api/services/cles_reference.py).
const FAMILLES: Record<string, string> = {
    openai_realtime: "openai",
    google_realtime: "google",
    google_vertex_realtime: "google_vertex",
    azure_realtime: "azure",
    grok_realtime: "xai",
};
export const famille = (f: string) => FAMILLES[f] ?? f;

export function ChampCleModele({
    valeur,
    fournisseur,
    placeholder,
    onChange,
    id,
}: {
    /** [.mark] Lot C d'agent-leger-greffier: the id of the typed-key input, for its label. */
    id?: string;
    valeur: string;
    /** The provider chosen in the form: the library opens on its keys. */
    fournisseur: string;
    placeholder?: string;
    onChange: (valeur: string) => void;
}) {
    const { t } = useLangue();
    const reference = estReference(valeur);
    // Read only when a key of the library shows: a key typed by hand needs no list.
    const { cles, recharger } = useCles(undefined, reference);
    const [bibliotheque, setBibliotheque] = useState(false);
    const designee = reference ? cles?.find((c) => `${PREFIXE_REFERENCE}${c.uuid}` === valeur) : undefined;
    const libelleCles: Texte = { en: "Keys…", fr: "Clés…" };

    return (
        <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex gap-2">
                {reference ? (
                    <div
                        className="flex min-w-0 flex-1 items-center rounded-md border border-border bg-muted/40 px-3 text-sm"
                        data-testid="cle-de-la-bibliotheque"
                    >
                        <span className="truncate">
                            {designee
                                ? `${designee.nom} · ${nomDu(designee.fournisseur)} · ${t({ en: "key library", fr: "bibliothèque de clés" })}`
                                : cles === null
                                  ? t({ en: "Loading…", fr: "Chargement…" })
                                  : t({ en: "Key deleted: pick another", fr: "Clé supprimée : choisis-en une autre" })}
                        </span>
                    </div>
                ) : (
                    <Input id={id} type="text" placeholder={placeholder} value={valeur} onChange={(e) => onChange(e.target.value)} />
                )}
                <Button type="button" variant="outline" size="sm" className="shrink-0" onClick={() => setBibliotheque(true)}>
                    {t(libelleCles)}
                </Button>
                {reference && (
                    <Button type="button" variant="ghost" size="sm" className="shrink-0" onClick={() => onChange("")}>
                        {t({ en: "Type a key", fr: "Taper une clé" })}
                    </Button>
                )}
            </div>
            {reference && cles !== null && !designee && (
                <p className="text-xs text-destructive" role="alert">
                    {t({
                        en: "This key was deleted from the library: calls will fail until you pick another.",
                        fr: "Cette clé a été supprimée de la bibliothèque : les appels échoueront tant que tu n'en choisis pas une autre.",
                    })}
                </p>
            )}
            {designee && famille(designee.fournisseur) !== famille(fournisseur) && (
                <p className="text-xs text-destructive" role="alert">
                    {t({
                        en: `This is a ${nomDu(designee.fournisseur)} key, not a ${nomDu(fournisseur)} one: the save will be refused.`,
                        fr: `C'est une clé ${nomDu(designee.fournisseur)}, pas ${nomDu(fournisseur)} : l'enregistrement sera refusé.`,
                    })}
                </p>
            )}
            {bibliotheque && (
                <FenetreCles
                    ouverte
                    onFermer={() => {
                        setBibliotheque(false);
                        void recharger();
                    }}
                    fournisseur={fournisseur as Fournisseur}
                    onChoisir={async (uuid) => {
                        // Reloaded first, or the new key would show as « deleted » for a moment.
                        await recharger();
                        onChange(`${PREFIXE_REFERENCE}${uuid}`);
                    }}
                />
            )}
        </div>
    );
}
