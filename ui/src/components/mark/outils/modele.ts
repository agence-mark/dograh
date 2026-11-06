/**
 * [.mark] U3 sexies (E73 à E75) : ce que l'écran des Outils sait d'un outil, sans rien inventer.
 *
 * Tout ce qui est réglé vit dans `definition.config` (aucune migration) ; l'écran lit et écrit ces clés telles
 * que le serveur les définit (`api/schemas/tool.py`). Les types de l'API restent des objets ouverts : on lit avec
 * les accesseurs ci-dessous plutôt que de supposer une forme.
 */
import type { ToolResponse } from "@/client/types.gen";

export type Config = Record<string, unknown>;

export const TYPES_D_OUTIL = [
    "integration",
    "http_api",
    "mcp",
    "transfer_call",
    "transfer_agent",
    "end_call",
    "native",
    "calculator",
] as const;
export type TypeOutil = (typeof TYPES_D_OUTIL)[number];

export const LIBELLES_TYPE: Record<TypeOutil, { en: string; fr: string }> = {
    integration: { en: "Software action", fr: "Action d'un logiciel" },
    http_api: { en: "HTTP request", fr: "Requête HTTP" },
    mcp: { en: "MCP tool", fr: "Outil MCP" },
    transfer_call: { en: "Call transfer", fr: "Transfert d'appel" },
    transfer_agent: { en: "Transfer to an agent", fr: "Transfert vers un agent" },
    end_call: { en: "End of call", fr: "Fin d'appel" },
    native: { en: "Call-back request", fr: "Demande de rappel" },
    calculator: { en: "Calculator", fr: "Calculatrice" },
};

/** Les types qui appellent l'extérieur : ils ont un comportement, un essai et des statistiques d'exécution. */
export const APPELLE_L_EXTERIEUR = new Set<string>(["http_api", "mcp", "integration"]);

export const configDe = (outil: Pick<ToolResponse, "definition">): Config => {
    const c = (outil.definition as { config?: unknown } | undefined)?.config;
    return c && typeof c === "object" ? (c as Config) : {};
};

export const texte = (c: Config, cle: string): string => (typeof c[cle] === "string" ? (c[cle] as string) : "");
export const nombre = (c: Config, cle: string, defaut: number): number =>
    typeof c[cle] === "number" ? (c[cle] as number) : defaut;
export const booleen = (c: Config, cle: string): boolean => c[cle] === true;
export function liste<T>(c: Config, cle: string): T[] {
    return Array.isArray(c[cle]) ? (c[cle] as T[]) : [];
}

/** La phrase avant l'outil : sans réglage, « toujours » quand une phrase est écrite (le comportement d'avant). */
export type ModePhrase = "auto" | "toujours" | "jamais";
export const modeDePhrase = (c: Config): ModePhrase => {
    const m = c.phrase_avant_mode;
    if (m === "auto" || m === "toujours" || m === "jamais") return m;
    const aPhrase = c.customMessageType === "audio" ? Boolean(c.customMessageRecordingId) : texte(c, "customMessage").trim() !== "";
    return aPhrase ? "toujours" : "jamais";
};

/** Même règle que le serveur (`essai.ecrit`) pour une requête HTTP ; une action de logiciel le dit par son catalogue. */
export function ecritHttp(c: Config): boolean {
    return String(c.method ?? "POST").toUpperCase() !== "GET" && !booleen(c, "sans_risque_de_doublon");
}

export const premierEssaiValide = (c: Config): boolean => Boolean(c.premier_essai);

/** Un outil à ajouter dans `config` sans toucher au reste : la définition complète avec la config fusionnée. */
export function definitionAvec(outil: Pick<ToolResponse, "definition">, modifs: Config): Record<string, unknown> {
    const d = (outil.definition ?? {}) as Record<string, unknown>;
    const fusionnee: Config = { ...configDe(outil) };
    for (const [k, v] of Object.entries(modifs)) {
        if (v === undefined) delete fusionnee[k];
        else fusionnee[k] = v;
    }
    return { ...d, config: fusionnee };
}
