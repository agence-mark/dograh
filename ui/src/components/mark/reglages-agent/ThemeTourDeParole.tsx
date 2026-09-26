"use client";

/**
 * [.mark] Theme « Tour de parole »: when the agent decides the caller has
 * finished, and when the caller can cut it off (convention § 2).
 *
 * Gathers what was split over two cards: the end-of-turn and interruption
 * strategies of Dograh's « General » (rebuilt here, option B of decision D6:
 * same keys, same controls, same texts, Dograh's file untouched) and the turn
 * taking, protected moments and greeting of our « Speech Tuning ».
 *
 * 🔑 The Smart Turn fields now follow the strategy chosen IN THIS THEME. They
 * used to follow the SAVED strategy, only because the strategy lived in
 * another card; the pipeline reads them only with Smart Turn on (E8).
 *
 * ⛔ Hidden for an agent whose transcription drives the turns (Deepgram Flux,
 * Cartesia ink-2) or runs a realtime model: the SAME rule as the pipeline,
 * `transcriptionPiloteLesTours`, never a list of its own (E8).
 */
import { Repeat } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useOrgConfig } from "@/context/OrgConfigContext";
import {
    DEFAULT_TURN_START_MIN_WORDS,
    TURN_START_STRATEGY_OPTIONS,
    type TurnStartStrategy,
    type TurnStopStrategy,
} from "@/types/workflow-configurations";

