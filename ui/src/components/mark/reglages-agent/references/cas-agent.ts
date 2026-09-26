/**
 * [.mark] One modification per setting of the agent settings page.
 *
 * The contract between the page as it was (14 cards, `ef03ef5e`) and the page
 * in 8 themes (chantier reorganisation-ecran-reglages, decision D1: « on range,
 * on ne change pas la logique »). Step 1 played every case on the OLD cards and
 * froze what each save sent (`charges-utiles-agent.json`). From step 4 on, the
 * same cases are played on the themes, and each payload must be identical.
 *
 * A case names the card the setting came from AND the theme it goes to
 * (convention § 2). The gestures only use what both screens share: element
 * ids, accessible names, visible labels of the reused Dograh components.
 */

export type CarteOrigine =
    | "general"
    | "speech-tuning"
    | "call-record"
    | "opening-hours"
    | "business-address"
    | "models"
    | "variables"
    | "dictionary"
    | "voicemail"
    | "deployment";

export type ThemeAgent =
    | "agent"
    | "briques"
    | "ecoute"
    | "tour"
    | "voix"
    | "rythme"
    | "donnees"
    | "etablissement";

export type Geste =
    | { type: "interrupteur"; id: string }
    | { type: "saisir"; id?: string; libelle?: string; indication?: string; valeur: string }
    | { type: "choisir"; id: string; valeur: string }
    | { type: "etiquette"; id: string; valeur: string }
    | { type: "cliquer"; nom: string }
    | { type: "radio"; nom: string };

export interface CasAgent {
    id: string;
    carte: CarteOrigine;
    theme: ThemeAgent;
    /** The keys of the configuration this case changes (for the inventory). */
    cles: string[];
    gestes: Geste[];
    /**
     * True when the gestures themselves save (a button of the reused component,
     * not the card's or the theme's). Otherwise the card's / theme's button is
     * pressed after the gestures.
     */
    enregistreSeul?: boolean;
}

/** The Save button of each ORIGINAL card, as it read on `ef03ef5e`. */
export const BOUTON_DE_LA_CARTE: Record<CarteOrigine, string | null> = {
    general: "Save General Settings",
    "speech-tuning": "Save Speech Tuning",
    "call-record": "Save Call Record",
    "opening-hours": "Save Opening Hours",
    "business-address": "Save Business Address",
    models: null,
    variables: "Save Variables",
    dictionary: "Save Dictionary",
    voicemail: "Save Voicemail Settings",
    deployment: null,
};

const inter = (id: string): Geste => ({ type: "interrupteur", id });
const saisir = (id: string, valeur: string): Geste => ({ type: "saisir", id, valeur });
const choisir = (id: string, valeur: string): Geste => ({ type: "choisir", id, valeur });

const c = (
    id: string,
    carte: CarteOrigine,
    theme: ThemeAgent,
    cles: string[],
    gestes: Geste[],
    enregistreSeul = false,
): CasAgent => ({ id, carte, theme, cles, gestes, enregistreSeul });

