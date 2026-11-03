"use client";

import { useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

import { BlocChamp, LigneChamp } from "./fenetre-onglets";
import { Liste } from "./liste";
import { Info } from "./marques";

/**
 * Fenêtre à champs (E55) : en-tête fixe, corps blanc, champs séparés par un trait, pied fixe. Les champs sont décrits
 * par leurs données (type, libellé, valeur de départ) ; la fenêtre rend les valeurs saisies à `onValider`, sans rien
 * inventer. Un champ `si` n'apparaît que si un autre champ a l'une des valeurs listées.
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

function ChampVue({ c, valeur, changer }: { c: Champ; valeur: string | boolean; changer: (v: string | boolean) => void }) {
    const texte = String(valeur);
    if (c.t === "inter") {
        return (
            <LigneChamp libelle={c.l} info={c.info}>
                <Switch checked={valeur === true} onCheckedChange={changer} aria-label={c.l} />
            </LigneChamp>
        );
    }
    if (c.t === "choix") {
        return (
            <LigneChamp libelle={c.l} info={c.info}>
                <Liste valeur={texte} changer={changer} options={c.o} className="w-56" />
            </LigneChamp>
        );
    }
    if (c.t === "nombre") {
        const n = Number(texte);
        const hors = texte !== "" && ((c.min !== undefined && n < c.min) || (c.max !== undefined && n > c.max));
        return (
            <LigneChamp libelle={c.l} info={c.info}>
                <span className="inline-flex items-center gap-2">
                    <Input
                        value={texte}
                        inputMode="numeric"
                        aria-label={c.l}
                        aria-invalid={hors}
                        onChange={(e) => changer(e.target.value.replace(/[^\d]/g, ""))}
                        className="h-8 w-24 text-right"
                    />
                    {c.unite && <span className="w-6 text-sm text-muted-foreground">{c.unite}</span>}
                </span>
            </LigneChamp>
        );
    }
    if (c.t === "lu") {
        return (
            <LigneChamp libelle={c.l} info={c.info}>
                <span className="text-sm text-muted-foreground">{c.v}</span>
            </LigneChamp>
        );
    }
    return (
        <BlocChamp libelle={c.l} info={c.info}>
            {c.t === "zone" ? (
                <Textarea value={texte} aria-label={c.l} onChange={(e) => changer(e.target.value)} rows={4} />
            ) : (
                <Input
                    type={c.t === "secret" ? "password" : "text"}
                    value={texte}
                    aria-label={c.l}
                    onChange={(e) => changer(e.target.value)}
                />
            )}
        </BlocChamp>
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
    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className={`${taille} flex flex-col gap-0 overflow-hidden p-0`}>
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <DialogTitle className="flex items-center gap-2 text-lg">
                        {titre}
                        {info && <Info>{info}</Info>}
                    </DialogTitle>
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
