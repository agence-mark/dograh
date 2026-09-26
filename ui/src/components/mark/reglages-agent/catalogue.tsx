"use client";

/**
 * [.mark] Our settings of an agent, each with its control, in two languages.
 *
 * Chantier reorganisation-ecran-reglages (step 4). These settings used to be
 * drawn by six section components in the order the chantiers added them. The
 * themes now interleave them with Dograh's (the pause next to the end-of-turn
 * strategy), so each setting is declared once here and drawn wherever its
 * theme puts it.
 *
 * ⛔ D1: the CONTROL is the one the sections drew -- same element, same id,
 * same step, same bounds attributes, same way of reading what is typed (a
 * whole number for the prompt count, nothing for an empty optional field…).
 * The English texts are the sections' own; the French ones are the mockup's.
 */
import type { ReactNode } from "react";

import { ChampEtiquettes } from "@/components/mark/ChampEtiquettes";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import { attributDeLongueur, attributsDeBorne, NOMBRE_MAX_ELEMENTS, texteHorsBornes } from "../bornes-reglages";
import { ChampReglage, texteBornes } from "../ecran/ChampReglage";
import { type Texte, useLangue } from "../langue/langue";

type Lecture = "decimal" | "decimalPositif" | "entier" | "entierPositif";

type Definition =
    | { type: "interrupteur"; id?: string; libelle: Texte; aides?: Texte[] }
    | {
          type: "nombre";
          pas: string;
          lecture: Lecture;
          libelle: Texte;
          aides?: Texte[];
          /** Empty is a value: the field sends null (two settings have two defaults). */
          facultatif?: { indication: string };
      }
    | { type: "choix"; libelle: Texte; aides?: Texte[]; options: Array<{ valeur: string; libelle: Texte }> }
    | { type: "texte"; libelle: Texte; aides?: Texte[] }
    | { type: "zone"; libelle: Texte; aides?: Texte[] }
    | { type: "etiquettes"; libelle: Texte; aides?: Texte[]; indication: string };

const d = <T extends Definition>(definition: T) => definition;

/**
 * The rule the server applies to the variable names (`decouper_variables_commune`),
 * in both languages. Same test as `erreurVariablesCommune` (`SectionTranscription.tsx`).
 */
const NOM_VARIABLE = /^(?:[\p{L}\p{N}_-]+|[\p{L}\p{N}_-]{3,}\*)$/u;
export const texteErreurVariables = (texte: string | null | undefined): Texte | null => {
    const fautif = (texte ?? "")
        .split(",")
        .map((nom) => nom.trim())
        .filter((nom) => nom !== "")
        .find((nom) => !NOM_VARIABLE.test(nom));
    return fautif === undefined
        ? null
        : {
              en: `"${fautif}" is not a variable name. Use letters, digits, _ or -, separated by commas; a * only at the end of a name, after at least 3 characters.`,
              fr: `« ${fautif} » n'est pas un nom de variable. Lettres, chiffres, _ ou -, séparés par des virgules ; un * seulement en fin de nom, après au moins 3 caractères.`,
          };
};

