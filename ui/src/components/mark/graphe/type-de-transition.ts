/**
 * [.mark] Partie 3, sous-lot 20 : une couleur par type de transition (façon ElevenLabs : vert succès, bleu condition, neutre
 * quand c'est le modèle qui décide). Couleurs par jetons seulement (`mark-theme.css`), jamais d'orange.
 * Le type se lit dans les données de la liaison : rien n'est recalculé ailleurs.
 * Sous-lot 21 : les règles vérifiées par le code, « toujours » et « sinon » (trait pointillé), et l'indicateur « code » ou
 * « modèle » (`decide`) de la maquette (✦ l'IA juge, { } le code vérifie).
 */
import type { FlowEdgeData } from "@/components/flow/types";
import type { Texte } from "@/components/mark/langue/langue";

export type TypeDeTransition = "modele" | "fiche-complete" | "fiche-champ" | "regles" | "toujours" | "sinon";
export type QuiDecideLiaison = "modele" | "code" | "toujours" | "sinon";

export function typeDeTransition(data?: Pick<FlowEdgeData, "condition_sur_la_fiche">): TypeDeTransition {
    const c = data?.condition_sur_la_fiche;
    if (c?.sinon) return "sinon";
    if (c?.toujours) return "toujours";
    if (c?.regles?.length) return "regles";
    if (c?.etape_complete) return "fiche-complete";
    if (c?.champ) return "fiche-champ";
    return "modele";
}

export const STYLE_TRANSITION: Record<TypeDeTransition, { trait: string; pastille: string; nom: Texte; decide: QuiDecideLiaison; pointille?: boolean }> = {
    modele: {
        trait: "var(--liaison)",
        pastille: "border-black/10 bg-background text-muted-foreground",
        nom: { en: "The model decides", fr: "Le modèle décide" },
        decide: "modele",
    },
    "fiche-complete": {
        trait: "var(--marque-succes-texte)",
        pastille: "border-(--marque-succes-texte)/40 bg-(--marque-succes) text-(--marque-succes-texte)",
        nom: { en: "Record step complete", fr: "Étape de la fiche complète" },
        decide: "code",
    },
    "fiche-champ": {
        trait: "var(--acc)",
        pastille: "border-(--acc)/40 bg-(--marque-attention) text-(--marque-attention-texte)",
        nom: { en: "A record field has a value", fr: "Un champ de la fiche a une valeur" },
        decide: "code",
    },
    regles: {
        trait: "var(--acc-fill)",
        pastille: "border-(--acc)/40 bg-(--marque-attention) text-(--marque-attention-texte)",
        nom: { en: "The code checks rules", fr: "Le code vérifie des règles" },
        decide: "code",
    },
    toujours: {
        trait: "var(--muted-foreground)",
        pastille: "border-black/10 bg-background text-foreground dark:border-white/15",
        nom: { en: "Always", fr: "Toujours" },
        decide: "toujours",
    },
    sinon: {
        trait: "var(--liaison)",
        pastille: "border-dashed border-black/20 bg-background text-muted-foreground dark:border-white/25",
        nom: { en: "Otherwise: when no other link passes", fr: "Sinon : quand aucune autre liaison ne passe" },
        decide: "sinon",
        pointille: true,
    },
};
