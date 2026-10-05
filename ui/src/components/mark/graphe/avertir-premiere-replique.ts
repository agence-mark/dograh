/**
 * [.mark] Plan porte-parlee (D3, D18): after the graph is saved, warn — never
 * block — when the agent takes its transitions in the reply and a step a
 * transition leads to has no "First reply". Same rule as the code that reads the
 * box (Postscript, record on) and as the list under the box in the settings.
 */
import { type Langue, LANGUE_PAR_DEFAUT, lireLangueGardee, type Texte } from "../langue/langue";
import { etapesSansPremiereReplique } from "./premiere-replique";

interface ConfigurationLue {
    fiche_au_fil_de_leau?: boolean;
    fiche_mode_de_note?: string;
    portes_dans_la_reponse?: boolean;
}

export const DEBUT_AVERTISSEMENT: Texte = {
    en: "Transitions in the reply: steps without a first reply (the agent gets a generic line instead): ",
    fr: "Portes dans la réponse : étapes sans première réplique (l'agent reçoit une ligne générique à la place) : ",
};

/** The warning to show after a save, or null when there is nothing to say. */
export const avertissementApresEnregistrement = (
    definition: Parameters<typeof etapesSansPremiereReplique>[0],
    configurations: ConfigurationLue | null | undefined,
    langue: Langue = lireLangueGardee() ?? LANGUE_PAR_DEFAUT,
): string | null => {
    if (
        !configurations?.fiche_au_fil_de_leau
        || configurations.fiche_mode_de_note !== "post_scriptum"
        || configurations.portes_dans_la_reponse !== true
    ) {
        return null;
    }
    const etapes = etapesSansPremiereReplique(definition);
    return etapes.length ? `${DEBUT_AVERTISSEMENT[langue]}${etapes.join(", ")}` : null;
};
