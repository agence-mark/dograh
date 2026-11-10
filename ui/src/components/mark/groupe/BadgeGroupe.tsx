"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A11) : le badge d'un agent d'un groupe dans la liste
 * d'agents. Un spécialisé porte « Spécialisé de [principal] » (et « cerveau propre » quand il a
 * détaché son cerveau) ; un principal porte « Principal ». Un agent seul n'a aucun badge.
 */
import { Badge } from "@/components/ui/badge";

import { type Texte, useLangue } from "../langue/langue";

export interface RoleAffiche {
    role: "principal" | "specialise";
    principalId: number | null;
    principalNom: string | null;
    cerveauPropre: boolean;
    specialises: number[];
}

const TEXTES = {
    principal: { en: "Main agent", fr: "Principal" },
    specialiseDe: { en: "Specialised agent of", fr: "Spécialisé de" },
    cerveauPropre: { en: "own brain", fr: "cerveau propre" },
    sansNom: { en: "the main agent", fr: "l'agent principal" },
} satisfies Record<string, Texte>;

export const BadgeGroupe = ({ role }: { role: RoleAffiche | undefined }) => {
    const { t } = useLangue();
    if (!role) return null;
    if (role.role === "principal") {
        return (
            <Badge variant="secondary" className="ml-2 font-normal" data-badge-groupe="principal">
                {t(TEXTES.principal)}
            </Badge>
        );
    }
    return (
        <>
            <Badge variant="secondary" className="ml-2 font-normal" data-badge-groupe="specialise">
                {t(TEXTES.specialiseDe)} {role.principalNom ?? t(TEXTES.sansNom)}
            </Badge>
            {role.cerveauPropre && (
                <Badge variant="outline" className="ml-1 font-normal" data-badge-groupe="cerveau-propre">
                    {t(TEXTES.cerveauPropre)}
                </Badge>
            )}
        </>
    );
};

// [.mark] Correctifs d'écran, point 3 : dans la liste des Agents, le rôle se lit en ligne grise SOUS le nom (le badge
// ci-dessus reste celui de la vue d'un groupe et du tableau des dossiers). « cerveau propre » n'apparaît qu'au survol.
export const SousLigneGroupe = ({ role }: { role: RoleAffiche | undefined }) => {
    const { t } = useLangue();
    if (!role) return null;
    const n = role.specialises.length;
    const texte =
        role.role === "principal"
            ? n === 0
                ? t({ en: "no specialist", fr: "aucun spécialisé" })
                : t({ en: `${n} specialised agent${n > 1 ? "s" : ""}`, fr: `${n} spécialisé${n > 1 ? "s" : ""}` })
            : `${t(TEXTES.specialiseDe)} ${role.principalNom ?? t(TEXTES.sansNom)}`;
    return (
        <span className="flex items-center gap-2 text-xs font-normal text-muted-foreground" data-sous-ligne-groupe={role.role}>
            <span className="truncate">{texte}</span>
            {role.role === "specialise" && role.cerveauPropre && (
                <Badge variant="outline" className="font-normal opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100" data-badge-groupe="cerveau-propre">
                    {t(TEXTES.cerveauPropre)}
                </Badge>
            )}
        </span>
    );
};
