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
    // fiabilite-orchestration, lot 4 (F20, F26): the guard and the fallback brains.
    delai_garde_modele_s: { theme: "briques", cas: ["garde-delai"] },
    cerveau_de_repli: { theme: "briques", cas: ["garde-repli"] },
    travail_llm_repli: { theme: "briques", cas: ["travail-repli"] },
    travail_consigne: { theme: "briques", cas: ["travail-modele"] },
    travail_outils: { theme: "briques", cas: ["travail-outils"] },
    travail_delai_max_s: { theme: "briques", cas: ["travail-delai"] },
    // Modules (cloture-code, F8, M4): moved from « Écoute » and « Données de l'appel », one sub-menu each.
    conversion_nombres_transcription: { theme: "modules", cas: ["nombres"] },
    variables_reference: { theme: "modules", cas: ["variables-reference"] },
    verification_communes: { theme: "modules", cas: ["communes"] },
    variables_commune: { theme: "modules", cas: ["variables-commune"] },
    controle_donnees: { theme: "modules", cas: ["controle-donnees"] },
    variables_telephone: { theme: "modules", cas: ["variables-telephone"] },
    variables_code_postal: { theme: "modules", cas: ["variables-code-postal"] },
    variables_courriel: { theme: "modules", cas: ["variables-courriel"] },
    variables_date: { theme: "modules", cas: ["variables-date"] },
    sons_communes: { theme: "modules", cas: ["sons-communes"] },
    verification_voies: { theme: "modules", cas: ["voies"] },
    lecture_epellation: { theme: "modules", cas: ["epellation"] },
    lexique_metier: { theme: "modules", cas: ["lexique"] },
    sons_lexique: { theme: "modules", cas: ["sons-lexique"] },
    equipe_connue: { theme: "modules", cas: ["equipe-connue"] },
    verification_appelant: { theme: "modules", cas: ["verification-appelant"] },
    // Écoute
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
    relance_tour_vide: { theme: "tour", cas: ["tour-vide"] },
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
    // Chantier voix-soniox, lot 5 bis (D11) then lot 7: a card that opens a centred modal (`BalisesPermises.tsx`).
    tts_balises_permises: { theme: "voix", cas: ["balises-permises"] },
    ambient_noise_configuration: { theme: "voix", cas: ["ambiance", "ambiance-volume"] },
    tts_cache_enabled: { theme: "voix", cas: ["cache-voix"] },
    // Rythme de l'appel
    max_user_idle_timeout: { theme: "rythme", cas: ["silence-relance"] },
    user_idle_prompt: { theme: "rythme", cas: ["relance-texte"] },
    user_idle_max_prompts: { theme: "rythme", cas: ["relances-nombre"] },
    user_idle_goodbye_prompt: { theme: "rythme", cas: ["au-revoir"] },
    raccrochage_silence_agent_s: { theme: "rythme", cas: ["raccrochage-agent"] },
    laisser_la_parole: { theme: "rythme", cas: ["laisser-la-parole"] },
    max_call_duration: { theme: "rythme", cas: ["duree-max"] },
    // Données de l'appel
    fiche_au_fil_de_leau: { theme: "donnees", cas: ["fiche"] },
    fiche_mode_de_note: { theme: "donnees", cas: ["mode-de-note"] },
    portes_dans_la_reponse: { theme: "donnees", cas: ["portes-dans-la-reponse"] },
    ordre_de_la_reponse: { theme: "donnees", cas: ["ordre-de-la-reponse"] },
    indices_des_modules: { theme: "donnees", cas: ["indices-des-modules", "indices-des-modules-greffier"] },
    // fiabilite-orchestration, lot 2 (F19): one box writes both keys (« known and expected »).
    etiquettes_des_etapes: { theme: "donnees", cas: ["fiche-deja-connu"] },
    fiche_deja_connu: { theme: "donnees", cas: ["fiche-deja-connu"] },
    fiche_dans_le_systeme: { theme: "donnees", cas: ["fiche-dans-le-systeme"] },
    fiche_forme_courte: { theme: "donnees", cas: ["fiche-forme-courte"] },
    reconnaitre_un_outil_ecrit: { theme: "donnees", cas: ["outil-ecrit-en-texte"] },
    transfert_garanti: { theme: "donnees", cas: ["transfert-garanti"] },
    // Lot 11 de correctifs-apres-banc-commun (F-3): the words that say « done », read by the steps' « Truth of actions ».
    verite_formulations_d_action: { theme: "donnees", cas: ["formulations-d-action"] },
    phrase_sans_redemande: { theme: "donnees", cas: ["phrase-sans-redemande"] },
    // Chantier repliques-coupees, lot 6 bis (D16): on screen, no longer « hors écran ».
    trace_requetes_modele: { theme: "agent", cas: ["trace-requetes-modele"] },
    // Chantier schema-parcours-unique (C1, C2): « parcours_lisible » is gone (the flow map box
    // drives it), the retry reasoning moves to the Agent theme.
    reflexion_de_relance: { theme: "agent", cas: ["reflexion-de-relance"] },
    greffier_llm: { theme: "donnees", cas: ["greffier", "greffier-format-garanti"] },
    greffier_consigne: { theme: "donnees", cas: ["greffier-consigne"] },
    // passages-fiables, lot B: the arbiter's brain, next to the clerk's.
    arbitre_llm: { theme: "donnees", cas: ["arbitre"] },
    // passages-fiables, lots F and G: « Improving the agent » in Call data.
    signaler_un_probleme: { theme: "donnees", cas: ["signaler-un-probleme"] },
    alertes_par_mail: { theme: "donnees", cas: ["alertes-par-mail"] },
    fiche_champs: { theme: "donnees", cas: ["fiche-champ"] },
    apres_appel: { theme: "donnees", cas: ["apres-appel"] },
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
    // fiabilite-orchestration, lot 4 bis (F15, F17, F23): the theme Phrases.
    phrases_regles: { theme: "phrases", cas: ["phrases-groupe", "phrases-agent"] },
    // Correctifs-apres-banc-v4, lot 4 then 5: the one common setting of the theme, on screen since the lot 5.
    phrases_repos_s: { theme: "phrases", cas: ["phrases-pause"] },
    prechauffage_agents: { theme: "agent", cas: ["agents-prechauffage"] },
    passation_sans_resume_jusqua: { theme: "agent", cas: ["agents-sans-resume"] },
    un_seul_renvoi_par_appel: { theme: "agent", cas: ["agents-renvoi-unique"] },
    passations_max_par_appel: { theme: "agent", cas: ["agents-plafond"] },
    // Lot 2 d'orchestrateur-trois-cerveaux (B2): « End-of-call safety net », under « Specialised agents ».
    filet_de_fin: { theme: "agent", cas: ["agents-filet-de-fin"] },
    attente: { theme: "voix", cas: ["attente"] },
    transfert_humain: {
        horsEcran:
            "Its only setting, the sentence before a call transfer, moved to the theme Phrases (fiabilite-orchestration, lot 4 bis, F17): shown there as a group rule and removed from this key at the theme's first save; still read by the call until then.",
    },
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
