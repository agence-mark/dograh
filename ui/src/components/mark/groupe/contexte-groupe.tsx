"use client";

/**
 * [.mark] Chantier agents-specialises, lots 10 et 12 (A10) : l'agent que l'écran montre
 * est-il un spécialisé ? Un spécialisé ne règle que son graphe : les thèmes communs lui
 * viennent de l'agent principal (recopiés à chaque enregistrement du principal) et
 * s'affichent EN LECTURE, avec un bandeau « Réglé sur l'agent principal » et un lien.
 *
 * Le contexte est posé par la page des réglages ; hors de la page (un test d'un thème seul,
 * l'écran de l'organisation) il vaut « agent seul » : rien ne change.
 */
import Link from "next/link";
import { createContext, type ReactNode, useContext } from "react";

import { type Texte, useLangue } from "../langue/langue";

export interface MembreAffiche {
    id: number;
    name: string;
    cerveau_propre?: boolean;
}

export interface ValeurGroupe {
    /** L'identifiant du principal quand l'agent est un spécialisé ; null pour un agent seul ou un principal. */
    specialiseDe: number | null;
    /** Le nom du principal, quand on l'a lu. */
    principalNom: string | null;
    /** Le spécialisé a détaché son cerveau (case « Cerveau propre »). */
    cerveauPropre: boolean;
    /** Les spécialisés du groupe (lus par la route du groupe), pour la liste du thème Agent. */
    membres: MembreAffiche[];
}

export const AGENT_SEUL: ValeurGroupe = { specialiseDe: null, principalNom: null, cerveauPropre: false, membres: [] };

export const ContexteGroupe = createContext<ValeurGroupe>(AGENT_SEUL);

export const useGroupe = () => useContext(ContexteGroupe);

/**
 * Les thèmes que le spécialisé reçoit du principal en entier (convention § 2, plan A10 : thèmes
 * 3, 4, 5, 6, 7, 8). Le thème 1 (Agent) et le thème 2 (Briques) en ont une partie seulement : ils
 * placent eux-mêmes leurs zones en lecture.
 */
export const THEMES_COMMUNS_EN_LECTURE: readonly string[] = [
    "ecoute",
    // cloture-code, F8: every key of the modules is common (copied from the main agent).
    "modules",
    "tour",
    "voix",
    "rythme",
    "donnees",
    "etablissement",
];

export const TEXTES_GROUPE = {
    bandeau: { en: "Set on the main agent", fr: "Réglé sur l'agent principal" },
    bandeauAide: {
        en: "These settings are the main agent's, copied here each time it is saved. Change them there.",
        fr: "Ces réglages sont ceux de l'agent principal, recopiés ici à chaque enregistrement du principal. Changez-les là-bas.",
    },
    ouvrirPrincipal: { en: "Open the main agent's settings", fr: "Ouvrir les réglages de l'agent principal" },
    principalSansNom: { en: "main agent", fr: "agent principal" },
} satisfies Record<string, Texte>;

/** Le bandeau « Réglé sur l'agent principal », avec le lien vers le principal. */
export const BandeauReglePrincipal = ({ detache = false }: { detache?: boolean }) => {
    const { t } = useLangue();
    const { specialiseDe, principalNom } = useGroupe();
    if (specialiseDe === null || detache) return null;
    return (
        <div
            role="note"
            data-bandeau="regle-sur-le-principal"
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-md border bg-muted/40 px-4 py-3 text-sm"
        >
            <span className="font-medium">{t(TEXTES_GROUPE.bandeau)}</span>
            <Link
                href={`/workflow/${specialiseDe}/settings`}
                className="underline"
                aria-label={t(TEXTES_GROUPE.ouvrirPrincipal)}
            >
                {principalNom ?? t(TEXTES_GROUPE.principalSansNom)}
            </Link>
            <span className="basis-full text-xs text-muted-foreground">{t(TEXTES_GROUPE.bandeauAide)}</span>
        </div>
    );
};

/**
 * Le contenu d'une zone commune. Pour un spécialisé : le bandeau, puis le contenu dans un
 * ensemble désactivé (aucun champ ne s'écrit, aucun bouton ne part) ; sinon le contenu tel quel.
 * ``lecture`` force ou lève la lecture seule (le thème Briques la lève quand le cerveau est détaché).
 */
export const ZoneCommune = ({
    children,
    lecture,
    bandeau = true,
}: {
    children: ReactNode;
    lecture?: boolean;
    /** Faux quand un bandeau a déjà été montré plus haut dans le même thème. */
    bandeau?: boolean;
}) => {
    const { specialiseDe } = useGroupe();
    const enLecture = lecture ?? specialiseDe !== null;
    if (!enLecture) return <>{children}</>;
    return (
        <>
            {bandeau && <BandeauReglePrincipal />}
            <fieldset disabled data-lecture="commune" className="m-0 min-w-0 space-y-6 border-0 p-0">
                {children}
            </fieldset>
        </>
    );
};
