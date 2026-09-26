/**
 * [.mark] The agent used by the payload references (chantier
 * reorganisation-ecran-reglages, step 1).
 *
 * Every value that has a condition of display is set so the setting it
 * conditions is ON SCREEN: Smart Turn chosen (its timeout and its two fields
 * show), minimum-words interruption (its count shows), the unfinished-sentence
 * judge on (its two waits show), the silence after speech on (its duration
 * shows), number conversion on (the reference variables show), the greeting
 * interruptible (its word count is editable), dispositions set, external PBX
 * lists filled, voicemail handled. A reference can only be taken on a setting
 * that is displayed.
 *
 * Non-default values elsewhere, so that a theme that sent a DEFAULT instead of
 * the stored value would show in the payload.
 */
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

export const NOM_AGENT_DE_REFERENCE = "Accueil de référence";

export const CONFIG_DE_REFERENCE: Partial<WorkflowConfigurations> = {
    ambient_noise_configuration: { enabled: true, volume: 0.4 },
    max_call_duration: 480,
    max_user_idle_timeout: 12,
    turn_stop_strategy: "turn_analyzer",
    smart_turn_stop_secs: 2.5,
    turn_start_strategy: "min_words",
    turn_start_min_words: 4,
    transcript_configuration: { include_end_timestamps: false },
    context_compaction_enabled: false,
    tts_cache_enabled: false,
    call_dispositions: [
        { code: "rappel", description: "Le client demande à être rappelé." },
        { code: "hors_zone", description: "Chantier hors de la zone d'intervention." },
    ],
    external_pbx_field_mappings: [{ context_path: "qualified", destination_field: "address3" }],
    external_pbx_lead_headers: ["first_name"],
    dictionary: "poêle à granulés, insert",
    voicemail_detection: {
        enabled: true,
        use_workflow_llm: true,
        voicemail_action: "hangup",
        screening_message: { text: "Bonjour, ici l'accueil." },
    },
    fiche_au_fil_de_leau: true,
    fiche_champs: [
        {
            nom: "nom",
            type: "string",
            origine: "dicte",
            description: "Nom de famille de l'appelant",
            lecteur: null,
            valeurs: null,
        },
    ],
    horaires_ouverture:
        "lundi : 10:00-18:30\nmardi : 10:00-18:30\nmercredi : 10:00-18:30\njeudi : 10:00-18:30\nvendredi : 10:00-18:30\nsamedi : 10:00-18:00\ndimanche : fermé",
    adresse_etablissement: {
        code_postal: "60000",
        code_insee: "60057",
        commune: "Beauvais",
        voie: "4 rue des Artisans",
    },
    conversion_nombres_transcription: true,
    variables_reference: "reference*",
    user_speech_timeout: 0.7,
    filter_incomplete_user_turns: true,
    tts_push_silence_after_stop: true,
    tts_silence_time_s: 1.5,
    tts_replacements: ["SAV:S. A. V."],
    accueil_interruptible: true,
    accueil_mots_minimum: 2,
    raccrochage_silence_agent_s: 30,
    user_idle_max_prompts: 2,
    model_overrides: { tts: { provider: "elevenlabs", model: "eleven_flash_v2_5" } },
};

export const VARIABLES_DE_REFERENCE: Record<string, string> = {
    nom_entreprise: "Nuances de Feu",
};

/** The communes the address field is offered for the reference postal code. */
export const COMMUNES_DE_REFERENCE = [
    { code_insee: "60057", nom: "Beauvais" },
];
