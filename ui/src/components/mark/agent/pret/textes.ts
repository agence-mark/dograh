/**
 * [.mark] Builder partie 3, SA-L3a : les textes de « Prêt à publier » (titres des lignes, ce qui manque, corrections en un clic).
 * Le serveur envoie des identifiants (`id`, `constat`, `corrections[].id`) et des noms (étapes, liaisons) : tout texte vit ici,
 * en français et en anglais.
 */
import type { Texte } from "../../langue/langue";
import { T as TEXTES_VERSIONS } from "../../outils/versions/textes";

export interface CorrectionDeLigne {
    id: string;
    noeud_id?: string | null;
    liaison_id?: string | null;
    nom?: string | null;
}

const guillemets = (nom: string | undefined) => (nom ? `« ${nom} »` : "");

export const TITRES_DES_LIGNES: Record<string, { titre: Texte; source: Texte }> = {
    // SA-L3d (décision 21) : ligne conseillée, présente seulement s'il reste un outil en retard.
    outils_a_jour: { titre: TEXTES_VERSIONS.outilsAJourTitre, source: TEXTES_VERSIONS.outilsAJourSource },
    bilan_du_prompt: {
        titre: { en: "The prompt health check is clean", fr: "Le bilan de santé du prompt est propre" },
        source: {
            en: "Read by the code: contradictions, unknown variable, tool named but missing. Only guards the agents the builder follows.",
            fr: "Lu par le code : contradictions, variable inconnue, outil cité mais absent. Ne garde que les agents suivis par le builder.",
        },
    },
    // Lot « façon Tala par motif » (T2, T3) : les contrôles de rédaction. Conseillés (ils préviennent par défaut), le bilan montre le détail.
    valeur_en_dur: {
        titre: { en: "No value is written in the prompts", fr: "Aucune valeur n'est écrite en dur dans les prompts" },
        source: {
            en: "An amount, a figure delay or a first name given as an example. See the prompt health check in the Publish window.",
            fr: "Un montant, un délai chiffré ou un prénom donné en exemple. Le détail est dans le bilan de santé du prompt, fenêtre Publier.",
        },
    },
    verbe_ecran: {
        titre: { en: "No screen verb in the prompts", fr: "Aucun verbe d'écran dans les prompts" },
        source: {
            en: "« Display », « click », « on the screen »: the caller on the phone has no screen.",
            fr: "« Afficher », « cliquer », « à l'écran » : la personne au téléphone n'a pas d'écran.",
        },
    },
    action_sans_outil: {
        titre: { en: "Every promised action has its tool", fr: "Chaque action promise a son outil" },
        source: {
            en: "A step that says « save », « book », « cancel », « send » carries a tool that writes.",
            fr: "Une étape qui dit « enregistrer », « réserver », « annuler », « envoyer » porte un outil qui écrit.",
        },
    },
    sortie_non_citee: {
        titre: { en: "Every step names its exits", fr: "Chaque étape cite ses sorties" },
        source: {
            en: "A step with two work exits or more names the steps it leads to in its text.",
            fr: "Une étape à deux sorties de travail ou plus cite dans son texte les étapes vers lesquelles elle mène.",
        },
    },
    poids_agent: {
        titre: { en: "The agent weight is within the brain's size", fr: "Le poids de l'agent tient dans la taille du cerveau" },
        source: {
            en: "What the brain reads at each reply, against the threshold set in Settings › Services. Informs, never blocks.",
            fr: "Ce que le cerveau lit à chaque réplique, comparé au seuil réglé dans Réglages › Briques. Informe, ne bloque jamais.",
        },
    },
    liste_vocale: {
        titre: { en: "The voice checklist is respected", fr: "La liste de contrôle vocale est respectée" },
        source: {
            en: "The points of the « Checks before publishing » library family, read on the agent's settings.",
            fr: "Les points de la famille « Contrôles avant publication » de la bibliothèque, lus sur les réglages de l'agent.",
        },
    },
    attaques: {
        titre: { en: "The attacks were played and held", fr: "Les attaques ont été jouées et ont tenu" },
        source: {
            en: "The last « Attack the agent » run on this draft. « Not tested » never counts as held.",
            fr: "Le dernier passage de « Attaquer l'agent » sur ce brouillon. « Non testé » n'est jamais compté comme tenu.",
        },
    },
    annonce_ia: {
        titre: { en: "The « you are talking to an AI » announcement has its text", fr: "L'annonce « vous parlez à une IA » a son texte" },
        source: {
            en: "Said at the start of every call and cannot be turned off. Only its text can change (Phrases theme); an empty text blocks publishing.",
            fr: "Dite en tête de chaque appel, impossible à éteindre. Seul son texte se change (thème Phrases) ; un texte vide bloque la publication.",
        },
    },
    // Lot 8 (décision d'Evan du 04/11) : bloquante, sans réglage ; présente seulement si un prompt cite un objet.
    etiquettes: {
        titre: { en: "The labels of the prompts are valid", fr: "Les étiquettes des prompts sont valides" },
        source: {
            en: "Every tool, step, agent, team subject, document, sentence or block cited by a label exists, is active, and every cited tool is attached to its step. Always blocks, no setting.",
            fr: "Chaque outil, étape, agent, sujet de l'équipe, document, phrase ou bloc cité par une étiquette existe, est actif, et chaque outil cité est rattaché à son étape. Bloque toujours, sans réglage.",
        },
    },
    // Lot 22 : conseillée, présente seulement si un prompt cite un bloc.
    blocs_a_jour: {
        titre: { en: "The blocks are up to date", fr: "Les blocs sont à jour" },
        source: {
            en: "A block kept on its version has a newer version in Recipe. Keeping it is allowed: this is only advice.",
            fr: "Un bloc resté sur sa version a une version plus récente en Recette. Rester est permis : ce n'est qu'un conseil.",
        },
    },
    garde_fous: {
        titre: { en: "A safety layer of the conversation is on", fr: "Une couche de sécurité de la conversation est allumée" },
        source: {
            en: "At least one safety layer of the conversation is on (Safety theme of the settings).",
            fr: "Au moins une couche de sécurité de la conversation est allumée (thème Sécurité des réglages).",
        },
    },
};

