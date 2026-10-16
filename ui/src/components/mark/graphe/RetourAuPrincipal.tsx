"use client";

/**
 * [.mark] Chantier agents-specialises, lot 12 (A1) : la case « Retour au principal » d'une étape.
 *
 * La dernière étape d'un agent spécialisé rend l'appel à l'agent principal : le CODE lance la
 * passation, sans annonce ni musique, dès que l'appel arrive dans l'étape marquée. La case écrit le
 * marqueur ``retour_au_principal`` dans les données de l'étape (lu par ``services/groupe/passations.py``).
 *
 * N'existe que dans la fenêtre d'une étape d'un agent qui a un ``agent_principal_id`` (un agent seul
 * ou un principal ne la voit pas). Cochée par défaut sur la dernière étape que crée « + Agent
 * spécialisé » (côté API). La fenêtre d'une étape n'est jamais traduite (T3), mais ce composant est
 * le nôtre : ses textes sont dans les deux langues.
 */
import Link from "next/link";

import { Switch } from "@/components/ui/switch";

import { ChampReglage } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";

export const MARQUEUR_RETOUR = "retour_au_principal";

const TEXTES = {
    libelle: { en: "Back to the main agent", fr: "Retour au principal" },
    aide: {
        en: "At the end of this step, the call goes back to the main agent.",
        fr: "À la fin de cette étape, l'appel revient à l'agent principal.",
    },
    aide2: {
        en: "The code hands the call back, with no announcement and no music: the main agent reads the caller's last answer and routes or closes. Put no hand-over tool and no way out to the end on this step.",
        fr: "Le code rend l'appel, sans annonce ni musique : le principal lit la dernière réponse de l'appelant puis oriente ou clôt. Ne mettre sur cette étape aucun outil de passation ni aucune sortie vers la fin.",
    },
    ouvrir: { en: "Open the main agent", fr: "Ouvrir l'agent principal" },
} satisfies Record<string, Texte>;

export const RetourAuPrincipal = ({
    coche,
    onChange,
    agentPrincipalId,
}: {
    coche: boolean;
    onChange: (coche: boolean) => void;
    agentPrincipalId: number;
}) => {
    const { t } = useLangue();
    return (
        <ChampReglage
            cle={MARQUEUR_RETOUR}
            idControle={MARQUEUR_RETOUR}
            libelle={TEXTES.libelle}
            aides={[TEXTES.aide, TEXTES.aide2]}
            disposition="ligne"
        >
            <div className="flex items-center gap-3">
                <Link href={`/workflow/${agentPrincipalId}`} target="_blank" className="text-xs underline">
                    {t(TEXTES.ouvrir)}
                </Link>
                <Switch id={MARQUEUR_RETOUR} checked={coche} onCheckedChange={onChange} />
            </div>
        </ChampReglage>
    );
};
