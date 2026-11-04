"use client";

/**
 * [.mark] Partie 3, sous-lot 1 (SE-9, A-4) : le thème « Qualité » de l'agent. Il porte le « Juge des vrais appels », réglage réel
 * qui flottait sous la grille des cartes : un réglage réel ne flotte pas. Le réglage s'enregistre à part (route propre, effet
 * immédiat) : le thème n'a donc pas de bouton d'enregistrement, comme les thèmes qui enregistrent ailleurs ou d'un coup.
 */
import { ClipboardCheck } from "lucide-react";

import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { JugeDesVraisAppels } from "./JugeDesVraisAppels";
import type { ProprietesThemeAgent } from "./theme-commun";

export const ID_THEME_QUALITE = "qualite";
export const TITRE_QUALITE = { en: "Quality", fr: "Qualité" };

export const ThemeQualite = ({ ouvert, onBasculer, workflowId }: Pick<ProprietesThemeAgent, "ouvert" | "onBasculer"> & { workflowId: number }) => {
    const { t } = useLangue();
    return (
        <Theme
            id={ID_THEME_QUALITE}
            icone={ClipboardCheck}
            titre={TITRE_QUALITE}
            description={{
                en: "How the real calls of this agent are judged. The setting is saved as soon as you change it.",
                fr: "La façon dont les vrais appels de cet agent sont jugés. Le réglage est enregistré dès que vous le changez.",
            }}
            resume={[t({ en: "Real-call judge", fr: "Juge des vrais appels" })]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={false}
            erreurs={[]}
        >
            <JugeDesVraisAppels workflowId={workflowId} />
        </Theme>
    );
};
