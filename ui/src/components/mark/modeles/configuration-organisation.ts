/**
 * [.mark] V2b (E51) : « Modèles et clés » lit et écrit la configuration de modèles de l'organisation brique par brique.
 *
 * Le serveur n'enregistre qu'UNE configuration entière (`model_configurations/v2` : chaîne = cerveau + voix +
 * transcription, ou temps réel = modèle temps réel + cerveau ; plongement facultatif dans les deux). Une carte ne
 * règle pourtant qu'une brique : ce module lit la configuration enregistrée par mode, dit quelles briques manquent
 * (la fenêtre les montre alors avec celle qu'on ouvre : on ne peut pas enregistrer une moitié de configuration) et
 * recompose la configuration entière à l'enregistrement, en gardant ce qu'on n'a pas touché.
 *
 * Aucune clé n'est lue ni affichée : le serveur rend les clés masquées, ou une référence `mark-cle:<uuid>` (nom lu
 * dans la bibliothèque), et il recolle les clés masquées avec les vraies à l'enregistrement.
 */
import type { OrganizationAiModelConfigurationV2 } from "@/client/types.gen";
import {
    asRecord,
    byokDefaults,
    getByokInitialConfig,
    hasRequiredApiKey,
    type ModelConfigurationDefaultsV2,
    preferredMode,
} from "@/components/AIModelConfigurationV2Editor";
import type { ServiceConfigurationDefaults, ServiceSegment } from "@/components/ServiceConfigurationForm";

import { estReference, PREFIXE_REFERENCE } from "../cles/ChampCleModele";
import type { Texte } from "../langue/langue";

/** Le mode de la configuration : la chaîne STT / LLM / TTS, ou un seul modèle temps réel. */
export type ModeModeles = "chaine" | "temps-reel";

/** Les briques que le serveur exige pour enregistrer le mode, dans l'ordre où l'appel les traverse. */
const REQUISES: Record<ModeModeles, ServiceSegment[]> = {
    chaine: ["stt", "llm", "tts"],
    "temps-reel": ["realtime", "llm"],
};

/** Les cartes affichées pour le mode (plongement à part, facultatif dans les deux). */
export const BRIQUES_DU_MODE: Record<ModeModeles, ServiceSegment[]> = {
    chaine: ["stt", "llm", "tts", "embeddings"],
    "temps-reel": ["realtime", "llm", "embeddings"],
};

export type Existant = Record<string, unknown>;

// Partie 3, lot 13 (SE-24, M-2) : le serveur garde DEUX configurations, `byok.pipeline` (la chaîne) et `byok.realtime` (le temps
// réel) ; `byok.mode` dit laquelle est active. Régler l'une ne fait jamais perdre l'autre.
const CLE_BLOC: Record<ModeModeles, "pipeline" | "realtime"> = { chaine: "pipeline", "temps-reel": "realtime" };

/** La configuration enregistrée d'un mode (clés masquées), qu'il soit actif ou non ; `null` quand il n'a jamais été réglé. */
export function blocEnregistre(configuration: Record<string, unknown> | null, mode: ModeModeles): Record<string, unknown> | null {
    if (configuration?.mode !== "byok") return null;
    return asRecord(asRecord(configuration.byok)?.[CLE_BLOC[mode]]);
}

/** Le mode ACTIF de la configuration enregistrée (celui que lisent les appels) ; `null` hors clés propres. */
export function modeActifEnregistre(configuration: Record<string, unknown> | null): ModeModeles | null {
    if (configuration?.mode !== "byok") return null;
    const mode = asRecord(configuration.byok)?.mode;
    return mode === "realtime" ? "temps-reel" : mode === "pipeline" ? "chaine" : null;
}

/** Le mode enregistré (ou, à défaut, celui de la configuration effective). */
export function modeEnregistre(
    configuration: Record<string, unknown> | null,
    effective: Record<string, unknown> | null,
): ModeModeles {
    return preferredMode(configuration, effective) === "realtime" ? "temps-reel" : "chaine";
}

/**
 * Ce que l'organisation a déjà réglé pour ce mode (forme du formulaire, clés masquées). Le cerveau et le plongement
 * servent dans les deux modes : s'ils ne sont réglés que dans l'autre, on les reprend.
 */
export function existantDuMode(
    configuration: Record<string, unknown> | null,
    effective: Record<string, unknown> | null,
    mode: ModeModeles,
): Existant {
    const autreMode: ModeModeles = mode === "temps-reel" ? "chaine" : "temps-reel";
    // Chaque mode se lit dans SA configuration enregistrée, active ou non (avant : seule l'active se lisait).
    const propre = blocEnregistre(configuration, mode) ?? getByokInitialConfig(configuration, effective, mode === "temps-reel");
    const autre = blocEnregistre(configuration, autreMode) ?? getByokInitialConfig(configuration, effective, mode !== "temps-reel");
    return {
        ...propre,
        llm: propre.llm ?? autre.llm,
        embeddings: propre.embeddings ?? autre.embeddings,
        is_realtime: mode === "temps-reel",
    };
}

const estPret = (existant: Existant, service: ServiceSegment, defauts: ServiceConfigurationDefaults) => {
    const configuration = asRecord(existant[service]);
    return Boolean(
        configuration && configuration.provider && configuration.provider !== "dograh" && hasRequiredApiKey(service, configuration, defauts),
    );
};

