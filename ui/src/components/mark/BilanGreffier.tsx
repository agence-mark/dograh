"use client";

/**
 * [.mark] The clerk's account of a call (plan mode-prise-de-notes, part 2).
 *
 * Each clerk pass leaves a line in the call record (`greffier_passes`, written
 * by `api/services/pipecat/greffier.py`). This card adds them up on the call's
 * page: how many passes, what they wrote, what failed, and the tokens they
 * used -- the clerk's cost, readable apart from the conversation's. A clerk
 * whose passes fail (wrong key, unknown model) does not switch the call back to
 * the tool: this card is where it shows. Nothing is drawn for a call without a
 * clerk.
 */
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { useLangue } from "./langue/langue";

export const CLE_PASSES_DU_GREFFIER = "greffier_passes";

type Passe = {
    etat?: string;
    jetons_entree?: number | null;
    jetons_sortie?: number | null;
    erreur?: string;
};

export type Bilan = {
    passes: number;
    ecrites: number;
    sansRien: number;
    echecs: number;
    illisibles: number;
    sautees: number;
    tardives: number;
    jetonsEntree: number;
    jetonsSortie: number;
    erreurs: string[];
};

export const bilanDuGreffier = (fiche: Record<string, unknown> | null | undefined): Bilan | null => {
    const brutes = fiche?.[CLE_PASSES_DU_GREFFIER];
    if (!Array.isArray(brutes) || brutes.length === 0) return null;
    const passes = brutes.filter((p): p is Passe => Boolean(p) && typeof p === "object");
    const compte = (etat: string) => passes.filter((p) => p.etat === etat).length;
    const somme = (cle: "jetons_entree" | "jetons_sortie") =>
        passes.reduce((total, p) => total + (typeof p[cle] === "number" ? (p[cle] as number) : 0), 0);
    return {
        passes: passes.length,
        ecrites: compte("ecrit"),
        sansRien: compte("rien"),
        echecs: compte("echec"),
        illisibles: compte("illisible"),
        sautees: compte("saute"),
        tardives: compte("tardive"),
        jetonsEntree: somme("jetons_entree"),
        jetonsSortie: somme("jetons_sortie"),
        erreurs: [...new Set(passes.map((p) => p.erreur).filter((e): e is string => Boolean(e)))],
    };
};

export const BilanGreffier = ({ fiche }: { fiche: Record<string, unknown> | null | undefined }) => {
    const { t } = useLangue();
    const bilan = bilanDuGreffier(fiche);
    if (!bilan) return null;
    const enEchec = bilan.echecs + bilan.illisibles;
    return (
        <Card data-testid="bilan-greffier">
            <CardHeader>
                <CardTitle>{t({ en: "Clerk", fr: "Greffier" })}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
                {enEchec > 0 && (
                    <p className="font-medium text-destructive" role="alert">
                        {t({
                            en: `The clerk failed ${enEchec} time(s) out of ${bilan.passes}${
                                bilan.erreurs.length ? ` (${bilan.erreurs.join(", ")})` : ""
                            }: check its model and its key. The end-of-call pass filled the empty fields.`,
                            fr: `Le greffier a échoué ${enEchec} fois sur ${bilan.passes}${
                                bilan.erreurs.length ? ` (${bilan.erreurs.join(", ")})` : ""
                            } : vérifiez son modèle et sa clé. La passe de fin d'appel a rempli les champs vides.`,
                        })}
                    </p>
                )}
                <p>
                    {t({
                        en: `${bilan.passes} passes: ${bilan.ecrites} wrote, ${bilan.sansRien} with nothing new, ${bilan.sautees} skipped for rate limit, ${bilan.tardives} after the call.`,
                        fr: `${bilan.passes} passes : ${bilan.ecrites} ont écrit, ${bilan.sansRien} sans rien de nouveau, ${bilan.sautees} sautées pour quota, ${bilan.tardives} après l'appel.`,
                    })}
                </p>
                <p className="text-muted-foreground">
                    {t({
                        en: `Tokens: ${bilan.jetonsEntree} in, ${bilan.jetonsSortie} out (the clerk's cost, apart from the conversation).`,
                        fr: `Jetons : ${bilan.jetonsEntree} en entrée, ${bilan.jetonsSortie} en sortie (le coût du greffier, à part de la conversation).`,
                    })}
                </p>
            </CardContent>
        </Card>
    );
};
