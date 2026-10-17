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
    generer_schema_parcours: { theme: "agent", cas: ["schema-parcours"] },
    text_chat_inactivity_timeout_seconds: {
        theme: "agent",
        via: "Add to Website dialog (EmbedDialog), reused as it is: set for a chat widget",
    },
    // Briques
    model_overrides: { theme: "briques", cas: ["par-service", "par-service-retire", "configuration-organisation"] },
    model_configuration_v2_override: { theme: "briques", cas: ["configuration-complete"] },
    mark_per_service_override: { theme: "briques", cas: ["par-service"] },
    // Lot 4 d'orchestrateur-trois-cerveaux (D13): « Background work », next to « Own brain ».
    travail_actif: { theme: "briques", cas: ["travail-actif"] },
    travail_llm: { theme: "briques", cas: ["travail-modele"] },
    travail_consigne: { theme: "briques", cas: ["travail-modele"] },
    travail_outils: { theme: "briques", cas: ["travail-outils"] },
    travail_delai_max_s: { theme: "briques", cas: ["travail-delai"] },
    // Écoute
    conversion_nombres_transcription: { theme: "ecoute", cas: ["nombres"] },
    variables_reference: { theme: "ecoute", cas: ["variables-reference"] },
    verification_communes: { theme: "ecoute", cas: ["communes"] },
    variables_commune: { theme: "ecoute", cas: ["variables-commune"] },
    controle_donnees: { theme: "ecoute", cas: ["controle-donnees"] },
    variables_telephone: { theme: "ecoute", cas: ["variables-telephone"] },
    variables_code_postal: { theme: "ecoute", cas: ["variables-code-postal"] },
    variables_courriel: { theme: "ecoute", cas: ["variables-courriel"] },
    variables_date: { theme: "ecoute", cas: ["variables-date"] },
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
    relance_apres_outil: { theme: "tour", cas: ["relance-outil"] },
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
    relecture_des_numeros: { theme: "voix", cas: ["relecture-des-numeros"] },
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
    fiche_mode_de_note: { theme: "donnees", cas: ["mode-de-note"] },
    portes_dans_la_reponse: { theme: "donnees", cas: ["portes-dans-la-reponse"] },
    ordre_de_la_reponse: { theme: "donnees", cas: ["ordre-de-la-reponse"] },
    indices_des_modules: { theme: "donnees", cas: ["indices-des-modules"] },
    etiquettes_des_etapes: { theme: "donnees", cas: ["etiquettes-des-etapes"] },
    // Lot 2 d'orchestrateur-trois-cerveaux (D4): « Known fields near the question ».
    fiche_deja_connu: { theme: "donnees", cas: ["fiche-deja-connu"] },
    transfert_garanti: { theme: "donnees", cas: ["transfert-garanti"] },
    phrase_sans_redemande: { theme: "donnees", cas: ["phrase-sans-redemande"] },
    // Chantier repliques-coupees, lot 6 bis (D16): on screen, no longer « hors écran ».
    trace_requetes_modele: { theme: "agent", cas: ["trace-requetes-modele"] },
    // Chantier schema-parcours-unique (C1, C2): « parcours_lisible » is gone (the flow map box
    // drives it), the retry reasoning moves to the Agent theme.
    reflexion_de_relance: { theme: "agent", cas: ["reflexion-de-relance"] },
    greffier_llm: { theme: "donnees", cas: ["greffier", "greffier-format-garanti"] },
    greffier_consigne: { theme: "donnees", cas: ["greffier-consigne"] },
    fiche_champs: { theme: "donnees", cas: ["fiche-champ"] },
    apres_appel: { theme: "donnees", cas: ["apres-appel"] },
    equipe_connue: { theme: "donnees", cas: ["equipe-connue"] },
    verification_appelant: { theme: "donnees", cas: ["verification-appelant"] },
    panne: { theme: "etablissement", cas: ["panne"] },
    call_dispositions: { theme: "donnees", cas: ["issues-eteintes"] },
    transcript_configuration: { theme: "donnees", cas: ["transcription-horodatee"] },
    context_compaction_enabled: { theme: "donnees", cas: ["compaction"] },
    external_pbx_field_mappings: { theme: "donnees", cas: ["pbx-correspondance"] },
    external_pbx_lead_headers: { theme: "donnees", cas: ["pbx-prospect"] },
    // Établissement
    horaires_ouverture: { theme: "etablissement", cas: ["horaires"] },
    adresse_etablissement: { theme: "etablissement", cas: ["adresse-voie", "adresse-organisation"] },
    // Chantier agents-specialises, lot 11: the fiche the agent serves (menu of the theme).
    etablissement_id: { theme: "etablissement", cas: ["fiche-de-lagent"] },
    agent_principal_id: {
        horsEcran:
            "Written by the group routes (lots 2 and 10), never by a gesture of this page; the theme only READS it to say « Establishment: the call's » on a specialised agent (no menu).",
    },
    // Chantier agents-specialises, lot 12 (A5, A6, A7, A10, A18): the group's settings, carried by the main agent.
    agents_specialises: {
        horsEcran:
            "Written by the group routes (lot 10), never by a gesture of this page; the theme Agent only LISTS the specialised agents (a link to each) under « Specialised agents ».",
    },
    prechauffage_agents: { theme: "agent", cas: ["agents-prechauffage"] },
    passation_sans_resume_jusqua: { theme: "agent", cas: ["agents-sans-resume"] },
    un_seul_renvoi_par_appel: { theme: "agent", cas: ["agents-renvoi-unique"] },
    passations_max_par_appel: { theme: "agent", cas: ["agents-plafond"] },
    // Lot 2 d'orchestrateur-trois-cerveaux (B2): « End-of-call safety net », under « Specialised agents ».
    filet_de_fin: { theme: "agent", cas: ["agents-filet-de-fin"] },
    attente: { theme: "voix", cas: ["attente"] },
    transfert_humain: { theme: "voix", cas: ["transfert-humain"] },
    cerveau_propre: { theme: "briques", cas: ["cerveau-propre"] },
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
