"use client";

import { useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { Liste } from "./liste";
import { Info } from "./marques";

/**
 * Fenêtre à champs (E55), reprise de la maquette (`modales.tsx`, K1) : en-tête fixe, corps blanc, champs séparés par un
 * trait, pied fixe. La première phrase d'une explication se lit sous le libellé, le reste est dans le « ! ». Les champs
 * sont décrits par leurs données (type, libellé, valeur de départ) ; la fenêtre rend les valeurs saisies à `onValider`,
 * sans rien inventer. Un champ `si` n'apparaît que si un autre champ a l'une des valeurs listées.
 */
export type Champ = { id: string; l: string; info?: React.ReactNode; si?: [string, (string | boolean)[]] } & (
    | { t: "texte"; v?: string }
    | { t: "zone"; v?: string }
    | { t: "choix"; o: string[]; v?: string }
    | { t: "inter"; v?: boolean }
    | { t: "nombre"; v?: string; min?: number; max?: number; unite?: string }
    | { t: "lu"; v: string }
    | { t: "secret"; v?: string }
);

export type SectionChamps = { titre?: string; info?: React.ReactNode; champs: Champ[] };
export type Valeurs = Record<string, string | boolean>;

const depart = (sections: SectionChamps[]): Valeurs =>
    Object.fromEntries(
        sections.flatMap((s) =>
            s.champs.map((c): [string, string | boolean] => [
                c.id,
                c.t === "inter" ? !!c.v : c.t === "choix" ? (c.v ?? c.o[0] ?? "") : ((c as { v?: string }).v ?? ""),
            ]),
        ),
    );

/** La première phrase d'une explication (celle qui se lit sous le libellé) ; le reste va dans le « ! ». */
const premiere = (a?: string) => (a ? a.split(/(?<=\.)\s/)[0] : "");

function ChampVue({ c, valeur, changer }: { c: Champ; valeur: string | boolean; changer: (v: string | boolean) => void }) {
    const { t } = useLangue();
    const texte = String(valeur);
    const phrase = typeof c.info === "string" ? premiere(c.info) : "";
    const reste = c.info && (typeof c.info !== "string" || c.info !== phrase) ? (typeof c.info === "string" ? c.info : c.info) : undefined;
    const entete = (
        <div className="min-w-0 flex-1">
            <p className="flex items-center gap-1.5 text-sm font-medium">
                {c.l}
                {reste && <Info>{reste}</Info>}
            </p>
            {phrase && <p className="mt-0.5 text-xs text-muted-foreground">{phrase}</p>}
        </div>
    );
    if (c.t === "inter") {
        return (
            <div className="flex items-start gap-4 py-3.5">
                {entete}
                <Switch checked={valeur === true} onCheckedChange={changer} aria-label={c.l} />
            </div>
        );
    }
    const n = Number(texte);
    const horsBornes = c.t === "nombre" && texte !== "" && ((c.min !== undefined && n < c.min) || (c.max !== undefined && n > c.max));
    return (
        <div className="space-y-2 py-3.5">
            {entete}
            {c.t === "texte" && <Input value={texte} aria-label={c.l} onChange={(e) => changer(e.target.value)} />}
            {c.t === "lu" && <p className="text-sm">{c.v}</p>}
            {c.t === "secret" && (
                <Input
                    type="password"
                    value={texte}
                    aria-label={c.l}
                    placeholder={t({ en: "Entered once, never shown again", fr: "Saisi une fois, jamais réaffiché" })}
                    onChange={(e) => changer(e.target.value)}
                />
            )}
            {c.t === "zone" && <Textarea value={texte} aria-label={c.l} onChange={(e) => changer(e.target.value)} className="min-h-20" />}
            {c.t === "nombre" && (
                <div className="flex items-center gap-2">
                    <Input
                        type="number"
                        min={c.min}
                        max={c.max}
                        value={texte}
                        aria-label={c.l}
                        aria-invalid={horsBornes}
                        onChange={(e) => changer(e.target.value)}
                        className={`w-32 ${horsBornes ? "border-(--pastille-urgente)" : ""}`}
                    />
                    {c.unite && <span className="text-sm text-muted-foreground">{c.unite}</span>}
                    {(c.min !== undefined || c.max !== undefined) && (
                        <span className={`ml-auto text-xs ${horsBornes ? "text-(--marque-danger-texte)" : "text-muted-foreground"}`}>
                            {t({ en: "from", fr: "de" })} {c.min} {t({ en: "to", fr: "à" })} {c.max}
                        </span>
                    )}
                </div>
            )}
            {c.t === "choix" &&
                (c.o.length >= 2 && c.o.length <= 3 ? (
                    <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm">
                        {c.o.map((o) => (
                            <button
                                key={o}
                                type="button"
                                onClick={() => changer(o)}
                                className={`rounded-md px-3 py-1 ${texte === o ? "bg-white font-medium shadow-sm" : "text-muted-foreground hover:font-medium"}`}
                            >
                                {o}
                            </button>
                        ))}
                    </span>
                ) : (
                    <Liste valeur={texte} changer={changer} options={c.o} taille="default" className="w-full" />
                ))}
        </div>
    );
}

export function FenetreChamps(props: {
    ouverte: boolean;
    fermer: () => void;
    titre: React.ReactNode;
    info?: React.ReactNode;
    sections: SectionChamps[];
    valider: string;
    onValider?: (valeurs: Valeurs) => void;
    danger?: boolean;
    pied?: React.ReactNode;
    /** Contenu libre sous les champs (liste, tableau) ; reste un corps blanc, sans carte. */
    corps?: React.ReactNode;
}) {
    // Montée à chaque ouverture : l'affichage conditionnel part des valeurs de l'objet ouvert, jamais d'un état périmé.
    return props.ouverte ? <FenetreOuverte {...props} /> : null;
}

function FenetreOuverte({ fermer, titre, info, sections, valider, onValider, danger, pied, corps }: Parameters<typeof FenetreChamps>[0]) {
    const { t } = useLangue();
    const [valeurs, setValeurs] = useState<Valeurs>(() => depart(sections));
    const visible = (c: Champ) => !c.si || c.si[1].includes(valeurs[c.si[0]]);
    const visibles = sections.map((s) => ({ ...s, champs: s.champs.filter(visible) })).filter((s) => s.champs.length);
    const taille = `${corps ? "sm:max-w-3xl" : sections.length > 1 ? "sm:max-w-2xl" : "sm:max-w-xl"} max-h-[86vh]`;
    const lecture = valider === "Fermer" || valider === "Close";
    const phrase = typeof info === "string" ? premiere(info) : "";
    const reste = info && (typeof info !== "string" || info !== phrase) ? info : undefined;
    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className={`${taille} flex flex-col gap-0 overflow-hidden p-0`}>
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {titre}
                        {reste && <Info>{reste}</Info>}
                    </DialogTitle>
                    {phrase && <p className="mt-0.5 text-sm text-muted-foreground">{phrase}</p>}
                </div>
                {corps && <div className="min-h-0 flex-1 space-y-8 overflow-auto bg-background px-6 py-5">{corps}</div>}
                {visibles.length > 0 && (
                    <div className={`min-h-0 flex-1 overflow-auto bg-background px-6 ${sections.length > 1 ? "space-y-8 py-5" : "py-1"}`}>
                        {visibles.map((s, i) => (
                            <section key={s.titre ?? i}>
                                {s.titre && (
                                    <p className="flex items-center gap-1.5 pb-1 text-sm font-semibold">
                                        {s.titre}
                                        {s.info && <Info>{s.info}</Info>}
                                    </p>
                                )}
                                <div className="divide-y">
                                    {s.champs.map((c) => (
                                        <ChampVue
                                            key={c.id}
                                            c={c}
                                            valeur={valeurs[c.id]}
                                            changer={(v) => setValeurs((x) => ({ ...x, [c.id]: v }))}
                                        />
                                    ))}
                                </div>
                            </section>
                        ))}
                    </div>
                )}
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {pied && <div className="mr-auto">{pied}</div>}
                    {lecture ? (
                        <Button onClick={fermer}>{valider}</Button>
                    ) : (
                        <>
                            <Button variant="outline" onClick={fermer}>
                                {t({ en: "Cancel", fr: "Annuler" })}
                            </Button>
                            <Button
                                variant={danger ? "destructive" : "default"}
                                onClick={() => {
                                    onValider?.(valeurs);
                                    fermer();
                                }}
                            >
                                {valider}
                            </Button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