export const CATALOGUE = {
    // ---- Écoute ------------------------------------------------------------
    conversion_nombres_transcription: d({
        type: "interrupteur",
        libelle: { en: "Write dictated numbers as digits", fr: "Écrire les nombres dictés en chiffres" },
        aides: [
            {
                en: "Rewrites the numbers the caller dictates as digits before the model reads them, and reads postal codes said both ways (\"soixante sept cent quarante\", \"soixante mille sept cent quarante\"), amounts and invoice or quote references.",
                fr: "Réécrit en chiffres les nombres dictés avant que le modèle ne les lise, et lit les codes postaux dits des deux façons (« soixante sept cent quarante », « soixante mille sept cent quarante »), les montants et les références de facture ou de devis.",
            },
            { en: "The recorded transcript keeps the caller's words.", fr: "La transcription enregistrée garde les mots de l'appelant." },
            { en: "French only. No effect in realtime mode.", fr: "Français seulement. Sans effet en mode temps réel." },
        ],
    }),
    variables_reference: d({
        type: "texte",
        libelle: { en: "Variables that trigger the reference reader", fr: "Variables qui déclenchent le lecteur de références" },
        aides: [
            {
                en: "The steps where an invoice, quote or order number is read as a reference. Same format as the town variables below. Empty: reference*. With the call record switched on, these names are matched against the record's fields instead of the step's variables.",
                fr: "Les étapes où un numéro de facture, de devis ou de commande est lu comme une référence. Même format que les variables de commune ci-dessous. Vide : reference*. Avec la fiche allumée, ces noms sont comparés aux champs de la fiche plutôt qu'aux variables de l'étape.",
            },
        ],
    }),
    verification_communes: d({
        type: "interrupteur",
        libelle: { en: "Recognise the caller's town", fr: "Reconnaître la commune de l'appelant" },
        aides: [
            {
                en: "Matches the town the caller names against the official list of French communes before the model reads it.",
                fr: "Compare la commune nommée à la liste officielle des communes françaises avant que le modèle ne la lise.",
            },
            {
                en: "Acts only at steps that collect a town variable: commune or adresse… by default, or the names set below.",
                fr: "N'agit qu'aux étapes qui recueillent une variable de commune : commune ou adresse… par défaut, ou les noms réglés ci-dessous.",
            },
            { en: "No effect in realtime mode.", fr: "Sans effet en mode temps réel." },
        ],
    }),
    variables_commune: d({
        type: "texte",
        libelle: { en: "Variables that trigger the town check", fr: "Variables qui déclenchent la vérification" },
        aides: [
            {
                en: "Write the name of the variable that collects the town, exactly as it appears in the step of the workflow: open the step, then Variables to Extract and its Variable Name.",
                fr: "Le nom de la variable qui recueille la commune, écrit exactement comme dans l'étape du workflow : ouvrir l'étape, puis Variables to Extract et son Variable Name.",
            },
            { en: "Several names: separate them with commas.", fr: "Plusieurs noms : séparés par des virgules." },
            {
                en: "A * at the end means \"every name that starts with\": adresse* covers adresse, adresse_chantier, adresse_intervention. At least 3 characters before the *.",
                fr: "Un * en fin de nom veut dire « tout nom qui commence par » : adresse* couvre adresse, adresse_chantier, adresse_intervention. Au moins 3 caractères avant le *.",
            },
            {
                en: "Example: ville, lieu_chantier, adresse*. Capitals and spaces do not matter.",
                fr: "Exemple : ville, lieu_chantier, adresse*. Majuscules et espaces sans importance.",
            },
            {
                en: "Leave empty to go back to the default: commune, commune_*, adresse*.",
                fr: "Vide : retour au réglage par défaut, commune, commune_*, adresse*.",
            },
        ],
    }),
    sons_communes: d({
        type: "interrupteur",
        libelle: { en: "Use sounds to recognise towns", fr: "Reconnaître les communes par le son" },
        aides: [
            {
                en: "Compares how the heard words sound with how each town sounds (pronunciation library), in addition to the spelling. Turn off to compare with spelling only.",
                fr: "Compare la façon dont les mots entendus sonnent avec chaque commune (bibliothèque de prononciation), en plus de l'orthographe. Éteint : orthographe seule.",
            },
        ],
    }),
    verification_voies: d({
        type: "interrupteur",
        libelle: { en: "Check street names", fr: "Vérifier le nom de la rue" },
        aides: [
            {
                en: "Matches the street the caller names against the streets of their commune in the national address base, and tells the model the name to use.",
                fr: "Compare la rue nommée aux rues de la commune dans la base nationale des adresses, et donne au modèle le nom à utiliser.",
            },
            {
                en: "A street that is not found is spelled out once, then noted as spelled - the caller is never asked twice.",
                fr: "Une rue introuvable est épelée une fois, puis notée comme épelée : on ne redemande jamais.",
            },
        ],
    }),
    lecture_epellation: d({
        type: "interrupteur",
        libelle: { en: "Read spelled letters", fr: "Lire les lettres épelées" },
        aides: [
            {
                en: "Reads the letters a caller spells out - \"f l a m a n t\", \"F comme François\", \"deux T\", accents, e-mail addresses - and tells the model to copy them exactly.",
                fr: "Lit les lettres qu'un appelant épelle (« f l a m a n t », « F comme François », « deux T », accents, adresses e-mail) et demande au modèle de les recopier exactement.",
            },
            {
                en: "Acts at every step: a name, a street or a brand can be spelled at any moment.",
                fr: "Agit à chaque étape : un nom, une rue ou une marque peut être épelé à tout moment.",
            },
            { en: "No effect in realtime mode.", fr: "Sans effet en mode temps réel." },
        ],
    }),
    lexique_metier: d({
        type: "interrupteur",
        libelle: { en: "Use the organization's trade vocabulary", fr: "Utiliser le lexique métier de l'organisation" },
        aides: [
            {
                en: "Listens for the ticked terms, corrects misheard names before the model reads them, and applies the pronunciations to the voice.",
                fr: "Écoute les termes cochés, corrige les noms mal entendus avant que le modèle ne les lise, et applique les prononciations à la voix.",
            },
            { en: "No effect in realtime mode.", fr: "Sans effet en mode temps réel." },
        ],
    }),
    sons_lexique: d({
        type: "interrupteur",
        libelle: { en: "Use sounds to recognise names", fr: "Reconnaître les noms par le son" },
        aides: [
            {
                en: "Compares how the heard words sound with how each name of the trade vocabulary sounds, in addition to the spelling. A name found by its sound alone is asked for confirmation. Turn off to compare with spelling only.",
                fr: "Compare le son des mots entendus avec chaque nom du lexique, en plus de l'orthographe. Un nom trouvé par le son seul est confirmé auprès de l'appelant. Éteint : orthographe seule.",
            },
        ],
    }),
    audio_in_noise_filter: d({
        type: "choix",
        libelle: { en: "Clean the caller's audio", fr: "Nettoyer le son de l'appelant" },
        aides: [
            {
                en: "RNNoise is free and runs locally. ⚠️ A noise filter can get in the transcription's way as easily as it helps: judge it on a real phone line, not on a browser call.",
                fr: "RNNoise est gratuit et tourne en local. ⚠️ Un filtre de bruit peut gêner la transcription autant qu'il l'aide : à juger sur une vraie ligne téléphonique, pas sur un appel navigateur.",
            },
        ],
        options: [
            { valeur: "none", libelle: { en: "No filter", fr: "Aucun filtre" } },
            { valeur: "rnnoise", libelle: { en: "RNNoise", fr: "RNNoise" } },
        ],
    }),

    // ---- Tour de parole ------------------------------------------------------
    user_speech_timeout: d({
        type: "nombre",
        pas: "0.1",
        lecture: "decimal",
        libelle: { en: "Pause before the agent answers (seconds)", fr: "Pause avant que l'agent réponde (secondes)" },
        aides: [
            {
                en: "How long the caller may pause without losing the floor. Pipecat's own value, 0.6 s, applied until now.",
                fr: "Combien de temps l'appelant peut marquer une pause sans perdre la parole. Valeur de Pipecat, 0,6 s, appliquée jusqu'ici.",
            },
        ],
    }),
    stt_ttfs_p99_latency: d({
        type: "nombre",
        pas: "0.05",
        lecture: "decimal",
        facultatif: { indication: "Provider value (0.35 s for Deepgram)" },
        libelle: { en: "Transcription latency allowed (seconds)", fr: "Latence de transcription admise (secondes)" },
        aides: [
            {
                en: "Leave empty to keep the value Pipecat measured for the provider. ⚠️ That measurement was taken with the voice detector set to 0.2 s: change \"Silence before speech ends\" below without this one, and the end of turn is wrong.",
                fr: "Vide : garde la valeur mesurée par Pipecat pour le fournisseur. ⚠️ Mesurée avec le détecteur de voix à 0,2 s : changer « Silence avant la fin de la parole » sans celle-ci fausse la fin de tour.",
            },
        ],
    }),
    user_turn_stop_timeout: d({
        type: "nombre",
        pas: "0.5",
        lecture: "decimal",
        facultatif: { indication: "5 s (30 s when the transcription drives the turns)" },
        libelle: { en: "Hard ceiling on waiting for a transcript (seconds)", fr: "Plafond d'attente d'une transcription (secondes)" },
        aides: [
            {
                en: "The turn ends anyway past this. ⛔ Leave empty: this setting has TWO defaults, 5 s normally and 30 s when the transcription service drives the turns. Writing 5 s here cuts the second case to 5 s.",
                fr: "Le tour se termine de toute façon au-delà. ⛔ Laisser vide : ce réglage a DEUX valeurs par défaut, 5 s normalement et 30 s quand la transcription pilote les tours. Écrire 5 ici ramène le second cas à 5 s.",
            },
        ],
    }),
    turn_wait_for_transcript: d({
        type: "interrupteur",
        libelle: { en: "Wait for a transcript before answering", fr: "Attendre une transcription avant de répondre" },
        aides: [
            {
                en: "Off, the agent answers on silence alone: faster, but on nothing that was understood.",
                fr: "Éteint, l'agent répond sur le seul silence : plus rapide, mais sans rien avoir compris.",
            },
        ],
    }),
    turn_start_use_interim: d({
        type: "interrupteur",
        libelle: { en: "Let partial transcripts confirm the caller started", fr: "Confirmer la prise de parole avec les transcriptions partielles" },
        aides: [
            {
                en: "Off, only final transcripts count, so interruptions are detected later.",
                fr: "Éteint, seules les transcriptions finales comptent : les interruptions sont détectées plus tard.",
            },
        ],
    }),
    mute_until_first_bot_complete: d({
        type: "interrupteur",
        libelle: { en: "During the opening sentence", fr: "Pendant la phrase d'accueil" },
        aides: [{ en: "Keeps a greeting from being cut in half by a hello. On until now.", fr: "Évite qu'un « allô » coupe l'accueil en deux. Allumé jusqu'ici." }],
    }),
    mute_during_function_call: d({
        type: "interrupteur",
        libelle: { en: "While the agent is running a tool", fr: "Pendant qu'un outil tourne" },
        aides: [{ en: "A transfer or a lookup is not interrupted halfway through. On until now.", fr: "Un transfert ou une recherche n'est pas interrompu à moitié. Allumé jusqu'ici." }],
    }),
    mute_engine_callback: d({
        type: "interrupteur",
        libelle: { en: "Where the workflow says not to interrupt", fr: "Là où le workflow interdit d'interrompre" },
        aides: [{ en: "⚠️ Off, every \"do not interrupt\" set on a node is ignored, silently.", fr: "⚠️ Éteint, chaque « ne pas interrompre » posé sur une étape est ignoré, sans prévenir." }],
    }),
    mute_first_speech: d({
        type: "interrupteur",
        libelle: { en: "During the agent's very first utterance", fr: "Pendant la toute première réplique de l'agent" },
        aides: [{ en: "Narrower than the first one above. Never used until now.", fr: "Plus étroit que le premier ci-dessus. Jamais utilisé jusqu'ici." }],
    }),
    mute_always: d({
        type: "interrupteur",
        libelle: { en: "Never let the caller interrupt at all", fr: "Ne jamais laisser l'appelant couper l'agent" },
        aides: [
            {
                en: "⚠️ On a phone call this is usually the wrong answer: someone made to wait out a whole answer hangs up.",
                fr: "⚠️ Au téléphone, c'est souvent la mauvaise réponse : quelqu'un obligé d'attendre la fin d'une réponse raccroche.",
            },
        ],
    }),
    accueil_interruptible: d({
        type: "interrupteur",
        libelle: { en: "Caller can cut the greeting", fr: "L'appelant peut couper l'accueil" },
        aides: [
            {
                en: "Off until now: the greeting is always heard to the end. On: the \"During the opening sentence\" protection is lifted for this agent, and the greeting stops once the caller has said the number of words below.",
                fr: "Éteint jusqu'ici : l'accueil est toujours entendu jusqu'au bout. Allumé : la protection « Pendant la phrase d'accueil » est levée pour cet agent, et l'accueil s'arrête dès que l'appelant a dit le nombre de mots ci-dessous.",
            },
        ],
    }),
    accueil_mots_minimum: d({
        type: "nombre",
        pas: "1",
        lecture: "entier",
        libelle: { en: "Words needed to cut the greeting", fr: "Mots nécessaires pour couper l'accueil" },
        aides: [
            {
                en: "Only used when the switch above is on. 2 keeps a cough or a lone \"hello\" from cutting it.",
                fr: "Utilisé seulement quand l'interrupteur ci-dessus est allumé. 2 évite qu'une toux ou un « allô » isolé coupe l'accueil.",
            },
        ],
    }),
    vad_confidence: d({
        type: "nombre",
        pas: "0.05",
        lecture: "decimal",
        libelle: { en: "Confidence required (0 to 1)", fr: "Confiance exigée (0 à 1)" },
        aides: [{ en: "Higher misses quiet speech; lower takes background noise for a caller.", fr: "Plus haut, la voix basse est ratée ; plus bas, le bruit de fond passe pour un appelant." }],
    }),
    vad_start_secs: d({
        type: "nombre",
        pas: "0.05",
        lecture: "decimal",
        libelle: { en: "Sound before speech starts (seconds)", fr: "Son avant le début de la parole (secondes)" },
        aides: [{ en: "Range is ours: Pipecat sets no bound on this one.", fr: "Bornes fixées par nous : Pipecat n'en met aucune sur ce réglage." }],
    }),
    vad_stop_secs: d({
        type: "nombre",
        pas: "0.05",
        lecture: "decimal",
        libelle: { en: "Silence before speech ends (seconds)", fr: "Silence avant la fin de la parole (secondes)" },
        aides: [{ en: "⚠️ Tied to the transcription latency above, measured at 0.2 s.", fr: "⚠️ Lié à la latence de transcription ci-dessus, mesurée à 0,2 s." }],
    }),
    vad_min_volume: d({
        type: "nombre",
        pas: "0.05",
        lecture: "decimal",
        libelle: { en: "Minimum volume (0 to 1)", fr: "Volume minimum (0 à 1)" },
        aides: [{ en: "Below this, sound is not treated as speech.", fr: "En dessous, le son n'est pas traité comme de la parole." }],
    }),
    audio_idle_timeout: d({
        type: "nombre",
        pas: "0.5",
        lecture: "decimal",
        libelle: { en: "No audio at all before the turn ends (seconds)", fr: "Aucun son avant la fin du tour (secondes)" },
        aides: [
            {
                en: "For instance if the caller mutes their microphone mid-sentence. 0 disables it.",
                fr: "Par exemple si l'appelant coupe son micro en pleine phrase. 0 le désactive.",
            },
        ],
    }),
    smart_turn_pre_speech_ms: d({
        type: "nombre",
        pas: "50",
        lecture: "decimal",
        libelle: { en: "Audio kept before speech (milliseconds)", fr: "Son gardé avant la parole (millisecondes)" },
        aides: [{ en: "What the Smart Turn model is given ahead of the caller's first word.", fr: "Ce que le modèle Smart Turn reçoit avant le premier mot de l'appelant." }],
    }),
    smart_turn_max_duration_secs: d({
        type: "nombre",
        pas: "1",
        lecture: "decimal",
        libelle: { en: "Longest segment examined (seconds)", fr: "Segment le plus long examiné (secondes)" },
        aides: [{ en: "Beyond this, the model stops looking further back.", fr: "Au-delà, le modèle ne regarde pas plus loin en arrière." }],
    }),
    filter_incomplete_user_turns: d({
        type: "interrupteur",
        libelle: { en: "Let the model judge if the caller finished", fr: "Laisser le modèle juger si l'appelant a fini" },
        aides: [
            {
                en: "⚠️ Off by default: one extra model call per turn, not checked against Mistral, and its follow-up prompts are in English.",
                fr: "⚠️ Éteint par défaut : un appel de modèle en plus par tour, non vérifié avec Mistral, et ses relances sont en anglais.",
            },
        ],
    }),
    incomplete_short_timeout: d({
        type: "nombre",
        pas: "0.5",
        lecture: "decimal",
        libelle: { en: "Wait after a sentence cut short (seconds)", fr: "Attente après une phrase coupée (secondes)" },
        aides: [{ en: "Before the agent prompts the caller again.", fr: "Avant que l'agent relance l'appelant." }],
    }),
    incomplete_long_timeout: d({
        type: "nombre",
        pas: "0.5",
        lecture: "decimal",
        libelle: { en: "Wait after the caller asked for time (seconds)", fr: "Attente après une demande de temps (secondes)" },
        aides: [{ en: "Before the agent prompts the caller again.", fr: "Avant que l'agent relance l'appelant." }],
    }),

    // ---- Voix ------------------------------------------------------------------
    tts_markdown_filter_enabled: d({
        type: "interrupteur",
        id: "tts-markdown-filter",
        libelle: { en: "Strip markdown before speaking", fr: "Retirer la mise en forme avant de parler" },
        aides: [
            {
                en: "Without this, a model that answers with **bold** has the asterisks read out loud. It does not touch parentheses: a stage direction such as \"(one moment, I'm transferring you)\" is still spoken, and stays a matter for the prompt.",
                fr: "Sans cela, un modèle qui répond avec **gras** fait lire les astérisques. Ne touche pas aux parenthèses : une indication comme « (un instant, je vous transfère) » est encore dite, et reste l'affaire du prompt.",
            },
        ],
    }),
    tts_text_aggregation_mode: d({
        type: "choix",
        libelle: { en: "Send text to the voice", fr: "Envoyer le texte à la voix" },
        aides: [
            {
                en: "Word by word answers sooner, but it can degrade the voice depending on the provider: judge it by ear.",
                fr: "Mot par mot répond plus tôt, mais peut dégrader la voix selon le fournisseur : à juger à l'oreille.",
            },
        ],
        options: [
            { valeur: "sentence", libelle: { en: "Sentence by sentence", fr: "Phrase par phrase" } },
            { valeur: "token", libelle: { en: "Word by word", fr: "Mot par mot" } },
        ],
    }),
    tts_push_silence_after_stop: d({
        type: "interrupteur",
        libelle: { en: "Add silence after the agent speaks", fr: "Ajouter un silence après que l'agent parle" },
        aides: [
            {
                en: "Useful where a phone line clips the last syllable. ⚠ Off until now, which is why the duration below changed nothing.",
                fr: "Utile quand une ligne téléphonique mange la dernière syllabe. ⚠️ Éteint jusqu'ici, ce qui explique que la durée ci-dessous ne changeait rien.",
            },
        ],
    }),
    tts_silence_time_s: d({
        type: "nombre",
        pas: "0.1",
        lecture: "decimalPositif",
        libelle: { en: "How long that silence lasts (seconds)", fr: "Durée de ce silence (secondes)" },
    }),
    interdire_nom_appelant: d({
        type: "interrupteur",
        libelle: { en: "Never say the caller's name", fr: "Ne jamais dire le nom de l'appelant" },
    }),
    interdire_civilite_appelant: d({
        type: "interrupteur",
        libelle: { en: "Never say Monsieur, Madame or Mademoiselle", fr: "Ne jamais dire Monsieur, Madame ou Mademoiselle" },
    }),
    tts_replacements: d({
        type: "etiquettes",
        indication: "SAV:S. A. V.",
        libelle: { en: "Pronunciation fixes", fr: "Corrections de prononciation" },
        aides: [
            {
                en: "Written heard:spoken, matched literally. Only the text sent to the voice changes: the conversation history keeps the original.",
                fr: "Écrit entendu:prononcé, appliqué mot pour mot. Seul le texte envoyé à la voix change : l'historique de la conversation garde l'original.",
            },
        ],
    }),

    // ---- Rythme de l'appel -------------------------------------------------------
    user_idle_prompt: d({
        type: "zone",
        libelle: { en: "When the caller goes quiet", fr: "Quand l'appelant se tait" },
    }),
    user_idle_max_prompts: d({
        type: "nombre",
        pas: "1",
        lecture: "entierPositif",
        libelle: { en: "How many times before hanging up", fr: "Nombre de relances avant de raccrocher" },
        aides: [{ en: "0 hangs up on the first silence, with the goodbye below.", fr: "0 raccroche au premier silence, avec l'au revoir ci-dessous." }],
    }),
    user_idle_goodbye_prompt: d({
        type: "zone",
        libelle: { en: "Before hanging up", fr: "Avant de raccrocher" },
        aides: [{ en: "The call is hung up right after this one, whatever the model answers.", fr: "L'appel est coupé juste après, quoi que réponde le modèle." }],
    }),
    raccrochage_silence_agent_s: d({
        type: "nombre",
        pas: "1",
        lecture: "decimal",
        libelle: { en: "Hang up after the agent is silent for (seconds)", fr: "Raccrocher après un silence de l'agent de (secondes)" },
        aides: [
            {
                en: "When the agent owes an answer and nothing is heard at all. Protects the caller from a frozen agent. While a tool runs, the wait is 180 s whatever this says.",
                fr: "Quand l'agent doit une réponse et que rien n'est entendu. Protège l'appelant d'un agent figé. Pendant un outil, l'attente est de 180 s quoi qu'indique ce réglage.",
            },
        ],
    }),
} as const satisfies Record<string, Definition>;

