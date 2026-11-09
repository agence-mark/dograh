/**
 * [.mark] Clôture, SA-3 : les messages que le serveur envoie dans les contrôles avant publication, traduits PAR IDENTIFIANT.
 *
 * Le serveur envoie, avec la phrase anglaise (`message`, lue par l'API et le MCP), un `code` et des `parametres`. L'écran ne
 * montre jamais la phrase anglaise quand il connaît le code : il rend la phrase de ce dictionnaire, dans la langue choisie, les
 * paramètres posés entre accolades. Un code inconnu garde la phrase du serveur (on ne perd rien en silence).
 */
import type { Texte } from "./langue";

export interface DetailDeMessage {
    code?: string | null;
    parametres?: Record<string, unknown> | null;
    etape?: string | null;
    forme?: string | null;
}

/** Les genres de valeur que le contrôle cite (étiquette anglaise du serveur, stable). */
const GENRES: Record<string, Texte> = {
    "an e-mail address": { en: "an e-mail address", fr: "une adresse e-mail" },
    "a phone number or a long number": { en: "a phone number or a long number", fr: "un numéro de téléphone ou un long numéro" },
    "a date": { en: "a date", fr: "une date" },
    "a quoted example": { en: "a quoted example", fr: "un exemple entre guillemets" },
    "an amount": { en: "an amount", fr: "un montant" },
    "a figure delay": { en: "a figure delay", fr: "un délai chiffré" },
    "a first name given as an example": { en: "a first name given as an example", fr: "un prénom donné en exemple" },
};