/** Les réglages « sans effet » : une ligne de « Prêt à publier » par cas, avec ce qu'il dit et pourquoi. */
export const TEXTES_DES_CONSTATS: Record<string, { titre: Texte; detail: (noms: string[]) => Texte; info: Texte }> = {
    condition_sur_le_modele: {
        titre: { en: "Rules on a step where the model decides", fr: "Règles sur une étape où le modèle décide" },
        detail: (n) => ({
            en: `The link ${guillemets(n[1])} of ${guillemets(n[0])} has rules on the record, but that step lets the model decide: they never play.`,
            fr: `La liaison ${guillemets(n[1])} de ${guillemets(n[0])} a des règles de la fiche, mais cette étape laisse le modèle décider : elles ne jouent jamais.`,
        }),
        info: {
            en: "A rule on the record is read only when the record decides the transition. When the model decides, it is ignored.",
            fr: "Une règle de la fiche n'est lue que si la fiche décide du passage. Quand le modèle décide, elle est ignorée.",
        },
    },
    collecte_sans_fiche: {
        titre: { en: "The record decides, but it is off", fr: "La fiche décide, mais elle est éteinte" },
        detail: (n) => ({
            en: `${guillemets(n[0])} passes through the record, and the record is not filled during the call: the step never passes.`,
            fr: `${guillemets(n[0])} passe par la fiche, et la fiche n'est pas remplie pendant l'appel : l'étape ne passe jamais.`,
        }),
        info: {
            en: "A transition through the record needs the record on, with at least one field (Settings › Record).",
            fr: "Un passage par la fiche exige la fiche allumée, avec au moins un champ (Réglages › Fiche).",
        },
    },
    portes_sans_fiche: {
        titre: { en: "Transitions in the reply, without a record", fr: "Portes écrites sans fiche" },
        detail: () => ({
            en: "The model writes the transition in its reply, and the record is off: the code has nothing to read it with.",
            fr: "Le modèle écrit la porte dans sa réponse, mais la fiche est éteinte : le code n'a rien pour la lire.",
        }),
        info: {
            en: "« In the reply » needs the record on: it is what lets the code take the transition at the end of the reply.",
            fr: "« Il l'écrit dans sa réponse » exige la fiche allumée : c'est elle qui permet au code de prendre la porte en fin de réponse.",
        },
    },
    temps_reel_chaine: {
        titre: { en: "Realtime mode, with functions of the chain", fr: "Temps réel avec des fonctions de la chaîne" },
        detail: (n) => ({
            en: `In realtime mode the voice and the brain are one service: ${n.map((c) => NOMS_DE_LA_CHAINE[c]?.en ?? c).join(", ")} have no effect.`,
            fr: `En temps réel, la voix et le cerveau forment un seul service : ${n.map((c) => NOMS_DE_LA_CHAINE[c]?.fr ?? c).join(", ")} n'ont pas d'effet.`,
        }),
        info: {
            en: "The record, the clerk, the written transitions and the code-led passages only work in the chain mode.",
            fr: "La fiche, le greffier, les portes écrites et les passages par le code ne marchent qu'en chaîne.",
        },
    },
    retour_double: {
        titre: { en: "Two return steps", fr: "Deux étapes de retour" },
        detail: (n) => ({
            en: `${n.map(guillemets).join(" and ")} are both marked as the return step: the code does not know where to bring the call back.`,
            fr: `${n.map(guillemets).join(" et ")} sont toutes deux marquées comme étape de retour : le code ne sait pas où ramener l'appel.`,
        }),
        info: {
            en: "One return marker per main agent. With two, the return of a specialist depends on the reading order.",
            fr: "Un seul marqueur de retour par accueil. Avec deux, le retour d'un spécialiste dépend de l'ordre de lecture.",
        },
    },
    retour_non_redige: {
        titre: { en: "The return step is not written", fr: "L'étape de retour n'est pas rédigée" },
        detail: (n) => ({
            en: `${guillemets(n[0])} is marked as the return step, but its prompt is still to be written: the code ignores it.`,
            fr: `${guillemets(n[0])} est marquée comme étape de retour, mais son prompt est encore à rédiger : le code l'ignore.`,
        }),
        info: {
            en: "Until it is written, a specialist's return falls back on the start step.",
            fr: "Tant qu'elle n'est pas rédigée, le retour d'un spécialiste retombe sur l'étape de départ.",
        },
    },
    annonce_jamais_dite: {
        titre: { en: "Opening announcement never said", fr: "Annonce d'ouverture jamais dite" },
        detail: (n) => ({
            en: `Opening hours are set, but ${guillemets(n[0])} does not carry the announcement: a call outside the hours gets the normal greeting.`,
            fr: `Des horaires sont réglés, mais ${guillemets(n[0])} ne porte pas l'annonce : un appel hors horaires reçoit l'accueil normal.`,
        }),
        info: {
            en: "The announcement is said only when the greeting contains it.",
            fr: "L'annonce n'est dite que si la phrase d'accueil la contient.",
        },
    },
    cumul_de_phrases: {
        titre: { en: "Two sentences in a row", fr: "Deux phrases à la suite" },
        detail: (n) => ({
            en: `The transition sentence of the link ${guillemets(n[1])} and the first reply of ${guillemets(n[0])} follow each other.`,
            fr: `La phrase de transition de la liaison ${guillemets(n[1])} et la première réplique de ${guillemets(n[0])} se suivent.`,
        }),
        info: {
            en: "Keep the one you want the caller to hear.",
            fr: "Garder celle qu'on veut faire entendre.",
        },
    },
    impasse_sans_issue: {
        titre: { en: "A dead end with no way out", fr: "Une impasse sans issue" },
        detail: () => ({
            en: "The dead-end exit is on, but its « Then » leads nowhere: the agent says it takes over and nothing happens.",
            fr: "La sortie d'impasse est allumée, mais son « Ensuite » ne mène nulle part : l'agent dit qu'il reprend la main et rien ne se passe.",
        }),
        info: {
            en: "The exit stays on by default. While its « Then » leads nowhere, publishing is blocked; the fix links it to a step.",
            fr: "La sortie d'impasse reste allumée par défaut. Tant que son « Ensuite » ne mène nulle part, la publication est bloquée ; la correction la relie à une étape.",
        },
    },
    deux_webhooks: {
        titre: { en: "Two webhooks after the call", fr: "Deux webhooks après l'appel" },
        detail: (n) => ({
            en: `${guillemets(n[0])} (Dograh's webhook) and the .mark webhook module both send after the call.`,
            fr: `${guillemets(n[0])} (le webhook de Dograh) et le module webhook .mark envoient tous deux après l'appel.`,
        }),
        info: {
            en: "The same call would be sent twice. Keep one.",
            fr: "Le même appel serait envoyé deux fois. N'en garder qu'un.",
        },
    },
};

