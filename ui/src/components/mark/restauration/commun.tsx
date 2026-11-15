"use client";

/**
 * [.mark] Module Restauration, lot 12 : les petites pièces que les écrans du module partagent (reprises de la maquette `commun.tsx`, branchées sur
 * les composants de production : la fiche de production fait foi, `reference/32`).
 */
import { Building2, Lock, Store } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { useLangue } from "../langue/langue";
import { EtatVide } from "../studio/etat-vide";
import { Liste } from "../studio/liste";
import { Info, Marque } from "../studio/marques";
import { type EtatDeLecture, useModuleRestauration } from "./contexte";
import type { Portee } from "./donnees";

/** Les textes de la maquette s'écrivent `t(fr, en)` ; l'écran écrit chaque texte dans les deux langues (convention T2). */
export function useTexte() {
    const { t } = useLangue();
    return (fr: string, en: string) => t({ fr, en });
}

export const euros = (centimes: number) => `${(centimes / 100).toFixed(2).replace(".", ",")} €`;
export const eurosCourts = (centimes: number) => `${(centimes / 100).toFixed(centimes % 100 ? 2 : 0).replace(".", ",")} €`;
/** « 12,5 » ou « 12 » d'un nombre d'euros tapé : en centimes (jamais de flottant gardé). */
export const centimes = (saisie: string): number => Math.round(Number(saisie.replace(",", ".")) * 100) || 0;

/** L'enveloppe d'un écran de données : chargement, erreur (avec « réessayer »), vide, sinon le contenu. */
export function EcranDonnees({
    etat, relire, vide, iconeVide = Store, titreVide, children,
}: {
    etat: EtatDeLecture;
    relire?: () => void;
    vide?: boolean;
    iconeVide?: typeof Store;
    titreVide?: string;
    children: React.ReactNode;
}) {
    const t = useTexte();
    if (etat === "chargement") return <EtatVide cas="chargement" lignes={6} />;
    if (etat === "erreur") return <EtatVide cas="erreur" reessayer={relire} />;
    if (vide) return <EtatVide cas="premier" icone={iconeVide} titre={titreVide ?? t("Rien pour l'instant", "Nothing yet")} />;
    return <>{children}</>;
}

/** La portée d'un objet : toute l'enseigne, cet établissement, ou commun avec une exception pour celui-ci. */
export function PorteePastille({ portee }: { portee: Portee }) {
    const t = useTexte();
    if (portee === "enseigne") return <Marque ton="neutre">{t("Toute l'enseigne", "Whole chain")}</Marque>;
    if (portee === "etablissement") return <Marque ton="plein">{t("Cet établissement", "This site")}</Marque>;
    return <Marque ton="attention">{t("Exception ici", "Exception here")}</Marque>;
}

/** Ligne de source : « gérée dans la caisse » (lecture seule) ou « modifiable ici ». */
export function LigneSource({ caisse, prise, objet }: { caisse: boolean; prise: string; objet: string }) {
    const t = useTexte();
    return (
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            {caisse ? <Lock className="size-3.5" /> : <Store className="size-3.5" />}
            {caisse
                ? t(`${objet} dans la caisse (${prise}). Lecture seule ici.`, `${objet} in the till (${prise}). Read-only here.`)
                : t("Modifiable ici : le restaurant la tient à jour depuis son portail.", "Editable here: the restaurant keeps it up to date from its portal.")}
        </p>
    );
}

/** Le sélecteur d'établissement, en tête de chaque onglet du module. */
export function SelecteurEtab() {
    const t = useTexte();
    const { etablissements, etab, poserEtab } = useModuleRestauration();
    return (
        <div className="flex items-center gap-2 text-sm">
            <Building2 className="size-4 text-muted-foreground" />
            <span className="text-muted-foreground">{t("Établissement", "Site")}</span>
            <Liste
                valeur={etab === null ? "" : String(etab)}
                changer={(v) => poserEtab(Number(v))}
                options={etablissements.map((e) => ({ valeur: String(e.id), libelle: e.nom }))}
                className="w-56"
                libelle={t("Établissement", "Site")}
            />
            <Info>
                {t(
                    "Chaque objet du module a sa portée : toute l'enseigne, cet établissement, ou commun avec une exception. Rien n'est en concurrence entre deux établissements.",
                    "Each object has a scope: whole chain, this site, or shared with an exception. Nothing competes between two sites.",
                )}
            </Info>
        </div>
    );
}

/** Un choix segmenté à valeurs (la `Segmente` de production prend des libellés ; celle-ci garde la valeur à part du libellé). */
export function Segment3<T extends string>({ valeur, options, changer }: { valeur: T; options: { v: T; l: string }[]; changer: (v: T) => void }) {
    return (
        <span role="group" className="inline-flex rounded-lg bg-muted p-0.5 text-sm">
            {options.map((o) => (
                <button
                    key={o.v}
                    type="button"
                    aria-pressed={valeur === o.v}
                    onClick={() => changer(o.v)}
                    className={`cursor-pointer rounded-md px-3 py-1 whitespace-nowrap ${valeur === o.v ? "bg-background font-medium shadow-sm" : "text-muted-foreground hover:font-medium hover:text-foreground"}`}
                >
                    {o.l}
                </button>
            ))}
        </span>
    );
}

/** Une confirmation (retirer le module, retirer un cercle) : petite fenêtre centrée, une des exceptions de la règle d'écran. */
export function Confirmer({
    titre, texte, bouton, fermer, valider, danger = true,
}: {
    titre: string;
    texte: string;
    bouton: string;
    fermer: () => void;
    valider: () => void;
    danger?: boolean;
}) {
    const t = useTexte();
    return (
        <Dialog centree open onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-sm" onOpenAutoFocus={(e) => e.preventDefault()}>
                <DialogTitle>{titre}</DialogTitle>
                <DialogDescription className="text-sm text-muted-foreground">{texte}</DialogDescription>
                <div className="flex justify-end gap-2 pt-2">
                    <Button variant="outline" onClick={fermer}>{t("Annuler", "Cancel")}</Button>
                    <Button variant={danger ? "destructive" : "default"} onClick={() => { valider(); fermer(); }}>{bouton}</Button>
                </div>
            </DialogContent>
        </Dialog>
    );
}

/** Un nombre saisi, avec son unité à droite (« 30 min », « 3,50 € »). La valeur reste le texte tapé : l'appelant la convertit à l'enregistrement. */
export function Nombre({ valeur, changer, unite, min, max, libelle, className = "" }: {
    valeur: string;
    changer: (v: string) => void;
    unite?: string;
    min?: number;
    max?: number;
    libelle?: string;
    className?: string;
}) {
    return (
        <span className={`inline-flex items-center gap-1.5 ${className}`}>
            <Input type="number" inputMode="decimal" value={valeur} min={min} max={max} onChange={(e) => changer(e.target.value)} aria-label={libelle} className="h-8 w-24 text-right" />
            {unite && <span className="text-sm text-muted-foreground">{unite}</span>}
        </span>
    );
}
