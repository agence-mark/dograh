"use client";

/**
 * [.mark] U4 (E42, E44) : la liste de préparation d'un agent, en tête de l'onglet Réglages.
 *
 * Calculée par le serveur à l'ouverture (`GET /workflow/{id}/preparation`), jamais stockée. Étape requise non faite =
 * cercle rouge ; conseillée non faite = cercle bleu .mark (jamais d'orange, E100) ; faite = coche. La source de chaque
 * étape est dite dans le « ! ». Une ligne cliquable ouvre le thème qui règle l'étape. Une étape « sans objet » n'est pas
 * montrée ; une lecture qui échoue le dit, sans inventer d'état.
 */
import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import { lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet } from "@/client/sdk.gen";
import type { EtapeDePreparation } from "@/client/types.gen";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";

export const TEXTES_ETAPES: Record<string, { titre: Texte; source: Texte }> = {
    variables: {
        titre: { en: "Variables of the prompts filled", fr: "Variables des prompts remplies" },
        source: {
            en: "Computed from the variables the prompts and sentences read, against the template variables and the ones a step extracts.",
            fr: "Calculé depuis les variables que lisent les prompts et les phrases, contre les variables du modèle et celles qu'une étape extrait.",
        },
    },
    briques: {
        titre: { en: "Models configured", fr: "Modèles configurés" },
        source: {
            en: "Computed from the effective model configuration (brain, transcription, voice). No provider is contacted: « Test the connection » stays a gesture of yours.",
            fr: "Calculé depuis la configuration effective des modèles (cerveau, transcription, voix). Aucun fournisseur n'est contacté : « Tester la connexion » reste un geste de votre part.",
        },
    },
    outils: {
        titre: { en: "Tools connected", fr: "Outils branchés" },
        source: {
            en: "Computed from the tools the steps carry: each must exist and be active.",
            fr: "Calculé depuis les outils que portent les étapes : chacun doit exister et être actif.",
        },
    },
    tests: {
        titre: { en: "Tests up to date", fr: "Tests à jour" },
        source: {
            en: "Computed from the agent's tests and their last runs. A required test not replayed, or failing, blocks publishing.",
            fr: "Calculé depuis les tests de l'agent et leurs dernières exécutions. Un test obligatoire non rejoué, ou en échec, bloque la publication.",
        },
    },
    etablissement: {
        titre: { en: "Establishment attached and filled", fr: "Établissement rattaché et rempli" },
        source: {
            en: "Computed from the establishment sheet the agent chose: it must exist, with a name and an address or opening hours.",
            fr: "Calculé depuis la fiche d'établissement choisie par l'agent : elle doit exister, avec un nom et une adresse ou des horaires.",
        },
    },
    fiche: {
        titre: { en: "Call record defined", fr: "Fiche d'appel définie" },
        source: { en: "Computed from the fields of the call record.", fr: "Calculé depuis les champs de la fiche d'appel." },
    },
    panne: {
        titre: { en: "Fallback in case of outage", fr: "Repli en cas de panne" },
        source: { en: "Computed from the outage fallback setting.", fr: "Calculé depuis le réglage du repli en cas de panne." },
    },
    phrases: {
        titre: { en: "Fixed sentences set", fr: "Phrases fixes réglées" },
        source: { en: "Computed from the sentence rules of the code.", fr: "Calculé depuis les règles des phrases du code." },
    },
};

const Cercle = ({ etape }: { etape: EtapeDePreparation }) => {
    if (etape.etat === "fait") {
        return (
            <span data-cercle="fait" className="inline-flex size-4 shrink-0 items-center justify-center rounded-full bg-(--point-fini) text-white">
                <Check className="size-3" />
            </span>
        );
    }
    const requis = etape.niveau === "requis";
    return (
        <span
            data-cercle={requis ? "requis" : "conseille"}
            className={cn("inline-block size-4 shrink-0 rounded-full border-2", requis ? "border-destructive" : "border-(--acc)")}
        />
    );
};

export const PreparationAgent = ({ workflowId, versTheme }: { workflowId: number; versTheme: (theme: string) => void }) => {
    const { t } = useLangue();
    const [etapes, setEtapes] = useState<EtapeDePreparation[] | null>(null);
    const [echec, setEchec] = useState(false);

    useEffect(() => {
        let annule = false;
        (async () => {
            try {
                const reponse = await lireLaPreparationApiV1WorkflowWorkflowIdPreparationGet({ path: { workflow_id: workflowId } });
                if (annule) return;
                if (reponse.error || !reponse.data) setEchec(true);
                else setEtapes(reponse.data.etapes);
            } catch {
                if (!annule) setEchec(true);
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId]);

    if (echec) {
        return (
            <p className="text-sm text-muted-foreground" data-preparation="echec">
                {t({ en: "The preparation list could not be read.", fr: "La liste de préparation n'a pas pu être lue." })}
            </p>
        );
    }
    if (!etapes) return null;
    const visibles = etapes.filter((e) => e.etat !== "sans_objet");
    const restantes = visibles.filter((e) => e.etat !== "fait" && e.niveau === "requis").length;

    return (
        <section aria-label={t({ en: "Preparation", fr: "Préparation" })} data-preparation="liste" className="space-y-1">
            <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold">{t({ en: "Preparation", fr: "Préparation" })}</h2>
                <span className="text-xs text-muted-foreground" data-preparation="restantes">
                    {restantes === 0
                        ? t({ en: "Nothing required is missing", fr: "Rien d'obligatoire ne manque" })
                        : t({ en: `${restantes} required to do`, fr: `${restantes} obligatoire${restantes > 1 ? "s" : ""} à faire` })}
                </span>
            </div>
            <ul className="divide-y">
                {visibles.map((etape) => {
                    const textes = TEXTES_ETAPES[etape.id];
                    if (!textes) return null;
                    return (
                        <li key={etape.id} data-etape={etape.id} data-etat={etape.etat}>
                            <button
                                type="button"
                                onClick={() => versTheme(etape.theme)}
                                className="flex w-full cursor-pointer items-center gap-3 py-2 text-left text-sm hover:font-semibold"
                            >
                                <Cercle etape={etape} />
                                <span className="min-w-0 flex-1 truncate">
                                    {t(textes.titre)}
                                    {etape.etat !== "fait" && (etape.manquants ?? []).length > 0 && (
                                        <span className="ml-2 text-xs font-normal text-muted-foreground">{(etape.manquants ?? []).join(", ")}</span>
                                    )}
                                </span>
                                <Info>{t(textes.source)}</Info>
                            </button>
                        </li>
                    );
                })}
            </ul>
        </section>
    );
};