const NOMS_DE_LA_CHAINE: Record<string, Texte> = {
    fiche_au_fil_de_leau: { en: "the record", fr: "la fiche" },
    portes_dans_la_reponse: { en: "written transitions", fr: "les portes écrites" },
    greffier: { en: "the clerk", fr: "le greffier" },
    passages: { en: "code-led passages", fr: "les passages par le code" },
};

export const TEXTES_DES_CORRECTIONS: Record<string, (c: CorrectionDeLigne) => Texte> = {
    faire_decider_la_fiche: (c) => ({ en: `Let the record decide on ${guillemets(c.nom ?? undefined)}`, fr: `Faire décider la fiche sur ${guillemets(c.nom ?? undefined)}` }),
    retirer_la_condition: () => ({ en: "Remove the rules", fr: "Retirer les règles" }),
    allumer_la_fiche: () => ({ en: "Turn the record on", fr: "Allumer la fiche" }),
    faire_decider_le_modele: (c) => ({ en: `Let the model decide on ${guillemets(c.nom ?? undefined)}`, fr: `Faire décider le modèle sur ${guillemets(c.nom ?? undefined)}` }),
    rappeler_la_porte: () => ({ en: "Back to « It calls the transition »", fr: "Revenir à « Il appelle la porte »" }),
    eteindre_la_chaine: () => ({ en: "Turn these functions off", fr: "Éteindre ces fonctions" }),
    garder_le_retour: (c) => ({ en: `Keep ${guillemets(c.nom ?? undefined)}`, fr: `Garder ${guillemets(c.nom ?? undefined)}` }),
    retirer_le_retour: () => ({ en: "Remove the return marker", fr: "Retirer le marqueur de retour" }),
    ajouter_l_annonce: () => ({ en: "Add the announcement to the greeting", fr: "Ajouter l'annonce à l'accueil" }),
    retirer_la_phrase_de_transition: () => ({ en: "Remove the transition sentence", fr: "Retirer la phrase de transition" }),
    renvoyer_a_l_accueil: (c) => ({ en: `Send to ${guillemets(c.nom ?? undefined)}`, fr: `Renvoyer vers ${guillemets(c.nom ?? undefined)}` }),
    eteindre_la_sortie_d_impasse: () => ({ en: "Turn the dead-end exit off", fr: "Éteindre la sortie d'impasse" }),
    desactiver_le_webhook_de_dograh: (c) => ({ en: `Turn off ${guillemets(c.nom ?? undefined)}`, fr: `Désactiver ${guillemets(c.nom ?? undefined)}` }),
    retirer_le_module_webhook: () => ({ en: "Remove the .mark webhook module", fr: "Retirer le module webhook .mark" }),
};
