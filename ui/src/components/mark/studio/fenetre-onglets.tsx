"use client";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";

import { Info } from "./marques";

/**
 * La fenêtre commune (E55, E71, E73) : en-tête fixe (visuel, titre, ligne grise, onglets), corps blanc sans carte,
 * pied fixe. Hauteur fixe : changer d'onglet ne fait pas sauter la fenêtre. Une fenêtre ouverte depuis celle-ci
 * prend la même taille avec la flèche retour : c'est réglé UNE fois, dans `components/ui/dialog.tsx`, jamais ici.
 */
export const TAILLE_FENETRE = "sm:max-w-4xl h-[86vh]";

export function FenetreOnglets({
    fermer,
    titre,
    sous,
    visuel,
    droite,
    onglets,
    onglet,
    changerOnglet,
    children,
    pied,
    valider,
    onValider,
    desactiver,
}: {
    fermer: () => void;
    titre: React.ReactNode;
    sous?: React.ReactNode;
    visuel?: React.ReactNode;
    droite?: React.ReactNode;
    onglets?: string[];
    onglet?: string;
    changerOnglet?: (o: string) => void;
    children: React.ReactNode;
    pied?: React.ReactNode;
    /** Libellé du bouton de validation ; `null` = lecture seule, un seul bouton « Fermer ». */
    valider?: string | null;
    onValider?: () => void;
    desactiver?: boolean;
}) {
    const { t } = useLangue();
    const libelle = valider === undefined ? t({ en: "Save", fr: "Enregistrer" }) : valider;
    return (
        <Dialog open onOpenChange={(ouvert) => !ouvert && fermer()}>
            <DialogContent
                onOpenAutoFocus={(e) => e.preventDefault()}
                className={`${TAILLE_FENETRE} flex flex-col gap-0 overflow-hidden p-0`}
            >
                <div className="shrink-0 border-b px-6 pt-5 pr-12">
                    <div className="flex items-start gap-3 pb-4">
                        {visuel}
                        <div className="min-w-0 flex-1">
                            <DialogTitle className="flex items-center gap-2 text-lg">{titre}</DialogTitle>
                            {sous && <p className="mt-0.5 text-sm text-muted-foreground">{sous}</p>}
                        </div>
                        {droite}
                    </div>
                    {onglets && (
                        <div role="tablist" className="-mb-px flex items-center gap-1">
                            {onglets.map((o) => (
                                <button
                                    key={o}
                                    type="button"
                                    role="tab"
                                    aria-selected={onglet === o}
                                    onClick={() => changerOnglet?.(o)}
                                    className={`border-b-2 px-3 py-2.5 text-sm ${
                                        onglet === o
                                            ? "border-primary font-medium"
                                            : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"
                                    }`}
                                >
                                    {o}
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                <div className="min-h-0 flex-1 overflow-auto bg-background px-6 py-5">{children}</div>
                <div className="flex shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                    {pied && <div className="mr-auto flex items-center gap-2">{pied}</div>}
                    {libelle === null ? (
                        <Button onClick={fermer}>{t({ en: "Close", fr: "Fermer" })}</Button>
                    ) : (
                        <>
                            <Button variant="outline" onClick={fermer}>
                                {t({ en: "Cancel", fr: "Annuler" })}
                            </Button>
                            <Button disabled={desactiver} onClick={() => onValider?.()}>
                                {libelle}
                            </Button>
                        </>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}

/** Une ligne de champ : libellé à gauche, réglage à droite. */
export function LigneChamp({ libelle, info, children }: { libelle: React.ReactNode; info?: React.ReactNode; children: React.ReactNode }) {
    return (
        <div className="flex items-center gap-4 py-3">
            <p className="flex flex-1 items-center gap-1.5 text-sm font-medium">
                {libelle}
                {info && <Info>{info}</Info>}
            </p>
            <div className="shrink-0">{children}</div>
        </div>
    );
}

/** Un bloc de champ : libellé au-dessus, réglage dessous. */
export function BlocChamp({
    libelle,
    info,
    action,
    children,
}: {
    libelle: React.ReactNode;
    info?: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <div className="space-y-2 py-3">
            <div className="flex items-center gap-2">
                <p className="flex flex-1 items-center gap-1.5 text-sm font-medium">
                    {libelle}
                    {info && <Info>{info}</Info>}
                </p>
                {action}
            </div>
            {children}
        </div>
    );
}

/** Les champs d'une fenêtre sont séparés par un trait, jamais par une carte. */
export function Champs({ children }: { children: React.ReactNode }) {
    return <div className="divide-y">{children}</div>;
}

/** Une section titrée sous une étiquette de groupe grise (E53 ter). */
export function Section({
    titre,
    info,
    action,
    children,
}: {
    titre: string;
    info?: React.ReactNode;
    action?: React.ReactNode;
    children: React.ReactNode;
}) {
    return (
        <section className="pt-6 first:pt-0">
            <div className="flex items-center gap-2 pb-1">
                <p className="flex flex-1 items-center gap-1.5 text-xs font-medium tracking-wider text-muted-foreground uppercase">
                    {titre}
                    {info && <Info>{info}</Info>}
                </p>
                {action}
            </div>
            {children}
        </section>
    );
}

/** Choix segmenté (deux à quatre options courtes). */
export function Segmente({ valeur, options, changer }: { valeur: string; options: string[]; changer: (v: string) => void }) {
    return (
        <span className="inline-flex rounded-lg bg-muted p-0.5 text-sm">
            {options.map((o) => (
                <button
                    key={o}
                    type="button"
                    aria-pressed={valeur === o}
                    onClick={() => changer(o)}
                    className={`rounded-md px-3 py-1 whitespace-nowrap ${
                        valeur === o ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium"
                    }`}
                >
                    {o}
                </button>
            ))}
        </span>
    );
}
