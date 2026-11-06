"use client";

/**
 * [.mark] U4 (E42, E44) puis partie 3 (SA-L3a) : « Prêt à publier », en tête de l'onglet Réglages.
 *
 * La MÊME liste que la fenêtre « Publier » (`agent/pret/ListePret`), calculée par le serveur (`GET /workflow/{id}/preparation`),
 * jamais stockée, relue après chaque enregistrement et chaque geste du builder. Quatre états ; « Régler » ouvre l'endroit exact
 * (thème de cette page, étape du graphe, onglet) ; un réglage sans effet propose sa correction en un clic. Une lecture qui
 * échoue le dit, sans inventer d'état.
 */
import { useRouter } from "next/navigation";

import { ListePret, useListeDePret } from "../agent/pret/ListePret";
import { useCorrectionEnUnClic } from "../agent/pret/useCorrection";
import { endroitDeLaLigne } from "../agent/pret/endroit";
import { type Texte, useLangue } from "../langue/langue";

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

export const PreparationAgent = ({
    workflowId,
    versTheme,
    recalcul,
}: {
    workflowId: number;
    versTheme: (theme: string) => void;
    /** Ce qui change à chaque enregistrement de l'agent (ses réglages) : la liste se relit. */
    recalcul?: unknown;
}) => {
    const { t } = useLangue();
    const router = useRouter();
    const { lignes, echec, relire } = useListeDePret(workflowId, recalcul);
    const { corriger, enCours } = useCorrectionEnUnClic(workflowId, relire);

    if (echec) {
        return (
            <p className="text-sm text-muted-foreground" data-preparation="echec">
                {t({ en: "The preparation list could not be read.", fr: "La liste de préparation n'a pas pu être lue." })}
            </p>
        );
    }
    if (!lignes) return null;
    return (
        <ListePret
            avecAnneau
            lignes={lignes}
            textesDesEtapes={TEXTES_ETAPES}
            enCours={enCours}
            corriger={(_, c) => void corriger(c)}
            regler={(ligne) => {
                const endroit = endroitDeLaLigne(ligne, workflowId);
                if (endroit.sorte === "theme") versTheme(endroit.theme);
                else router.push(endroit.adresse);
            }}
        />
    );
};
