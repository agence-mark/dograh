/**
 * [.mark] RA-B (R6, audit 06) : ce que dit l'écran d'un appel que le juge n'a pas noté, d'après l'état écrit par l'après-appel
 * dans `annotations.juge.etat` (`api/services/juge/appels.py`, `tri.py`). Un état qu'on ne connaît pas ne montre rien.
 */
import type { Texte } from "../langue/langue";

export const LIBELLES_ETAT_DU_JUGE: Record<string, Texte> = {
    budget_atteint: {
        en: "Not judged: the judge's monthly budget is reached.",
        fr: "Non jugé : le budget du mois du juge est atteint.",
    },
    non_regle: {
        en: "Not judged: the judge is switched on for this agent but not set up (switched off or no key in the Labo settings).",
        fr: "Non jugé : le juge est allumé sur cet agent mais pas réglé (éteint ou sans clé dans les Réglages du Labo).",
    },
    a_juger: { en: "Waiting in « To judge » (Claude Code).", fr: "En attente dans « À juger » (Claude Code)." },
    sans_transcription: { en: "Not judged: no transcript to read.", fr: "Non jugé : aucune transcription à lire." },
    trop_court: { en: "Not judged: the call is shorter than the minimum duration.", fr: "Non jugé : l'appel est plus court que la durée minimale." },
    repondeur: { en: "Not judged: the call ended on an answering machine.", fr: "Non jugé : l'appel a fini sur un répondeur." },
    non_echantillonne: { en: "Not judged: outside the share of calls judged.", fr: "Non jugé : hors de la part des appels jugés." },
};

/** Le libellé d'un état, ou `null` pour un appel jugé (`juge`) ou un état inconnu. */
export const libelleEtatDuJuge = (etat: unknown): Texte | null =>
    typeof etat === "string" && etat in LIBELLES_ETAT_DU_JUGE ? LIBELLES_ETAT_DU_JUGE[etat] : null;
