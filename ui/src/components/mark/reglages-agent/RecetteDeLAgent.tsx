"use client";

/**
 * [.mark] Lot M (pièce 7) : la recette de l'agent, en tête de l'onglet Réglages. Lue sur l'agent (`GET /builder/agents/{id}/recette`) ;
 * la liste des recettes vient de la bibliothèque. Elle se change librement tant qu'aucune version n'est publiée ; après une
 * publication (partie 3, SE-6) le changement passe par un avertissement (l'agent change de comportement) et ses tests sont à
 * rejouer avant de republier : le serveur le garde. Conçue sans maquette : composants de la maquette (`Info`), jetons seulement. Rien à l'écran sans réponse du serveur.
 */
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";

import {
    changerLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecettePut,
    lireLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecetteGet,
    listerLesRecettesApiV1BuilderRecettesGet,
} from "@/client/sdk.gen";
import { notifier } from "@/components/mark/notifications";
import { ListeDeroulante } from "@/components/mark/studio/liste-deroulante";
import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";

const T = {
    titre: { en: "Recipe", fr: "Recette" },
    info: {
        en: "How the builder builds this agent (its pieces and method, read from the library). After a publication, changing it asks for a confirmation and the tests must be replayed before publishing again.",
        fr: "La façon dont le builder construit cet agent (ses pièces et sa méthode, lues dans la bibliothèque). Après une publication, la changer demande une confirmation et les tests sont à rejouer avant de republier.",
    },
    nonIndiquee: { en: "none chosen: the default one applies", fr: "aucune choisie : celle par défaut s'applique" },
    nonProuvee: { en: "not proven", fr: "non prouvée" },
    publiee: { en: "A version is published: changing it asks for a confirmation.", fr: "Une version est publiée : la changer demande une confirmation." },
    aRejouer: { en: "Tests to replay before publishing again.", fr: "Tests à rejouer avant de republier." },
    avertissementTitre: { en: "Change the recipe of a published agent?", fr: "Changer la recette d'un agent publié ?" },
    avertissement: {
        en: "A version of this agent is already published. A new recipe changes how the builder builds it: the agent can behave differently. Its tests must be replayed before you publish again; the publication stays blocked until then.",
        fr: "Une version de cet agent est déjà publiée. Une autre recette change la façon dont le builder le construit : l'agent peut se comporter autrement. Ses tests sont à rejouer avant de republier ; la publication reste bloquée d'ici là.",
    },
    annuler: { en: "Cancel", fr: "Annuler" },
    confirmer: { en: "Change the recipe", fr: "Changer la recette" },
    changeeATester: { en: "Recipe changed. Replay the tests before publishing again.", fr: "Recette changée. Rejouez les tests avant de republier." },
    changee: { en: "Recipe changed.", fr: "Recette changée." },
    echec: { en: "The recipe could not be changed.", fr: "La recette n'a pas pu être changée." },
} satisfies Record<string, Texte>;

type Une = { slug: string; nom: string; prouvee: boolean };
type VueAgent = { recette: Une | null; indiquee: boolean; modifiable: boolean; tests_a_rejouer_depuis?: string | null };

export function RecetteDeLAgent({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [vue, setVue] = useState<VueAgent | null>(null);
    const [liste, setListe] = useState<Une[]>([]);
    const [demandee, setDemandee] = useState<string | null>(null); // SE-6 : la recette choisie, en attente de confirmation
    const [enCours, setEnCours] = useState(false);

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

    const changer = async (slug: string, confirmer = false) => {
        setEnCours(true);
        // `confirmer` (SE-6) : la route l'accepte ; le client généré le reçoit au prochain passage du générateur.
        const corps = (confirmer ? { recette: slug, confirmer } : { recette: slug }) as { recette: string };
        const r = await changerLaRecetteDeLAgentApiV1BuilderAgentsWorkflowIdRecettePut({ path: { workflow_id: workflowId }, body: corps });
        setEnCours(false);
        setDemandee(null);
        if (r.error || !r.data) return notifier.echec(T.echec, { erreur: r.error });
        const neuve = r.data as VueAgent;
        setVue(neuve);
        if (neuve.tests_a_rejouer_depuis) notifier.avertissement(T.changeeATester);
        else notifier.succes(T.changee);
    };
    // Avant toute publication : un clic change. Après : un avertissement d'abord.
    const choisir = (slug: string) => {
        if (vue.modifiable) void changer(slug);
        else setDemandee(slug);
    };

    const courante = vue.recette;
    return (
        <section className="flex flex-wrap items-center gap-3 py-2 text-sm" data-section="recette-de-l-agent">
            <span className="flex items-center gap-1.5 font-medium">
                {t(T.titre)}
                <Info>{t(T.info)}</Info>
            </span>
            <ListeDeroulante
                aria-label={t(T.titre)}
                className="cursor-pointer rounded-md border bg-background px-2 py-1"
                value={vue.indiquee ? (courante?.slug ?? "") : ""}
                onChange={(e) => e.target.value && choisir(e.target.value)}
            >
                {!vue.indiquee && <option value="">{t(T.nonIndiquee)}</option>}
                {liste.map((r) => (
                    <option key={r.slug} value={r.slug}>
                        {r.nom}
                        {r.prouvee ? "" : ` (${t(T.nonProuvee)})`}
                    </option>
                ))}
            </ListeDeroulante>
            {!vue.modifiable && <span className="text-xs text-muted-foreground">{t(T.publiee)}</span>}
            {vue.tests_a_rejouer_depuis && (
                <span data-recette-tests-a-rejouer className="text-xs font-medium">
                    {t(T.aRejouer)}
                </span>
            )}
            <Dialog open={demandee !== null} onOpenChange={(o) => !o && !enCours && setDemandee(null)}>
                <DialogContent className="sm:max-w-md" data-fenetre-recette-publiee>
                    <DialogHeader>
                        <DialogTitle>{t(T.avertissementTitre)}</DialogTitle>
                        <DialogDescription>{t(T.avertissement)}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button type="button" variant="outline" className="cursor-pointer" autoFocus disabled={enCours} onClick={() => setDemandee(null)}>
                            {t(T.annuler)}
                        </Button>
                        <Button
                            type="button"
                            className="cursor-pointer"
                            disabled={enCours}
                            data-confirmer-recette
                            onClick={() => demandee && void changer(demandee, true)}
                        >
                            {t(T.confirmer)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </section>
    );
}
