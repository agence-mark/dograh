"use client";

/**
 * [.mark] Saving a theme of the agent page: exactly what the original cards sent.
 *
 * A theme gathers PARTS that came from different cards of the page as it was
 * (the end of turn from « General », the pause from « Speech Tuning »…). Each
 * card sent `{ ...resolved configuration, ...its own values }`. So a theme sends
 * the resolved configuration, then the values of every part that was CHANGED,
 * each computed the way its card computed it (trimmed lead fields, normalized
 * dispositions, voicemail instructions kept only when they differ from the
 * built-in text…). A part left alone is not re-sent: the resolved value it
 * already has is what goes, as it went before.
 *
 * Parts that save through another route (the template variables, the
 * dictionary) are saved after, in that order, by their original functions.
 * A failure names the part (plan § 4: « une erreur nomme la partie »).
 *
 * `references/charges-utiles-agent.test.tsx` holds this to the payloads frozen
 * on the page as it was, case by case.
 */
import { useState } from "react";
import { toast } from "sonner";

import { detailFromError } from "@/lib/apiError";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { type Texte, useLangue } from "../langue/langue";

export const RAPPEL_PUBLICATION_TEXTE: Texte = {
    en: "Publish the agent to apply the changes.",
    fr: "Publiez l'agent pour appliquer les changements.",
};

export type Enregistrer = (configurations: WorkflowConfigurations, workflowName: string) => Promise<void>;

export interface Partie {
    /** Its name, for a failure (« Opening hours not saved: … »). */
    nom: Texte;
    modifie: boolean;
    /** The keys this part adds to the configuration payload, computed like its card did. */
    config?: () => Record<string, unknown>;
    /** The agent's name, when this part is the name (theme Agent). */
    nomAgent?: () => string;
    /** A part saved through another route (template variables, dictionary). */
    enregistrerAutrement?: () => Promise<void>;
    /** What the original card did once saved (resynchronize a list, forget an edit…). */
    apres?: () => void;
    /** A failure of this part, shown under its field (the opening hours' line number). */
    surEchec?: (message: string) => void;
}

export class EchecPartie extends Error {
    constructor(
        public readonly parties: Texte[],
        message: string,
    ) {
        super(message);
    }
}

/** The payload and the name of the configuration save, or null when no such part changed. */
export const chargeDuTheme = (
    resolue: WorkflowConfigurations,
    workflowName: string,
    parties: Partie[],
): { configurations: WorkflowConfigurations; nom: string; parties: Partie[] } | null => {
    const concernees = parties.filter((p) => p.modifie && (p.config || p.nomAgent));
    if (concernees.length === 0) return null;
    const configurations = { ...resolue } as WorkflowConfigurations;
    for (const partie of concernees) Object.assign(configurations, partie.config?.() ?? {});
    const partieNom = concernees.find((p) => p.nomAgent);
    return { configurations, nom: partieNom?.nomAgent?.() ?? workflowName, parties: concernees };
};

export const useEnregistrementTheme = ({
    titre,
    resolue,
    workflowName,
    onSave,
    parties,
}: {
    titre: Texte;
    resolue: WorkflowConfigurations;
    workflowName: string;
    onSave: Enregistrer;
    parties: Partie[];
}) => {
    const { t } = useLangue();
    const [enCours, setEnCours] = useState(false);

    const enregistrer = async () => {
        setEnCours(true);
        const reussies: Partie[] = [];
        try {
            // ⛔ The other routes FIRST (review of 26/09, B1). Dograh's variables
            // and dictionary saves send the agent's name as it was when the page
            // last rendered; sent after a rename, they would put the old name
            // back on the server. The configuration save, which carries the name
            // typed, therefore always comes last; it reads the dictionary from
            // the store, so the order is harmless for Listening.
            for (const partie of parties) {
                if (!partie.modifie || !partie.enregistrerAutrement) continue;
                try {
                    await partie.enregistrerAutrement();
                    reussies.push(partie);
                } catch (erreur) {
                    throw new EchecPartie(
                        [partie.nom],
                        erreur instanceof Error && erreur.message
                            ? erreur.message
                            : detailFromError(erreur, "Not saved."),
                    );
                }
            }
            const charge = chargeDuTheme(resolue, workflowName, parties);
            if (charge) {
                try {
                    await onSave(charge.configurations, charge.nom);
                    reussies.push(...charge.parties);
                } catch (erreur) {
                    throw new EchecPartie(
                        charge.parties.map((p) => p.nom),
                        erreur instanceof Error && erreur.message
                            ? erreur.message
                            : detailFromError(erreur, "Not saved."),
                    );
                }
            }
            reussies.forEach((p) => p.apres?.());
            toast.success(
                `${t({ en: `${titre.en} saved.`, fr: `${titre.fr} : enregistré.` })} ${t(RAPPEL_PUBLICATION_TEXTE)}`,
            );
        } catch (erreur) {
            reussies.forEach((p) => p.apres?.());
            if (erreur instanceof EchecPartie) {
                const noms = erreur.parties.map((p) => t(p)).join(", ");
                const message = erreur.message.replace(/^Value error,\s*/gm, "");
                parties.filter((p) => erreur.parties.includes(p.nom)).forEach((p) => p.surEchec?.(message));
                toast.error(`${noms}: ${t({ en: "not saved", fr: "non enregistré" })}. ${message}`);
            } else {
                toast.error(t({ en: "Not saved. Check the values and try again.", fr: "Non enregistré. Vérifiez les valeurs et réessayez." }));
            }
        } finally {
            setEnCours(false);
        }
    };

    return { enCours, enregistrer };
};