export type CleCatalogue = keyof typeof CATALOGUE;

const lire = (brut: string, lecture: Lecture): number | undefined => {
    const valeur = lecture === "entier" || lecture === "entierPositif" ? parseInt(brut, 10) : parseFloat(brut);
    if (isNaN(valeur)) return undefined;
    if ((lecture === "entierPositif" || lecture === "decimalPositif") && valeur < 0) return undefined;
    return valeur;
};

/** The message a setting of the catalogue shows, or null (bounds, variable names). */
export const erreurDuReglage = (cle: CleCatalogue, valeur: unknown): Texte | null => {
    if (cle === "variables_commune" || cle === "variables_reference") return texteErreurVariables(valeur as string);
    if (typeof valeur === "number" || valeur === null || valeur === undefined) {
        return texteHorsBornes(cle, valeur as number | null | undefined);
    }
    return null;
};

/** The settings of a theme that cannot be saved, with their label and message. */
export const erreursDuCatalogue = (cles: readonly CleCatalogue[], valeurs: Record<string, unknown>) =>
    cles.flatMap((cle) => {
        const message = erreurDuReglage(cle, valeurs[cle]);
        return message ? [{ cle: cle as string, libelle: CATALOGUE[cle].libelle as Texte, message }] : [];
    });

/** One setting of the catalogue, drawn with its control (the sections' own). */
export const Reglage = ({
    cle,
    valeur,
    onChange,
    desactive = false,
    note = null,
    apres,
}: {
    cle: CleCatalogue;
    valeur: unknown;
    onChange: (valeur: unknown) => void;
    desactive?: boolean;
    note?: Texte | null;
    /** Something the section showed right under this control (a warning…). */
    apres?: ReactNode;
}) => {
    const definition: Definition = CATALOGUE[cle];
    const erreur = erreurDuReglage(cle, valeur);
    const commun = {
        cle,
        libelle: definition.libelle,
        aides: definition.aides ?? [],
        erreur,
        note,
    };

    switch (definition.type) {
        case "interrupteur": {
            const id = definition.id ?? cle;
            return (
                <ChampReglage {...commun} idControle={id} disposition="ligne">
                    <Switch id={id} checked={Boolean(valeur)} disabled={desactive} onCheckedChange={(coche) => onChange(coche)} />
                </ChampReglage>
            );
        }
        case "nombre": {
            const facultatif = definition.facultatif;
            return (
                <ChampReglage {...commun} idControle={cle} bornes={texteBornes(cle, Boolean(facultatif))}>
                    <Input
                        id={cle}
                        type="number"
                        step={definition.pas}
                        disabled={desactive}
                        placeholder={facultatif?.indication}
                        {...attributsDeBorne(cle)}
                        aria-invalid={erreur ? true : undefined}
                        value={facultatif ? ((valeur as number | null) ?? "") : (valeur as number)}
                        onChange={(e) => {
                            const brut = e.target.value;
                            if (facultatif && brut === "") {
                                onChange(null);
                                return;
                            }
                            const lu = lire(brut, definition.lecture);
                            if (lu !== undefined) onChange(lu);
                        }}
                    />
                    {apres}
                </ChampReglage>
            );
        }
        case "choix":
            return (
                <ChampReglage {...commun} idControle={cle}>
                    <OptionsTraduites cle={cle} valeur={valeur as string} options={definition.options} onChange={onChange} />
                </ChampReglage>
            );
        case "texte":
            return (
                <ChampReglage {...commun} idControle={cle}>
                    <Input
                        id={cle}
                        {...attributDeLongueur(cle)}
                        aria-invalid={erreur ? true : undefined}
                        value={(valeur as string) ?? ""}
                        onChange={(e) => onChange(e.target.value)}
                    />
                </ChampReglage>
            );
        case "zone":
            return (
                <ChampReglage {...commun} idControle={cle}>
                    <Textarea
                        id={cle}
                        {...attributDeLongueur(cle)}
                        rows={3}
                        value={(valeur as string) ?? ""}
                        onChange={(e) => onChange(e.target.value)}
                    />
                </ChampReglage>
            );
        case "etiquettes":
            return (
                <ChampReglage {...commun} idControle={cle}>
                    <ChampEtiquettes
                        id={cle}
                        valeurs={(valeur as string[]) ?? []}
                        onChange={(valeurs) => onChange(valeurs)}
                        placeholder={definition.indication}
                        maxElements={NOMBRE_MAX_ELEMENTS[cle]}
                    />
                </ChampReglage>
            );
    }
};

const OptionsTraduites = ({
    cle,
    valeur,
    options,
    onChange,
}: {
    cle: string;
    valeur: string;
    options: Array<{ valeur: string; libelle: Texte }>;
    onChange: (valeur: unknown) => void;
}) => {
    const { t } = useLangue();
    return (
        <Select value={valeur} onValueChange={(v) => onChange(v)}>
            <SelectTrigger id={cle}>
                <SelectValue />
            </SelectTrigger>
            <SelectContent>
                {options.map((option) => (
                    <SelectItem key={option.valeur} value={option.valeur}>
                        {t(option.libelle)}
                    </SelectItem>
                ))}
            </SelectContent>
        </Select>
    );
};

/** The settings of the catalogue a configuration carries, read as the sections read them. */
export const extraire = <K extends CleCatalogue>(configurations: WorkflowConfigurations, cles: readonly K[]) =>
    Object.fromEntries(
        cles.map((cle) => [
            cle,
            cle === "tts_replacements"
                ? ((configurations as Record<string, unknown>)[cle] ?? [])
                : (configurations as Record<string, unknown>)[cle],
        ]),
    ) as Record<K, unknown>;