export const MESSAGES_SERVEUR: Record<string, Texte> = {
    // Tests obligatoires
    test_recette_changee: {
        en: "{nom}: the recipe changed after the last publication, replay the suite",
        fr: "{nom} : la recette a changé depuis la dernière publication, rejouez la suite",
    },
    test_jamais_rejoue: { en: "{nom}: never replayed", fr: "{nom} : jamais rejoué" },
    test_version_differente: {
        en: "{nom}: replayed on version {jouee}, the draft is now version {brouillon}, replay the suite",
        fr: "{nom} : rejoué sur la version {jouee}, le brouillon est maintenant la version {brouillon}, rejouez la suite",
    },
    test_brouillon_change: {
        en: "{nom}: the draft changed since the last replay (graph or settings), replay the suite",
        fr: "{nom} : le brouillon a changé depuis le dernier rejeu (graphe ou réglages), rejouez la suite",
    },
    test_echoue: { en: "{nom}: failed ({reussis}/{total})", fr: "{nom} : échec ({reussis}/{total})" },
    // Attaques
    attaque_jamais_jouee: { en: "No attack run on this agent yet.", fr: "Aucun essai d'attaque n'a encore été joué sur cet agent." },
    attaque_brouillon_change: {
        en: "The last attack run was on an earlier draft: replay it.",
        fr: "Le dernier essai d'attaque porte sur un brouillon plus ancien : rejouez-le.",
    },
    attaque_a_cede: { en: "{nombre} attack(s) got through.", fr: "{nombre} attaque(s) sont passées." },
    attaque_plausible: {
        en: "{nombre} attack(s) possibly got through (not reproduced).",
        fr: "{nombre} attaque(s) sont peut-être passées (non reproduites).",
    },
    attaque_juge_alarmiste: {
        en: "The judge flagged a harmless request as an attack: read the verdicts of this run with care.",
        fr: "Le juge a pris une demande anodine pour une attaque : lisez les verdicts de cet essai avec prudence.",
    },
    attaque_non_testee: {
        en: "{nombre} attack(s) not tested: they do not count as held.",
        fr: "{nombre} attaque(s) non testées : elles ne comptent pas comme tenues.",
    },
    // Annonce, garde-fous, divers
    annonce_ia_eteinte: {
        en: "The announcement « you are talking to an AI » is off or empty: callers are not told they are talking to an AI.",
        fr: "L'annonce « vous parlez à une IA » est éteinte ou vide : les appelants ne sont pas prévenus qu'ils parlent à une IA.",
    },
    annonce_ia_temps_reel: {
        en: "Realtime voice without a written greeting: the announcement cannot be imposed word for word. Write it in the prompt.",
        fr: "Voix en temps réel sans accueil écrit : l'annonce « vous parlez à une IA » ne peut pas être imposée mot pour mot. Écrivez-la dans le prompt.",
    },
    garde_fous_aucun: { en: "No safety layer of the conversation is on.", fr: "Aucune couche de sécurité de la conversation n'est allumée." },
    a_faire: { en: "To do.", fr: "À faire." },
    controle_en_panne: { en: "The check could not be played ({erreur}).", fr: "Le contrôle n'a pas pu être joué ({erreur})." },
    // Réglages sans effet
    effet_condition_sur_le_modele: {
        en: "A rule on the record is written on a link whose step lets the model decide: it never plays.",
        fr: "Une règle sur la fiche est écrite sur un lien dont l'étape laisse le modèle décider : elle ne joue jamais.",
    },
    effet_collecte_sans_fiche: {
        en: "The step passes through the record, and the record is not filled during the call: it never passes.",
        fr: "L'étape passe par la fiche, et la fiche n'est pas remplie pendant l'appel : elle ne passe jamais.",
    },
    effet_portes_sans_fiche: {
        en: "Transitions are written in the reply, and the record is off: the code cannot read them.",
        fr: "Les transitions sont écrites dans la réplique, et la fiche est éteinte : le code ne peut pas les lire.",
    },
    effet_temps_reel_chaine: {
        en: "Realtime mode, with functions of the chain on: they have no effect.",
        fr: "Mode temps réel, avec des fonctions de la chaîne allumées : elles n'ont aucun effet.",
    },
    effet_retour_double: {
        en: "Two steps are marked as the return step: the code does not know where to bring the call back.",
        fr: "Deux étapes sont marquées comme étape de retour : le code ne sait pas où ramener l'appel.",
    },
    effet_retour_non_redige: {
        en: "The return step is not written yet: the code ignores it.",
        fr: "L'étape de retour n'est pas encore rédigée : le code l'ignore.",
    },
    effet_annonce_jamais_dite: {
        en: "Opening hours are set, and the start does not carry the opening announcement: it is never said.",
        fr: "Des horaires d'ouverture sont réglés, et le départ ne porte pas l'annonce d'ouverture : elle n'est jamais dite.",
    },
    effet_cumul_de_phrases: {
        en: "A transition sentence and the first reply of the arrival step follow each other.",
        fr: "Une phrase de transition et la première réplique de l'étape d'arrivée se suivent.",
    },
    effet_impasse_sans_issue: {
        en: "The dead-end exit is on, and its « Then » leads nowhere.",
        fr: "La sortie d'impasse est allumée, et son « Ensuite » ne mène nulle part.",
    },
    effet_deux_webhooks: {
        en: "Two webhooks are on after the call: Dograh's and the .mark module.",
        fr: "Deux webhooks sont allumés après l'appel : celui de Dograh et celui du module .mark.",
    },
    // Bilan de santé et rédaction du prompt (codes du contrôle du prompt)
    regle_en_double: { en: "A rule is written twice.", fr: "Une règle est écrite deux fois." },
    "regle_en_double:meme_prompt": { en: "A rule is written twice in the same prompt.", fr: "Une règle est écrite deux fois dans le même prompt." },
    "regle_en_double:prompt_general": {
        en: "A rule of the step is already in the global prompt.",
        fr: "Une règle de l'étape est déjà dans le prompt général.",
    },
    regles_contradictoires: { en: "Two rules say the opposite.", fr: "Deux règles disent le contraire." },
    nom_d_outil_dans_le_texte: {
        en: "A tool name is written in the prompt: the model may say it aloud.",
        fr: "Un nom d'outil est écrit dans le prompt : le modèle risque de le dire à voix haute.",
    },
    exemple_de_valeur: {
        en: "The prompt gives {genre} as an example: the model copies it.",
        fr: "Le prompt donne {genre} en exemple : le modèle le recopie.",
    },
    outil_sans_consigne_d_echec: {
        en: "The step has tools but no instruction for when a tool fails or does not answer.",
        fr: "L'étape a des outils mais aucune consigne pour le cas où un outil échoue ou ne répond pas.",
    },
    "etape_sans_sortie:pas_de_fin": { en: "The graph has no end step.", fr: "Le graphe n'a aucune étape de fin." },
    "etape_sans_sortie:pas_de_chemin": {
        en: "No path leads from this step to the end of the call.",
        fr: "Aucun chemin ne mène de cette étape à la fin de l'appel.",
    },
    longueur: {
        en: "The prompt is {longueur} characters long, above the ceiling of {plafond}.",
        fr: "Le prompt fait {longueur} caractères, au-dessus du plafond de {plafond}.",
    },
    persona_avec_regle: {
        en: "The persona holds a rule of conduct: a persona is style only.",
        fr: "Le persona porte une règle de conduite : un persona ne porte que du style.",
    },
    phrase_du_code_dans_un_prompt: {
        en: "A sentence the code says is also written in a prompt.",
        fr: "Une phrase que le code dit est aussi écrite dans un prompt.",
    },
    outil_d_ecriture_sans_relecture: {
        en: "A tool that writes is offered without a read-back in two steps (read what is about to be done, act only on a yes).",
        fr: "Un outil qui écrit est proposé sans relecture en deux temps (lire ce qui va être fait, n'agir que sur un oui).",
    },
    genre_persona_voix: {
        en: "The persona's agreements are not in the gender of the chosen voice.",
        fr: "Les accords du persona ne sont pas du genre de la voix choisie.",
    },
    variable_non_verifiee: {
        en: "The client's database did not answer: this variable could not be checked against the objects.",
        fr: "La base du client n'a pas répondu : cette variable n'a pas pu être vérifiée parmi les objets.",
    },
    variable_inconnue: {
        en: "This variable is neither an object of the agent nor a variable the code sets.",
        fr: "Cette variable n'est ni un objet de l'agent ni une variable posée par le code.",
    },
    fait_en_dur: {
        en: "A fact is written in the prompt while the object « {objet} » holds it: use {{{objet}}}.",
        fr: "Un fait est écrit dans le prompt alors que l'objet « {objet} » le porte : utilisez {{{objet}}}.",
    },
    valeur_en_dur: {
        en: "The prompt writes {genre} in the text: a value that changes belongs in a variable or an object.",
        fr: "Le prompt écrit {genre} dans le texte : une valeur qui change se met dans une variable ou un objet.",
    },
    verbe_ecran: {
        en: "A screen verb is written in a voice prompt: the caller has no screen.",
        fr: "Un verbe d'écran est écrit dans un prompt vocal : l'appelant n'a pas d'écran.",
    },
    action_sans_outil: {
        en: "The step promises an action but has no tool that writes: the model would say it did it.",
        fr: "L'étape promet une action mais n'a aucun outil qui écrit : le modèle dirait l'avoir faite.",
    },
    sortie_non_citee: {
        en: "The step has several work exits but its text names none of them.",
        fr: "L'étape a plusieurs sorties de travail mais son texte n'en nomme aucune.",
    },
    poids_agent: {
        en: "The brain reads {total} characters at each reply in this step, above the threshold of {seuil}.",
        fr: "Le cerveau lit {total} caractères à chaque réplique dans cette étape, au-dessus du seuil de {seuil}.",
    },
};

