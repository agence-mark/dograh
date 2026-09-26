/**
 * [.mark] Inventory of the agent configuration: where each key is on screen.
 *
 * Convention `reference/22-convention-ecran.md` § 6. Every key of an agent's
 * configuration is either DISPLAYED by a theme -- and then a reference case
 * proves it is displayed AND saved -- or listed off screen with its reason.
 * `inventaire-agent.test.ts` reads the keys from the schemas themselves (the
 * Python model, our type, the generated client): a key Dograh adds at an
 * upgrade has no entry here, and the test goes red. A setting is never lost
 * in silence.
 */
import type { ThemeAgent } from "./references/cas-agent";

export type EntreeInventaire =
    | {
          theme: ThemeAgent;
          /** Reference cases (`cas-agent.ts`) that change this key. */
          cas: string[];
      }
    | {
          theme: ThemeAgent;
          /** Displayed by a Dograh component reused as it is, with its own tests. */
          via: string;
      }
    | { horsEcran: string };

export const INVENTAIRE_AGENT: Record<string, EntreeInventaire> = {
    // Agent
    text_chat_inactivity_timeout_seconds: {
        theme: "agent",
        via: "Add to Website dialog (EmbedDialog), reused as it is: set for a chat widget",
    },
    // Briques
    model_overrides: { theme: "briques", cas: ["par-service", "par-service-retire", "configuration-organisation"] },
    model_configuration_v2_override: { theme: "briques", cas: ["configuration-complete"] },
    mark_per_service_override: { theme: "briques", cas: ["par-service"] },
    // Écoute
    conversion_nombres_transcription: { theme: "ecoute", cas: ["nombres"] },
    variables_reference: { theme: "ecoute", cas: ["variables-reference"] },
    verification_communes: { theme: "ecoute", cas: ["communes"] },
    variables_commune: { theme: "ecoute", cas: ["variables-commune"] },
    sons_communes: { theme: "ecoute", cas: ["sons-communes"] },
    verification_voies: { theme: "ecoute", cas: ["voies"] },
    lecture_epellation: { theme: "ecoute", cas: ["epellation"] },
    lexique_metier: { theme: "ecoute", cas: ["lexique"] },
    sons_lexique: { theme: "ecoute", cas: ["sons-lexique"] },
    dictionary: { theme: "ecoute", cas: ["dictionnaire"] },
    audio_in_noise_filter: { theme: "ecoute", cas: ["bruit-entree"] },
    // Tour de parole
    turn_stop_strategy: { theme: "tour", cas: ["fin-de-tour"] },
    smart_turn_stop_secs: { theme: "tour", cas: ["smart-turn-delai"] },
    user_speech_timeout: { theme: "tour", cas: ["pause"] },
    stt_ttfs_p99_latency: { theme: "tour", cas: ["latence-transcription"] },
    user_turn_stop_timeout: { theme: "tour", cas: ["plafond-transcription"] },
    turn_wait_for_transcript: { theme: "tour", cas: ["attendre-transcription"] },
    turn_start_strategy: { theme: "tour", cas: ["interruption"] },
    turn_start_min_words: { theme: "tour", cas: ["interruption-mots"] },
    turn_start_use_interim: { theme: "tour", cas: ["transcriptions-partielles"] },
    mute_until_first_bot_complete: { theme: "tour", cas: ["muet-accueil"] },
    mute_during_function_call: { theme: "tour", cas: ["muet-outil"] },
    mute_engine_callback: { theme: "tour", cas: ["muet-workflow"] },
    mute_first_speech: { theme: "tour", cas: ["muet-premiere"] },
    mute_always: { theme: "tour", cas: ["muet-toujours"] },
    accueil_interruptible: { theme: "tour", cas: ["accueil-coupable"] },
    accueil_mots_minimum: { theme: "tour", cas: ["accueil-mots"] },
    vad_confidence: { theme: "tour", cas: ["vad-confiance"] },
    vad_start_secs: { theme: "tour", cas: ["vad-debut"] },
    vad_stop_secs: { theme: "tour", cas: ["vad-fin"] },
    vad_min_volume: { theme: "tour", cas: ["vad-volume"] },
    audio_idle_timeout: { theme: "tour", cas: ["aucun-son"] },
    smart_turn_pre_speech_ms: { theme: "tour", cas: ["smart-turn-avant"] },
    smart_turn_max_duration_secs: { theme: "tour", cas: ["smart-turn-duree"] },
    filter_incomplete_user_turns: { theme: "tour", cas: ["phrase-inachevee"] },
    incomplete_short_timeout: { theme: "tour", cas: ["attente-coupee"] },
    incomplete_long_timeout: { theme: "tour", cas: ["attente-temps"] },
    // Voix
    tts_markdown_filter_enabled: { theme: "voix", cas: ["markdown"] },
    tts_text_aggregation_mode: { theme: "voix", cas: ["envoi-voix"] },
    tts_push_silence_after_stop: { theme: "voix", cas: ["silence-apres"] },
    tts_silence_time_s: { theme: "voix", cas: ["silence-duree"] },
    interdire_nom_appelant: { theme: "voix", cas: ["nom-appelant"] },
    interdire_civilite_appelant: { theme: "voix", cas: ["civilite"] },
    tts_replacements: { theme: "voix", cas: ["prononciation"] },
    ambient_noise_configuration: { theme: "voix", cas: ["ambiance", "ambiance-volume"] },
    tts_cache_enabled: { theme: "voix", cas: ["cache-voix"] },
    // Rythme de l'appel
    max_user_idle_timeout: { theme: "rythme", cas: ["silence-relance"] },
    user_idle_prompt: { theme: "rythme", cas: ["relance-texte"] },
    user_idle_max_prompts: { theme: "rythme", cas: ["relances-nombre"] },
    user_idle_goodbye_prompt: { theme: "rythme", cas: ["au-revoir"] },
    raccrochage_silence_agent_s: { theme: "rythme", cas: ["raccrochage-agent"] },
    max_call_duration: { theme: "rythme", cas: ["duree-max"] },
    // Données de l'appel
    fiche_au_fil_de_leau: { theme: "donnees", cas: ["fiche"] },
    fiche_champs: { theme: "donnees", cas: ["fiche-champ"] },
    call_dispositions: { theme: "donnees", cas: ["issues-eteintes"] },
    transcript_configuration: { theme: "donnees", cas: ["transcription-horodatee"] },
    context_compaction_enabled: { theme: "donnees", cas: ["compaction"] },
    external_pbx_field_mappings: { theme: "donnees", cas: ["pbx-correspondance"] },
    external_pbx_lead_headers: { theme: "donnees", cas: ["pbx-prospect"] },
    // Établissement
    horaires_ouverture: { theme: "etablissement", cas: ["horaires"] },
    adresse_etablissement: { theme: "etablissement", cas: ["adresse-voie", "adresse-organisation"] },
    voicemail_detection: {
        theme: "etablissement",
        cas: [
            "messagerie",
            "messagerie-message",
            "messagerie-filtrage",
            "messagerie-attente",
            "messagerie-modele",
            "messagerie-consignes",
        ],
    },
};