import { bornesDe, ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { transcriptionPiloteLesTours } from "../transcriptionPiloteLesTours";
import { type CleCatalogue, erreursDuCatalogue, extraire, Reglage } from "./catalogue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, nommerErreurs, type ProprietesThemeAgent, useBrouillon, useEtatTheme, useRevelation } from "./theme-commun";

export const ID_THEME_TOUR = "tour";
export const TITRE_TOUR = { en: "Turn taking", fr: "Tour de parole" };

export const CLES_TOUR_MARK = [
    "user_speech_timeout",
    "stt_ttfs_p99_latency",
    "user_turn_stop_timeout",
    "turn_wait_for_transcript",
    "turn_start_use_interim",
    "mute_until_first_bot_complete",
    "mute_during_function_call",
    "mute_engine_callback",
    "mute_first_speech",
    "mute_always",
    "accueil_interruptible",
    "accueil_mots_minimum",
    "vad_confidence",
    "vad_start_secs",
    "vad_stop_secs",
    "vad_min_volume",
    "audio_idle_timeout",
    "smart_turn_pre_speech_ms",
    "smart_turn_max_duration_secs",
    "filter_incomplete_user_turns",
    "incomplete_short_timeout",
    "incomplete_long_timeout",
] as const satisfies readonly CleCatalogue[];

const CLES_MUETTES = [
    "mute_until_first_bot_complete",
    "mute_during_function_call",
    "mute_engine_callback",
    "mute_first_speech",
    "mute_always",
] as const;

/** French for Dograh's two interruption strategies; an unknown one keeps its English. */
const STRATEGIES_INTERRUPTION: Record<string, { libelle: string; description: string }> = {
    default: {
        libelle: "Par défaut",
        description: "Défaut de la plateforme : signaux de tour de la transcription quand ils existent, sinon détection de voix locale.",
    },
    min_words: {
        libelle: "Nombre minimum de mots",
        description: "Attend un nombre minimum de mots transcrits avant de couper l'agent.",
    },
};

const extraireTout = (resolue: ProprietesThemeAgent["resolue"]) => ({
    turn_stop_strategy: resolue.turn_stop_strategy as TurnStopStrategy,
    smart_turn_stop_secs: resolue.smart_turn_stop_secs,
    turn_start_strategy: resolue.turn_start_strategy as TurnStartStrategy,
    turn_start_min_words: resolue.turn_start_min_words,
    ...extraire(resolue, CLES_TOUR_MARK),
});

export const ThemeTourDeParole = ({ resolue, workflowName, onSave, ouvert, onBasculer, ouvrir }: ProprietesThemeAgent) => {
    const { t, langue } = useLangue();
    const { userConfig } = useOrgConfig();
    const { enregistre, brouillon, setBrouillon, resynchroniser } = useBrouillon(resolue, extraireTout);
    const { afficher, visible } = useRevelation(ouvrir);

    const maj = (cle: keyof typeof brouillon) => (valeur: unknown) => setBrouillon((avant) => ({ ...avant, [cle]: valeur }));

    // Read from the SAME resolution the server uses: a section hidden for an
    // agent that does use these settings is as wrong as one shown for an agent
    // that does not.
    const tourPiloteAilleurs = transcriptionPiloteLesTours({ organisation: userConfig, agent: resolue });
    const smartTurn = brouillon.turn_stop_strategy === "turn_analyzer";
    const modifie = differe(brouillon, enregistre);

    const erreurs = erreursDuCatalogue(CLES_TOUR_MARK, brouillon);

    useEtatTheme(ID_THEME_TOUR, modifie, erreurs.length > 0);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_TOUR,
        resolue,
        workflowName,
        onSave,
        parties: [{ nom: { en: "Turn taking settings", fr: "Réglages du tour de parole" }, modifie, config: () => brouillon, apres: resynchroniser }],
    });

    const r = (cle: (typeof CLES_TOUR_MARK)[number], condition = true, desactive = false) => {
        const { affiche, note } = visible(cle, condition);
        return affiche ? <Reglage key={cle} cle={cle} valeur={brouillon[cle]} onChange={maj(cle)} note={note} desactive={desactive} /> : null;
    };
    const groupeVisible = (cles: readonly (typeof CLES_TOUR_MARK)[number][], condition: boolean) =>
        cles.some((cle) => visible(cle, condition).affiche);

    const strategieInterruption = TURN_START_STRATEGY_OPTIONS.find((o) => o.value === brouillon.turn_start_strategy);
    const libelleStrategie = (valeur: string, anglais: string) =>
        langue === "fr" ? (STRATEGIES_INTERRUPTION[valeur]?.libelle ?? anglais) : anglais;

    const detecteur = ["vad_confidence", "vad_start_secs", "vad_stop_secs", "vad_min_volume", "audio_idle_timeout"] as const;
    const smart = ["smart_turn_pre_speech_ms", "smart_turn_max_duration_secs"] as const;
    const inachevee = ["filter_incomplete_user_turns", "incomplete_short_timeout", "incomplete_long_timeout"] as const;

    return (
        <Theme
            id={ID_THEME_TOUR}
            icone={Repeat}
            titre={TITRE_TOUR}
            description={{
                en: "When the agent decides the caller has finished, and when the caller can cut it off.",
                fr: "Quand l'agent décide que l'appelant a fini, et quand l'appelant peut le couper.",
            }}
            resume={[
                brouillon.turn_stop_strategy === "transcription"
                    ? t({ en: "End of turn: transcription", fr: "Fin de tour : transcription" })
                    : t({ en: "End of turn: Smart Turn", fr: "Fin de tour : Smart Turn" }),
                tourPiloteAilleurs
                    ? t({ en: "Turns driven by the transcription", fr: "Tours pilotés par la transcription" })
                    : `${t({ en: "Pause", fr: "Pause" })} ${brouillon.user_speech_timeout} s`,
                brouillon.accueil_interruptible
                    ? t({ en: "Greeting interruptible", fr: "Accueil coupable" })
                    : t({ en: "Greeting protected", fr: "Accueil protégé" }),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={nommerErreurs(erreurs, t, afficher)}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="tour-fin" titre={{ en: "End of turn", fr: "Fin de tour" }}>
                <ChampReglage
                    cle="turn_stop_strategy"
                    idControle="turn_stop_strategy"
                    libelle={{ en: "Detection Strategy", fr: "Stratégie de détection" }}
                    aides={[
                        brouillon.turn_stop_strategy === "transcription"
                            ? {
                                  en: "Best for short responses (1-2 word statements). Ends turn when transcription indicates completion.",
                                  fr: "Idéal pour les réponses courtes (1 ou 2 mots). Termine le tour quand la transcription indique la fin.",
                              }
                            : {
                                  en: "Best for longer responses with natural pauses. Uses ML model to detect end of turn.",
                                  fr: "Idéal pour les réponses longues avec des pauses naturelles. Un modèle détecte la fin du tour.",
                              },
                    ]}
                >
                    <Select value={brouillon.turn_stop_strategy} onValueChange={(v: TurnStopStrategy) => maj("turn_stop_strategy")(v)}>
                        <SelectTrigger id="turn_stop_strategy">
                            <SelectValue placeholder={t({ en: "Select strategy", fr: "Choisir une stratégie" })} />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="transcription">{t({ en: "Transcription-based", fr: "Selon la transcription" })}</SelectItem>
                            <SelectItem value="turn_analyzer">{t({ en: "Smart Turn Analyzer", fr: "Analyseur Smart Turn" })}</SelectItem>
                        </SelectContent>
                    </Select>
                </ChampReglage>
                {smartTurn && (
                    <ChampReglage
                        cle="smart_turn_stop_secs"
                        idControle="smart_turn_stop_secs"
                        libelle={{ en: "Incomplete Turn Timeout (seconds)", fr: "Délai d'un tour incomplet (secondes)" }}
                        aides={[
                            {
                                en: "Max silence duration before ending an incomplete turn. Default: 2 seconds",
                                fr: "Silence maximum avant de terminer un tour incomplet. Défaut : 2 secondes.",
                            },
                        ]}
                        bornes={bornesDe(0.5, 10)}
                    >
                        <Input
                            id="smart_turn_stop_secs"
                            type="number"
                            step="0.5"
                            min="0.5"
                            max="10"
                            value={brouillon.smart_turn_stop_secs}
                            onChange={(e) => {
                                const value = parseFloat(e.target.value);
                                if (!isNaN(value) && value >= 0.5) maj("smart_turn_stop_secs")(value);
                            }}
                        />
                    </ChampReglage>
                )}
                {tourPiloteAilleurs && (
                    <p className="rounded-md border bg-muted/30 p-3 text-xs text-muted-foreground" data-note="tour-pilote">
                        {t({
                            en: "Pause settings hidden for this agent: its transcription service decides the turn boundaries itself (Deepgram Flux, Cartesia ink-2), or it runs a realtime model that does. The pipeline follows those signals and builds none of these settings, so showing them here would show values that play no part in the call.",
                            fr: "Réglages de pause masqués pour cet agent : sa transcription décide elle-même des fins de tour (Deepgram Flux, Cartesia ink-2), ou il tourne sur un modèle temps réel. Le pipeline suit ces signaux et ne construit aucun de ces réglages : les afficher montrerait des valeurs qui ne jouent aucun rôle dans l'appel.",
                        })}
                    </p>
                )}
                {r("user_speech_timeout", !tourPiloteAilleurs)}
                {r("stt_ttfs_p99_latency", !tourPiloteAilleurs)}
                {r("user_turn_stop_timeout", !tourPiloteAilleurs)}
                {r("turn_wait_for_transcript", !tourPiloteAilleurs)}
            </Intertitre>

            <Intertitre id="tour-interruption" titre={{ en: "Interruption", fr: "Interruption" }}>
                <ChampReglage
                    cle="turn_start_strategy"
                    idControle="turn_start_strategy"
                    libelle={{ en: "Interruption Strategy", fr: "Stratégie d'interruption" }}
                    aides={
                        strategieInterruption
                            ? [
                                  {
                                      en: strategieInterruption.description,
                                      fr: STRATEGIES_INTERRUPTION[strategieInterruption.value]?.description ?? strategieInterruption.description,
                                  },
                              ]
                            : []
                    }
                >
                    <Select value={brouillon.turn_start_strategy} onValueChange={(v: TurnStartStrategy) => maj("turn_start_strategy")(v)}>
                        <SelectTrigger id="turn_start_strategy">
                            <SelectValue placeholder={t({ en: "Select strategy", fr: "Choisir une stratégie" })} />
                        </SelectTrigger>
                        <SelectContent>
                            {TURN_START_STRATEGY_OPTIONS.map((option) => (
                                <SelectItem key={option.value} value={option.value}>
                                    {libelleStrategie(option.value, option.label)}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </ChampReglage>
                {brouillon.turn_start_strategy === "min_words" && (
                    <ChampReglage
                        cle="turn_start_min_words"
                        idControle="turn_start_min_words"
                        libelle={{ en: "Minimum Words Before Interruption", fr: "Mots minimum avant interruption" }}
                        aides={[
                            {
                                en: `Number of transcribed words needed to interrupt while the bot is speaking. Default: ${DEFAULT_TURN_START_MIN_WORDS}`,
                                fr: `Nombre de mots transcrits nécessaires pour couper l'agent pendant qu'il parle. Défaut : ${DEFAULT_TURN_START_MIN_WORDS}.`,
                            },
                        ]}
                        bornes={bornesDe(1, 10)}
                    >
                        <Input
                            id="turn_start_min_words"
                            type="number"
                            step="1"
                            min="1"
                            max="10"
                            value={brouillon.turn_start_min_words}
                            onChange={(e) => {
                                const value = parseInt(e.target.value);
                                if (!isNaN(value) && value >= 1) maj("turn_start_min_words")(value);
                            }}
                        />
                    </ChampReglage>
                )}
                {r("turn_start_use_interim", !tourPiloteAilleurs)}
            </Intertitre>

            <Intertitre
                id="tour-proteges"
                titre={{ en: "Moments when the agent can't be interrupted", fr: "Moments où l'agent ne peut pas être coupé" }}
                description={{
                    en: "When the caller's microphone is ignored, so the agent can finish what it is doing.",
                    fr: "Quand le micro de l'appelant est ignoré, pour que l'agent finisse ce qu'il fait.",
                }}
            >
                {CLES_MUETTES.map((cle) => r(cle))}
                {r("accueil_interruptible")}
                {r("accueil_mots_minimum", true, !brouillon.accueil_interruptible)}
            </Intertitre>

            {groupeVisible(detecteur, !tourPiloteAilleurs) && (
                <Intertitre id="tour-detecteur" titre={{ en: "Voice detector", fr: "Détecteur de voix" }}>
                    {detecteur.map((cle) => r(cle, !tourPiloteAilleurs))}
                </Intertitre>
            )}

            {groupeVisible(smart, !tourPiloteAilleurs && smartTurn) && (
                <Intertitre id="tour-smart-turn" titre={{ en: "Smart Turn", fr: "Smart Turn" }}>
                    {smart.map((cle) => r(cle, !tourPiloteAilleurs && smartTurn))}
                </Intertitre>
            )}

            {groupeVisible(inachevee, !tourPiloteAilleurs) && (
                <Intertitre id="tour-inachevee" titre={{ en: "Unfinished sentence", fr: "Phrase inachevée" }}>
                    {r("filter_incomplete_user_turns", !tourPiloteAilleurs)}
                    {r("incomplete_short_timeout", !tourPiloteAilleurs && Boolean(brouillon.filter_incomplete_user_turns))}
                    {r("incomplete_long_timeout", !tourPiloteAilleurs && Boolean(brouillon.filter_incomplete_user_turns))}
                </Intertitre>
            )}
        </Theme>
    );
};
