/**
 * [.mark] Partie 3, sous-lot 20 : une couleur par type de transition (façon ElevenLabs : vert succès, bleu condition, neutre
 * quand c'est le modèle qui décide). Couleurs par jetons seulement (`mark-theme.css`), jamais d'orange.
 * Le type se lit dans les données de la liaison : rien n'est recalculé ailleurs.
 */
import type { FlowEdgeData } from "@/components/flow/types";
import type { Texte } from "@/components/mark/langue/langue";

export type TypeDeTransition = "modele" | "fiche-complete" | "fiche-champ";

export function typeDeTransition(data?: Pick<FlowEdgeData, "condition_sur_la_fiche">): TypeDeTransition {
    const c = data?.condition_sur_la_fiche;
    if (c?.etape_complete) return "fiche-complete";
    if (c?.champ) return "fiche-champ";
    return "modele";
}

export const STYLE_TRANSITION: Record<TypeDeTransition, { trait: string; pastille: string; nom: Texte }> = {
    modele: {
        trait: "var(--liaison)",
        pastille: "border-black/10 bg-background text-muted-foreground",
        nom: { en: "The model decides", fr: "Le modèle décide" },
    },
    "fiche-complete": {
        trait: "var(--marque-succes-texte)",
        pastille: "border-(--marque-succes-texte)/40 bg-(--marque-succes) text-(--marque-succes-texte)",
        nom: { en: "Record step complete", fr: "Étape de la fiche complète" },
    },
    "fiche-champ": {
        trait: "var(--acc)",
        pastille: "border-(--acc)/40 bg-(--marque-attention) text-(--marque-attention-texte)",
        nom: { en: "A record field has a value", fr: "Un champ de la fiche a une valeur" },
    },
};