export const CAS_AGENT: CasAgent[] = [
    // ---- General (Dograh) -------------------------------------------------
    c("nom", "general", "agent", ["name"], [saisir("workflow_name", "Accueil modifié")]),
    c("ambiance", "general", "voix", ["ambient_noise_configuration.enabled"], [inter("ambient-noise-enabled")]),
    c("ambiance-volume", "general", "voix", ["ambient_noise_configuration.volume"], [saisir("ambient-volume", "0.7")]),
    c("fin-de-tour", "general", "tour", ["turn_stop_strategy"], [choisir("turn_stop_strategy", "transcription")]),
    c("smart-turn-delai", "general", "tour", ["smart_turn_stop_secs"], [saisir("smart_turn_stop_secs", "3")]),
    c("interruption", "general", "tour", ["turn_start_strategy"], [choisir("turn_start_strategy", "default")]),
    c("interruption-mots", "general", "tour", ["turn_start_min_words"], [saisir("turn_start_min_words", "5")]),
    c("transcription-horodatee", "general", "donnees", ["transcript_configuration.include_end_timestamps"], [inter("transcript-end-timestamps-enabled")]),
    c("compaction", "general", "donnees", ["context_compaction_enabled"], [inter("context-compaction-enabled")]),
    c("cache-voix", "general", "voix", ["tts_cache_enabled"], [inter("tts-cache-enabled")]),
    c("issues-eteintes", "general", "donnees", ["call_dispositions"], [inter("call-disposition-extraction-enabled")]),
    c("duree-max", "general", "rythme", ["max_call_duration"], [saisir("max_call_duration", "900")]),
    c("silence-relance", "general", "rythme", ["max_user_idle_timeout"], [saisir("max_user_idle_timeout", "15")]),
    c("pbx-correspondance", "general", "donnees", ["external_pbx_field_mappings"], [
        { type: "saisir", libelle: "Gathered context field 1", valeur: "urgence" },
    ]),
    c("pbx-prospect", "general", "donnees", ["external_pbx_lead_headers"], [
        { type: "saisir", libelle: "External PBX lead field 1", valeur: " last_name " },
    ]),

    // ---- Speech Tuning (.mark) --------------------------------------------
    c("nombres", "speech-tuning", "ecoute", ["conversion_nombres_transcription"], [inter("conversion_nombres_transcription")]),
    c("variables-reference", "speech-tuning", "ecoute", ["variables_reference"], [saisir("variables_reference", "reference*, facture")]),
    c("communes", "speech-tuning", "ecoute", ["verification_communes"], [inter("verification_communes")]),
    c("variables-commune", "speech-tuning", "ecoute", ["variables_commune"], [saisir("variables_commune", "ville, adresse*")]),
    c("sons-communes", "speech-tuning", "ecoute", ["sons_communes"], [inter("sons_communes")]),
    c("voies", "speech-tuning", "ecoute", ["verification_voies"], [inter("verification_voies")]),
    c("epellation", "speech-tuning", "ecoute", ["lecture_epellation"], [inter("lecture_epellation")]),
    c("lexique", "speech-tuning", "ecoute", ["lexique_metier"], [inter("lexique_metier")]),
    c("sons-lexique", "speech-tuning", "ecoute", ["sons_lexique"], [inter("sons_lexique")]),
    c("bruit-entree", "speech-tuning", "ecoute", ["audio_in_noise_filter"], [choisir("audio_in_noise_filter", "rnnoise")]),
    c("pause", "speech-tuning", "tour", ["user_speech_timeout"], [saisir("user_speech_timeout", "0.8")]),
    c("latence-transcription", "speech-tuning", "tour", ["stt_ttfs_p99_latency"], [saisir("stt_ttfs_p99_latency", "0.4")]),
    c("plafond-transcription", "speech-tuning", "tour", ["user_turn_stop_timeout"], [saisir("user_turn_stop_timeout", "6")]),
    c("attendre-transcription", "speech-tuning", "tour", ["turn_wait_for_transcript"], [inter("turn_wait_for_transcript")]),
    c("transcriptions-partielles", "speech-tuning", "tour", ["turn_start_use_interim"], [inter("turn_start_use_interim")]),
    c("vad-confiance", "speech-tuning", "tour", ["vad_confidence"], [saisir("vad_confidence", "0.6")]),
    c("vad-debut", "speech-tuning", "tour", ["vad_start_secs"], [saisir("vad_start_secs", "0.3")]),
    c("vad-fin", "speech-tuning", "tour", ["vad_stop_secs"], [saisir("vad_stop_secs", "0.3")]),
    c("vad-volume", "speech-tuning", "tour", ["vad_min_volume"], [saisir("vad_min_volume", "0.5")]),
    c("aucun-son", "speech-tuning", "tour", ["audio_idle_timeout"], [saisir("audio_idle_timeout", "2")]),
    c("smart-turn-avant", "speech-tuning", "tour", ["smart_turn_pre_speech_ms"], [saisir("smart_turn_pre_speech_ms", "600")]),
    c("smart-turn-duree", "speech-tuning", "tour", ["smart_turn_max_duration_secs"], [saisir("smart_turn_max_duration_secs", "10")]),
    c("phrase-inachevee", "speech-tuning", "tour", ["filter_incomplete_user_turns"], [inter("filter_incomplete_user_turns")]),
    c("attente-coupee", "speech-tuning", "tour", ["incomplete_short_timeout"], [saisir("incomplete_short_timeout", "6")]),
    c("attente-temps", "speech-tuning", "tour", ["incomplete_long_timeout"], [saisir("incomplete_long_timeout", "12")]),
    c("muet-accueil", "speech-tuning", "tour", ["mute_until_first_bot_complete"], [inter("mute_until_first_bot_complete")]),
    c("muet-outil", "speech-tuning", "tour", ["mute_during_function_call"], [inter("mute_during_function_call")]),
    c("muet-workflow", "speech-tuning", "tour", ["mute_engine_callback"], [inter("mute_engine_callback")]),
    c("muet-premiere", "speech-tuning", "tour", ["mute_first_speech"], [inter("mute_first_speech")]),
    c("muet-toujours", "speech-tuning", "tour", ["mute_always"], [inter("mute_always")]),
    c("accueil-coupable", "speech-tuning", "tour", ["accueil_interruptible"], [inter("accueil_interruptible")]),
    c("accueil-mots", "speech-tuning", "tour", ["accueil_mots_minimum"], [saisir("accueil_mots_minimum", "3")]),
    c("raccrochage-agent", "speech-tuning", "rythme", ["raccrochage_silence_agent_s"], [saisir("raccrochage_silence_agent_s", "40")]),
    c("relance-texte", "speech-tuning", "rythme", ["user_idle_prompt"], [saisir("user_idle_prompt", "Relance modifiée.")]),
    c("relances-nombre", "speech-tuning", "rythme", ["user_idle_max_prompts"], [saisir("user_idle_max_prompts", "3")]),
    c("au-revoir", "speech-tuning", "rythme", ["user_idle_goodbye_prompt"], [saisir("user_idle_goodbye_prompt", "Au revoir modifié.")]),
    c("markdown", "speech-tuning", "voix", ["tts_markdown_filter_enabled"], [inter("tts-markdown-filter")]),
    c("envoi-voix", "speech-tuning", "voix", ["tts_text_aggregation_mode"], [choisir("tts_text_aggregation_mode", "token")]),
    c("silence-apres", "speech-tuning", "voix", ["tts_push_silence_after_stop"], [inter("tts_push_silence_after_stop")]),
    c("silence-duree", "speech-tuning", "voix", ["tts_silence_time_s"], [saisir("tts_silence_time_s", "2")]),
    c("nom-appelant", "speech-tuning", "voix", ["interdire_nom_appelant"], [inter("interdire_nom_appelant")]),
    c("civilite", "speech-tuning", "voix", ["interdire_civilite_appelant"], [inter("interdire_civilite_appelant")]),
    c("prononciation", "speech-tuning", "voix", ["tts_replacements"], [{ type: "etiquette", id: "tts_replacements", valeur: "RGE:R. G. E." }]),

    // ---- Call Record (.mark) -----------------------------------------------
    c("fiche", "call-record", "donnees", ["fiche_au_fil_de_leau"], [inter("fiche_au_fil_de_leau")]),
    c("fiche-champ", "call-record", "donnees", ["fiche_champs"], [
        { type: "cliquer", nom: "Edit fields" },
        saisir("fiche_nom_0", "nom_appelant"),
        { type: "cliquer", nom: "Done" },
    ]),

    // ---- Opening Hours, Business Address (.mark) ---------------------------
    c("horaires", "opening-hours", "etablissement", ["horaires_ouverture"], [
        saisir("horaires_ouverture", "lundi : 9:00-18:00\nmardi : 9:00-18:00\nmercredi : 9:00-18:00\njeudi : 9:00-18:00\nvendredi : 9:00-18:00\nsamedi : fermé\ndimanche : fermé"),
    ]),
    c("adresse-voie", "business-address", "etablissement", ["adresse_etablissement"], [saisir("agent-business-address-voie", "7 rue Neuve")]),
    c("adresse-organisation", "business-address", "etablissement", ["adresse_etablissement"], [
        { type: "cliquer", nom: "Use the organization's address" },
    ], true),

    // ---- Model Overrides (Dograh + .mark) ---------------------------------
    c("configuration-organisation", "models", "briques", ["model_overrides", "model_configuration_v2_override"], [
        { type: "cliquer", nom: "Save Organization Configuration" },
    ], true),
    c("configuration-complete", "models", "briques", ["model_configuration_v2_override"], [
        inter("workflow-model-v2-override"),
        { type: "cliquer", nom: "Save Model Override" },
    ], true),
    c("par-service", "models", "briques", ["model_overrides"], [
        { type: "cliquer", nom: "Save Per-Service Override" },
    ], true),
    c("par-service-retire", "models", "briques", ["model_overrides"], [
        inter("per-service-override-toggle"),
        { type: "cliquer", nom: "Remove the saved per-service override" },
    ], true),

    // ---- Template Variables, Dictionary (Dograh) -----------------------------
    c("variable-ajoutee", "variables", "agent", ["template_context_variables"], [
        saisir("var-key", "ville_siege"),
        saisir("var-value", "Beauvais"),
        { type: "cliquer", nom: "Add Variable" },
    ]),
    c("variable-en-cours", "variables", "agent", ["template_context_variables"], [
        saisir("var-key", "telephone"),
        saisir("var-value", "0344000000"),
    ]),
    c("dictionnaire", "dictionary", "ecoute", ["dictionary"], [
        { type: "saisir", indication: "Enter words separated by comma (e.g. billing department, tretinoin)", valeur: "poêle à granulés, insert, tubage" },
    ]),

    // ---- Voicemail & Screening (Dograh) ------------------------------------
    c("messagerie", "voicemail", "etablissement", ["voicemail_detection.enabled"], [inter("voicemail-enabled")]),
    c("messagerie-message", "voicemail", "etablissement", ["voicemail_detection.voicemail_action", "voicemail_detection.voicemail_message"], [
        { type: "radio", nom: "Leave a message" },
        { type: "saisir", libelle: "Voicemail message", valeur: "Bonjour, rappelez-nous." },
    ]),
    c("messagerie-filtrage", "voicemail", "etablissement", ["voicemail_detection.screening_message"], [
        { type: "saisir", libelle: "Screening message", valeur: "Bonjour, ici le standard." },
    ]),
    c("messagerie-attente", "voicemail", "etablissement", ["voicemail_detection.screening_wait_ms"], [
        { type: "saisir", libelle: "Screening wait (seconds)", valeur: "20" },
    ]),
    c("messagerie-modele", "voicemail", "etablissement", ["voicemail_detection.use_workflow_llm"], [inter("voicemail-use-workflow-llm")]),
    c("messagerie-consignes", "voicemail", "etablissement", ["voicemail_detection.system_prompt"], [
        saisir("voicemail-system-prompt", "Consignes du classificateur modifiées."),
    ]),

    // ---- Add to Website (Dograh dialog, reused) -----------------------------
    c("module-site", "deployment", "agent", ["embed"], [
        { type: "cliquer", nom: "Configure Widget" },
        { type: "cliquer", nom: "Stub: save widget" },
    ], true),
];

