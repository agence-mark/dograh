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