/** Les briques exigées par le serveur qui ne sont pas encore réglées (ni leur clé). */
export function briquesManquantes(
    mode: ModeModeles,
    existant: Existant,
    defauts: ServiceConfigurationDefaults,
): ServiceSegment[] {
    return REQUISES[mode].filter((service) => !estPret(existant, service, defauts));
}

/** Les briques que la fenêtre de `service` montre : la sienne, puis celles qu'il faut régler avec elle. */
export function segmentsDeLaFenetre(
    service: ServiceSegment,
    mode: ModeModeles,
    existant: Existant,
    defauts: ServiceConfigurationDefaults,
): ServiceSegment[] {
    const manquantes = briquesManquantes(mode, existant, defauts);
    return [service, ...manquantes.filter((s) => s !== service)];
}

export class ConfigurationIncomplete extends Error {
    constructor(public readonly service: ServiceSegment) {
        super(`${service} configuration is required`);
    }
}

/**
 * La configuration entière à enregistrer : les briques de `segments` viennent du formulaire, les autres de ce qui
 * est déjà réglé. Refuse (`ConfigurationIncomplete`) une brique exigée sans fournisseur ni clé.
 */
export function construireCorps(
    mode: ModeModeles,
    existant: Existant,
    sortie: Record<string, unknown>,
    segments: ServiceSegment[],
    defauts: ServiceConfigurationDefaults,
    /** La configuration enregistrée : l'autre mode y est repris tel quel, et le mode actif y est gardé (changer d'onglet n'active rien). */
    enregistree: Record<string, unknown> | null = null,
): OrganizationAiModelConfigurationV2 {
    const source = (service: ServiceSegment): Record<string, unknown> => {
        const brute = segments.includes(service) ? sortie : existant;
        return asRecord(brute[service]) ?? {};
    };
    const exigee = (service: ServiceSegment) => {
        const configuration = source(service);
        if (!configuration.provider || configuration.provider === "dograh" || !hasRequiredApiKey(service, configuration, defauts)) {
            throw new ConfigurationIncomplete(service);
        }
        return configuration;
    };
    const facultative = (service: ServiceSegment) => {
        const configuration = source(service);
        return configuration.provider && configuration.provider !== "dograh" ? configuration : undefined;
    };
    const plongement = facultative("embeddings");
    const autreMode: ModeModeles = mode === "temps-reel" ? "chaine" : "temps-reel";
    const autreBloc = blocEnregistre(enregistree, autreMode);
    // Le mode actif enregistré reste actif tant que son bloc existe ; première configuration : celle qu'on vient de régler.
    const actif = modeActifEnregistre(enregistree);
    const modeActif: ModeModeles = actif && (actif === mode || autreBloc) ? actif : mode;
    const edite =
        mode === "temps-reel"
            ? {
                  realtime: {
                      realtime: exigee("realtime") as never,
                      llm: exigee("llm") as never,
                      ...(plongement ? { embeddings: plongement as never } : {}),
                  },
              }
            : {
                  pipeline: {
                      llm: exigee("llm") as never,
                      tts: exigee("tts") as never,
                      stt: exigee("stt") as never,
                      ...(plongement ? { embeddings: plongement as never } : {}),
                  },
              };
    return {
        version: 2,
        mode: "byok",
        byok: {
            mode: CLE_BLOC[modeActif],
            ...edite,
            ...(autreBloc ? { [CLE_BLOC[autreMode]]: autreBloc as never } : {}),
        },
    };
}

/** Ce qu'une carte montre d'une brique réglée. `cle` : la référence de la bibliothèque, `"saisie"` (clé tapée à la main) ou `null`. */
export type VueBrique = { fournisseur: string; modele: string; cle: string | "saisie" | null };

export function vueDeLaBrique(existant: Existant, service: ServiceSegment): VueBrique | null {
    const configuration = asRecord(existant[service]);
    if (!configuration?.provider || configuration.provider === "dograh") return null;
    // La voix d'un fournisseur est un identifiant, pas un nom lisible : la carte dit le modèle seulement.
    const modele = typeof configuration.model === "string" ? configuration.model : "";
    const brute = Array.isArray(configuration.api_key) ? configuration.api_key[0] : configuration.api_key;
    const cle = typeof brute === "string" && brute ? (estReference(brute) ? brute.slice(PREFIXE_REFERENCE.length) : "saisie") : null;
    return { fournisseur: String(configuration.provider), modele, cle };
}

/** Le message d'une brique manquante, dit à la personne (jamais le texte du serveur). */
export const messageBriqueManquante = (service: ServiceSegment): Texte => {
    const noms: Record<ServiceSegment, Texte> = {
        llm: { en: "the brain", fr: "le cerveau" },
        tts: { en: "the voice", fr: "la voix" },
        stt: { en: "the transcription", fr: "la transcription" },
        embeddings: { en: "the embedding", fr: "le plongement" },
        realtime: { en: "the realtime model", fr: "le modèle temps réel" },
    };
    const nom = noms[service];
    return {
        en: `Choose a provider and a key for ${nom.en} too: the configuration is saved as a whole.`,
        fr: `Choisis aussi un fournisseur et une clé pour ${nom.fr} : la configuration s'enregistre d'un bloc.`,
    };
};

export { byokDefaults };
export type { ModelConfigurationDefaultsV2 };