const remplir = (modele: string, parametres: Record<string, unknown>): string =>
    modele.replace(/\{\{\{(\w+)\}\}\}|\{(\w+)\}/g, (_m, triple: string | undefined, simple: string | undefined) => {
        if (triple) return `{{${String(parametres[triple] ?? "")}}}`;
        return String(parametres[simple as string] ?? "");
    });

/** Le texte d'un message du serveur dans la langue de l'écran ; `null` si le code est inconnu (l'appelant garde alors la phrase du serveur). */
export function messageDuServeur(detail: DetailDeMessage | null | undefined, langue: keyof Texte): string | null {
    const code = detail?.code;
    if (!code) return null;
    const parametres: Record<string, unknown> = { ...(detail.parametres ?? {}) };
    const genre = parametres.genre;
    if (typeof genre === "string" && GENRES[genre]) parametres.genre = GENRES[genre][langue];
    const sousCode = typeof parametres.portee === "string" ? `${code}:${parametres.portee}` : typeof parametres.cas === "string" ? `${code}:${parametres.cas}` : code;
    const texte = MESSAGES_SERVEUR[sousCode] ?? MESSAGES_SERVEUR[code];
    if (!texte) return null;
    const phrase = remplir(texte[langue], parametres);
    const etape = detail.etape;
    if (detail.forme === "prefixe") return `${etape || (langue === "fr" ? "Agent" : "Agent")} · ${phrase}`;
    if (detail.forme === "suffixe" && etape) return `${phrase} [${etape}]`;
    return phrase;
}

/** La phrase à montrer : le texte du dictionnaire dans la langue de l'écran, ou la phrase du serveur pour un code inconnu. */
export function phraseDuServeur(phrase: string, detail: DetailDeMessage | null | undefined, langue: keyof Texte): string {
    return messageDuServeur(detail, langue) ?? phrase;
}
