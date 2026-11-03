"use client";

/**
 * [.mark] U4 (F3, E16) : une seule grammaire pour l'héritage, sur chaque réglage.
 *
 * L'API (`GET /workflow/{id}/heritage-reglages`) rend, pour chaque clé, sa valeur effective et son origine
 * (organisation, principal, établissement, propre à l'agent, défaut). `ChampReglage` lit ce contexte et dessine la
 * pastille d'origine : en gris pour une valeur héritée, en noir pour « propre à l'agent », avec « revenir à la valeur
 * héritée ». Sans contexte (une page qui n'en fournit pas), rien ne s'affiche : aucune fausse origine.
 */
import { createContext, useContext } from "react";

import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";

export type OrigineReglage = "organisation" | "principal" | "etablissement" | "agent" | "defaut";

export interface ReglageHerite {
    origine: OrigineReglage | string;
    valeur?: unknown;
    valeur_heritee?: unknown;
    propre: boolean;
    modifiable: boolean;
    masquee: boolean;
}

export interface ValeurHeritage {
    reglages: Record<string, ReglageHerite>;
    /** Pose la valeur héritée de la clé et l'enregistre (un geste volontaire). Absent : pas de bouton. */
    revenir?: (cle: string) => void;
}

export const ContexteHeritage = createContext<ValeurHeritage | null>(null);

export const TEXTES_ORIGINE: Record<OrigineReglage, Texte> = {
    organisation: { en: "From the organization", fr: "De l'organisation" },
    principal: { en: "Set by the main agent", fr: "Réglé par l'agent principal" },
    etablissement: { en: "From the establishment", fr: "De l'établissement" },
    agent: { en: "Own to this agent", fr: "Propre à cet agent" },
    defaut: { en: "Default value", fr: "Valeur par défaut" },
};

export const TEXTE_REVENIR: Texte = { en: "Back to the inherited value", fr: "Revenir à la valeur héritée" };

export const PastilleOrigine = ({ cle }: { cle: string }) => {
    const { t } = useLangue();
    const heritage = useContext(ContexteHeritage);
    const reglage = heritage?.reglages[cle];
    if (!heritage || !reglage) return null;
    const origine = (reglage.origine in TEXTES_ORIGINE ? reglage.origine : "defaut") as OrigineReglage;
    const peutRevenir = reglage.propre && reglage.modifiable && !reglage.masquee && heritage.revenir;
    return (
        <span className="inline-flex items-baseline gap-2" data-origine={origine} data-reglage-origine={cle}>
            <span className={cn("text-[11px]", reglage.propre ? "font-medium text-foreground" : "text-muted-foreground")}>
                {t(TEXTES_ORIGINE[origine])}
            </span>
            {peutRevenir && (
                <button
                    type="button"
                    className="cursor-pointer text-[11px] text-muted-foreground hover:font-semibold hover:text-foreground"
                    onClick={() => heritage.revenir?.(cle)}
                >
                    {t(TEXTE_REVENIR)}
                </button>
            )}
        </span>
    );
};
