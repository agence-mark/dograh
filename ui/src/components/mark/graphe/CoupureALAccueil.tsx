"use client";

/**
 * [.mark] Clôture, SA-3 (D14, Evan, 09/11) : « Couper l'agent à l'accueil » vit sur la fenêtre de l'ÉTAPE DE DÉPART, là où il
 * sert, et nulle part ailleurs (il a quitté le thème « Tour de parole » des réglages de l'agent : un seul endroit).
 *
 * Ce sont quatre réglages DE L'AGENT (pas de l'étape), lus et écrits avec les réglages de l'agent par `reglagesDeLAgent` du
 * contexte du graphe : la protection de la phrase d'accueil, « L'appelant peut couper l'accueil » (maquette : « L'appelant peut
 * couper la parole »), le nombre de mots, la protection de la toute première réplique. Mêmes libellés, aides, bornes et
 * valeurs par défaut que le catalogue des réglages (`Reglage`). Un bouton enregistre les quatre ensemble, avec sa notification.
 */
import { useEffect, useMemo, useState } from "react";

import { useWorkflow } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { Button } from "@/components/ui/button";
import { DEFAUTS_PIPECAT, type WorkflowConfigurations } from "@/types/workflow-configurations";

import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { CATALOGUE, type CleCatalogue, erreursDuCatalogue, Reglage } from "../reglages-agent/catalogue";
import { DESCRIPTION_COUPER_A_L_ACCUEIL, noteAccueil, TITRE_COUPER_A_L_ACCUEIL } from "../reglages-agent/ThemeTourDeParole";

export const CLES_COUPURE_A_L_ACCUEIL = ["mute_until_first_bot_complete", "accueil_interruptible", "accueil_mots_minimum", "mute_first_speech"] as const satisfies readonly CleCatalogue[];
type Cle = (typeof CLES_COUPURE_A_L_ACCUEIL)[number];

const T = {
    enregistrer: { en: "Save", fr: "Enregistrer" },
    aucune: { en: "No change", fr: "Aucune modification" },
    succes: { en: "Greeting protection saved.", fr: "Protection de l'accueil enregistrée." },
    echec: {
        en: "Greeting protection not saved. If the live version is protected, use a branch.",
        fr: "Protection de l'accueil non enregistrée. Si la version en ligne est protégée, passez par une branche.",
    },
    agent: { en: "A setting of the agent, not of this step only.", fr: "Un réglage de l'agent, pas de cette étape seule." },
} satisfies Record<string, Texte>;

const valeurDe = (configuration: Partial<WorkflowConfigurations> | null | undefined, cle: Cle): unknown =>
    (configuration as Record<string, unknown> | null | undefined)?.[cle] ?? (DEFAUTS_PIPECAT as unknown as Record<string, unknown>)[cle];

export function CoupureALAccueil() {
    const { t } = useLangue();
    const { reglagesDeLAgent, readOnly } = useWorkflow();
    const configuration = reglagesDeLAgent?.configuration ?? null;
    const enregistrees = useMemo(() => Object.fromEntries(CLES_COUPURE_A_L_ACCUEIL.map((c) => [c, valeurDe(configuration, c)])) as Record<Cle, unknown>, [configuration]);
    const [brouillon, setBrouillon] = useState<Record<Cle, unknown>>(enregistrees);
    const [enCours, setEnCours] = useState(false);
    const cle = JSON.stringify(enregistrees);
    useEffect(() => setBrouillon(JSON.parse(cle) as Record<Cle, unknown>), [cle]);

    if (!reglagesDeLAgent) return null;
    const modifie = JSON.stringify(brouillon) !== cle;
    const erreurs = erreursDuCatalogue(CLES_COUPURE_A_L_ACCUEIL, brouillon);
    // « Ne jamais laisser l'appelant couper » reste dans « Tour de parole » : il l'emporte sur l'accueil, et la note le dit.
    const note = noteAccueil({ ...brouillon, mute_always: valeurDe(configuration, "mute_always" as Cle) } as { accueil_interruptible?: unknown; mute_always?: unknown; mute_first_speech?: unknown });

    const enregistrer = async () => {
        setEnCours(true);
        try {
            await reglagesDeLAgent.enregistrer(brouillon as Partial<WorkflowConfigurations>);
            notifier.succes(T.succes);
        } catch (erreur) {
            notifier.echec(T.echec, { erreur });
        } finally {
            setEnCours(false);
        }
    };

    return (
        <section className="space-y-3 pt-2" data-bloc="coupure-a-l-accueil" aria-label={t(TITRE_COUPER_A_L_ACCUEIL)}>
            <div>
                <h3 className="text-sm font-semibold">{t(TITRE_COUPER_A_L_ACCUEIL)}</h3>
                <p className="text-xs text-muted-foreground">{t(DESCRIPTION_COUPER_A_L_ACCUEIL)}</p>
                <p className="text-xs text-muted-foreground">{t(T.agent)}</p>
            </div>
            {CLES_COUPURE_A_L_ACCUEIL.map((c) => (
                <Reglage
                    key={c}
                    cle={c}
                    valeur={brouillon[c]}
                    onChange={(v) => setBrouillon((avant) => ({ ...avant, [c]: v }))}
                    desactive={Boolean(readOnly) || (c === "accueil_mots_minimum" && !brouillon.accueil_interruptible)}
                />
            ))}
            {note && (
                <p className="text-xs font-medium text-foreground" data-note="accueil-annule">
                    {t(note)}
                </p>
            )}
            <div className="flex items-center justify-end gap-3">
                {erreurs.length > 0 && (
                    <span role="alert" className="mr-auto text-xs text-destructive">
                        {erreurs.map((e) => `${t(e.libelle)} : ${t(e.message)}`).join(" ; ")}
                    </span>
                )}
                {erreurs.length === 0 && !modifie && <span className="mr-auto text-xs text-muted-foreground">{t(T.aucune)}</span>}
                <Button size="sm" disabled={!modifie || erreurs.length > 0 || enCours || Boolean(readOnly)} onClick={() => void enregistrer()}>
                    {t(T.enregistrer)}
                </Button>
            </div>
        </section>
    );
}

// Les libellés viennent du catalogue des réglages : une seule source (le test le vérifie).
export const LIBELLES_COUPURE_A_L_ACCUEIL = CLES_COUPURE_A_L_ACCUEIL.map((c) => CATALOGUE[c].libelle as Texte);
