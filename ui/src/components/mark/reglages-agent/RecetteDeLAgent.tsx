"use client";

/**
 * [.mark] Lot M (pièce 7) : la recette de l'agent, en tête de l'onglet Réglages. Lue sur l'agent (`GET /builder/agents/{id}/recette`) ;
 * la liste des recettes vient de la bibliothèque. Elle se change tant qu'aucune version n'est publiée ; ensuite elle est montrée sans
 * pouvoir changer. Conçue sans maquette : composants de la maquette (`Info`), jetons seulement. Rien à l'écran sans réponse du serveur.
 */
import { useEffect, useState } from "react";

import {
    changerLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecettePut,
    lireLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecetteGet,
    listerLesRecettesApiV1BuilderRecettesGet,
} from "@/client/sdk.gen";
import { notifier } from "@/components/mark/notifications";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";

const T = {
    titre: { en: "Recipe", fr: "Recette" },
    info: {
        en: "How the builder builds this agent (its pieces and method, read from the library). It can be changed until a version is published.",
        fr: "La façon dont le builder construit cet agent (ses pièces et sa méthode, lues dans la bibliothèque). Elle se change tant qu'aucune version n'est publiée.",
    },
    nonIndiquee: { en: "none chosen: the default one applies", fr: "aucune choisie : celle par défaut s'applique" },
    nonProuvee: { en: "not proven", fr: "non prouvée" },
    figee: { en: "Locked: a version is published.", fr: "Figée : une version est publiée." },
    changee: { en: "Recipe changed.", fr: "Recette changée." },
    echec: { en: "The recipe could not be changed.", fr: "La recette n'a pas pu être changée." },
} satisfies Record<string, Texte>;

type Une = { slug: string; nom: string; prouvee: boolean };
type VueAgent = { recette: Une | null; indiquee: boolean; modifiable: boolean };

export function RecetteDeLAgent({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [vue, setVue] = useState<VueAgent | null>(null);
    const [liste, setListe] = useState<Une[]>([]);

    useEffect(() => {
        void Promise.all([
            lireLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecetteGet({ path: { workflow_id: workflowId } }),
            listerLesRecettesApiV1BuilderRecettesGet(),
        ]).then(([agent, recettes]) => {
            if (agent?.data) setVue(agent.data as VueAgent);
            const lues = (recettes?.data as { recettes: Une[] } | undefined)?.recettes;
            if (lues) setListe(lues);
        });
    }, [workflowId]);

    if (!vue || (!vue.recette && liste.length === 0)) return null;

    const changer = async (slug: string) => {
        const r = await changerLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecettePut({ path: { workflow_id: workflowId }, body: { recette: slug } });
        if (r.error || !r.data) return notifier.echec({ en: `${t(T.echec)} ${detailFromError(r.error, "")}`.trim(), fr: T.echec.fr });
        setVue(r.data as VueAgent);
        notifier.succes(T.changee);
    };

    const courante = vue.recette;
    return (
        <section className="flex flex-wrap items-center gap-3 py-2 text-sm" data-section="recette-de-l-agent">
            <span className="flex items-center gap-1.5 font-medium">
                {t(T.titre)}
                <Info>{t(T.info)}</Info>
            </span>
            {vue.modifiable ? (
                <select
                    aria-label={t(T.titre)}
                    className="cursor-pointer rounded-md border bg-background px-2 py-1"
                    value={vue.indiquee ? (courante?.slug ?? "") : ""}
                    onChange={(e) => e.target.value && void changer(e.target.value)}
                >
                    {!vue.indiquee && <option value="">{t(T.nonIndiquee)}</option>}
                    {liste.map((r) => (
                        <option key={r.slug} value={r.slug}>
                            {r.nom}
                            {r.prouvee ? "" : ` (${t(T.nonProuvee)})`}
                        </option>
                    ))}
                </select>
            ) : (
                <span data-recette-figee>
                    {courante?.nom ?? ""} <span className="text-xs text-muted-foreground">{t(T.figee)}</span>
                </span>
            )}
        </section>
    );
}