/** The theme's title in English: its save button reads « Save <title> » (step 4 on). */
export const TITRE_ANGLAIS_DU_THEME: Record<ThemeAgent, string> = {
    agent: "Agent",
    briques: "Services",
    ecoute: "Listening",
    tour: "Turn taking",
    voix: "Voice",
    rythme: "Call pacing",
    donnees: "Call data",
    etablissement: "Business",
};

/**
 * What the themes add around a case's gestures, and only that: a list now
 * edited in a dialog (convention E4) is opened first and closed with « Done »
 * after. The gestures themselves are the step-1 ones, untouched.
 */
export const AUTOUR_DU_CAS: Record<string, { avant: Geste[]; apres: Geste[] }> = {
    "pbx-correspondance": { avant: [{ type: "cliquer", nom: "Edit field mappings" }], apres: [{ type: "cliquer", nom: "Done" }] },
    "pbx-prospect": { avant: [{ type: "cliquer", nom: "Edit lead fields" }], apres: [{ type: "cliquer", nom: "Done" }] },
    "variable-ajoutee": { avant: [{ type: "cliquer", nom: "Manage variables" }], apres: [{ type: "cliquer", nom: "Done" }] },
    "variable-en-cours": { avant: [{ type: "cliquer", nom: "Manage variables" }], apres: [{ type: "cliquer", nom: "Done" }] },
};
