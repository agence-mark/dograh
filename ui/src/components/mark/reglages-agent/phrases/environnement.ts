"use client";

/**
 * [.mark] correctifs-apres-banc-v4, lot 5 : ce que la modale d'une règle lit autour d'elle (les étapes, les outils de
 * l'agent, la fiche, l'équipe, les délais lus ailleurs), construit une fois pour le thème Phrases et pour la fenêtre
 * d'une étape de l'éditeur : les deux ouvrent la MÊME modale.
 */
import { useMemo } from "react";

import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { useLangue } from "../../langue/langue";
import { useDestinations, useEquipe, useOutilsDeLAgent } from "./donnees";
import type { EnvironnementPhrases } from "./ModaleRegle";
import { type ContextePhrases, type EtapeGraphe, REPOS_DEFAUT_S } from "./modele";

const lireN = (texte: string | number | null | undefined): number | null => {
    if (texte === null || texte === undefined || String(texte).trim() === "") return null;
    const n = Number(String(texte).replace(",", "."));
    return Number.isFinite(n) ? n : null;
};

export const useEnvironnementPhrases = ({
    configuration,
    etapes,
    outilsUuids,
    actif,
    peutGroupe,
    workflowId,
    repos,
}: {
    configuration: Partial<WorkflowConfigurations> | null | undefined;
    etapes: EtapeGraphe[];
    outilsUuids: string[];
    actif: boolean;
    peutGroupe: boolean;
    /** L'agent dont on règle les phrases : cible des liens vers les réglages lus ailleurs. */
    workflowId?: number;
    /** La pause minimale en cours de saisie (secondes, texte) ; absente : celle de la configuration. */
    repos?: string;
}): { env: EnvironnementPhrases; contexte: ContextePhrases } => {
    const { t, langue } = useLangue();
    const outils = useOutilsDeLAgent(outilsUuids, actif);
    const equipe = useEquipe(actif);
    const destinations = useDestinations(equipe);
    const reposS = lireN(repos ?? configuration?.phrases_repos_s) ?? REPOS_DEFAUT_S;
    const maxOutil = useMemo(() => {
        const delais = outils.map((o) => o.delaiTotalS).filter((d): d is number => d !== null);
        return delais.length > 0 ? Math.max(...delais) : null;
    }, [outils]);
    const travail = configuration?.travail_delai_max_s ?? 60;
    const garde = configuration?.delai_garde_modele_s ?? null;
    const delaiSilence = configuration?.max_user_idle_timeout ?? 10;
    const relances = configuration?.user_idle_max_prompts ?? 0;
    const contexte: ContextePhrases = useMemo(
        () => ({
            langue,
            t,
            reposS,
            abandonS: { outil: maxOutil, travail, garde },
            rythme: { delaiS: delaiSilence, relances },
            destinations,
        }),
        [langue, t, reposS, maxOutil, travail, garde, delaiSilence, relances, destinations],
    );
    const champs = configuration?.fiche_champs;
    const env: EnvironnementPhrases = useMemo(
        () => ({
            etapes,
            outils,
            champsFiche: (champs ?? []).map((c) => ({ nom: c.nom, valeurs: c.valeurs ?? null })),
            equipe,
            peutGroupe,
            workflowId,
            contexte,
        }),
        [etapes, outils, champs, equipe, peutGroupe, workflowId, contexte],
    );
    return { env, contexte };
};
