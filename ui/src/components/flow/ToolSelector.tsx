"use client";

import { Plus, RefreshCw, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useWorkflowOptional } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import type { ToolResponse } from "@/client/types.gen";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import { type McpDiscoveredTool, refreshMcpTools } from "./mcpRefresh";

interface ToolSelectorProps {
    value: string[];
    onChange: (uuids: string[]) => void;
    tools: ToolResponse[];
    disabled?: boolean;
    label?: string;
    description?: string;
    showLabel?: boolean;
    mcpToolFilters?: Record<string, string[]>;
    onMcpToolFiltersChange?: (next: Record<string, string[]>) => void;
}

function isMcp(tool: ToolResponse): boolean {
    return tool.category === "mcp";
}

function discoveredOf(tool: ToolResponse): McpDiscoveredTool[] {
    const def = (tool.definition ?? {}) as {
        config?: { discovered_tools?: McpDiscoveredTool[] };
    };
    return def.config?.discovered_tools ?? [];
}

function withDiscoveredTools(tool: ToolResponse, discoveredTools: McpDiscoveredTool[]): ToolResponse {
    const definition = tool.definition && typeof tool.definition === "object" ? tool.definition : {};
    const config = "config" in definition && definition.config && typeof definition.config === "object" ? definition.config : {};

    return {
        ...tool,
        definition: {
            ...definition,
            config: {
                ...config,
                discovered_tools: discoveredTools,
            },
        },
    };
}

const T = {
    mcp: { en: "Tools of an MCP server", fr: "Outils d'un serveur MCP" },
    mcpAide: {
        en: "Filter: only the checked tools of the server are given to the step.",
        fr: "Filtre : seuls les outils cochés du serveur sont donnés à l'étape.",
    },
    ajouterOutil: { en: "tool", fr: "outil" },
    ajouterServeur: { en: "MCP server", fr: "Serveur MCP" },
    aucunOutil: { en: "No tool available yet.", fr: "Aucun outil disponible pour l'instant." },
    gerer: { en: "Manage tools", fr: "Gérer les outils" },
    retirer: { en: "Remove", fr: "Retirer" },
    actualiser: { en: "Refresh the tools", fr: "Actualiser les outils" },
    aucuneFonction: { en: "No tool found: refresh.", fr: "Aucun outil trouvé : actualiser." },
    indisponible: { en: "unavailable", fr: "indisponible" },
} satisfies Record<string, Texte>;

/**
 * [.mark] K2b : le choix des outils d'une étape comme la maquette le dessine (`modale-noeud.tsx`) : les outils choisis en
 * pastilles et « + outil » qui ouvre la liste ; ceux d'un serveur MCP en lignes « serveur · outils » et « + Serveur MCP ».
 * Les valeurs écrites sont celles d'avant (les identifiants d'outils et le filtre des outils MCP).
 */
export function ToolSelector({
    value,
    onChange,
    tools,
    disabled = false,
    label = "Tools",
    description = "Select tools that the agent can use during the conversation.",
    showLabel = true,
    mcpToolFilters = {},
    onMcpToolFiltersChange = () => {},
}: ToolSelectorProps) {
    const { t } = useLangue();
    const workflow = useWorkflowOptional();
    const activeTools = tools.filter((x) => x.status === "active");
    const httpTools = activeTools.filter((x) => !isMcp(x));
    const mcpTools = activeTools.filter(isMcp);

    const [refreshing, setRefreshing] = useState<Record<string, boolean>>({});
    const [refreshError, setRefreshError] = useState<Record<string, string>>({});

    const httpHandleToggle = (toolUuid: string, checked: boolean) => {
        if (checked) onChange([...value, toolUuid]);
        else onChange(value.filter((id) => id !== toolUuid));
    };

    const mcpFnToggle = (toolUuid: string, fnName: string, checked: boolean) => {
        const current = mcpToolFilters[toolUuid] ?? [];
        const nextFns = checked ? Array.from(new Set([...current, fnName])) : current.filter((n) => n !== fnName);

        const nextFilters = { ...mcpToolFilters };
        if (nextFns.length > 0) nextFilters[toolUuid] = nextFns;
        else delete nextFilters[toolUuid];
        onMcpToolFiltersChange(nextFilters);

        const hasUuid = value.includes(toolUuid);
        if (nextFns.length > 0 && !hasUuid) onChange([...value, toolUuid]);
        else if (nextFns.length === 0 && hasUuid) onChange(value.filter((id) => id !== toolUuid));
    };

    const doRefresh = async (toolUuid: string) => {
        setRefreshing((r) => ({ ...r, [toolUuid]: true }));
        setRefreshError((e) => {
            const n = { ...e };
            delete n[toolUuid];
            return n;
        });
        const res = await refreshMcpTools(toolUuid);
        setRefreshing((r) => ({ ...r, [toolUuid]: false }));
        if (res.error && res.discovered_tools.length === 0) {
            setRefreshError((e) => ({ ...e, [toolUuid]: res.error as string }));
            return;
        }
        workflow?.updateTool?.(toolUuid, (tool) => withDiscoveredTools(tool, res.discovered_tools));
    };

    const choisis = httpTools.filter((x) => value.includes(x.tool_uuid));
    const serveursChoisis = mcpTools.filter((x) => (mcpToolFilters[x.tool_uuid] ?? []).length > 0);

    const boutonAjout =
        "inline-flex h-6 cursor-pointer items-center gap-1 rounded-md px-2 text-sm text-muted-foreground hover:font-medium hover:text-foreground";

    return (
        <div className="grid gap-5" data-selecteur-outils>
            <div className="grid gap-1.5">
                {showLabel && (
                    <Label className="flex items-center gap-1.5">
                        {label}
                        {description && <Info>{description}</Info>}
                    </Label>
                )}
                <div className="flex flex-wrap items-center gap-2">
                    {choisis.map((tool) => (
                        <span key={tool.tool_uuid} className="inline-flex h-6 items-center gap-1 rounded-md border px-2 text-xs">
                            {tool.name}
                            <button
                                type="button"
                                disabled={disabled}
                                aria-label={`${t(T.retirer)} ${tool.name}`}
                                className="cursor-pointer text-muted-foreground hover:text-foreground"
                                onClick={() => httpHandleToggle(tool.tool_uuid, false)}
                            >
                                <X className="size-3" />
                            </button>
                        </span>
                    ))}
                    <Popover>
                        <PopoverTrigger asChild>
                            <button type="button" disabled={disabled} className={boutonAjout}>
                                + {t(T.ajouterOutil)}
                            </button>
                        </PopoverTrigger>
                        <PopoverContent align="start" className="w-80 p-1">
                            {httpTools.length === 0 && <p className="px-3 py-2 text-sm text-muted-foreground">{t(T.aucunOutil)}</p>}
                            <div className="max-h-64 overflow-y-auto">
                                {httpTools.map((tool) => (
                                    <label key={tool.tool_uuid} className="flex cursor-pointer items-center gap-3 rounded-md px-3 py-2 hover:bg-muted/50">
                                        <Checkbox
                                            checked={value.includes(tool.tool_uuid)}
                                            disabled={disabled}
                                            onCheckedChange={(c) => httpHandleToggle(tool.tool_uuid, c === true)}
                                        />
                                        <span className="flex min-w-0 flex-1 flex-col">
                                            <span className="truncate text-sm font-medium">{tool.name}</span>
                                            {tool.description && <span className="break-words text-xs text-muted-foreground">{tool.description}</span>}
                                        </span>
                                    </label>
                                ))}
                            </div>
                            <Link href="/tools" target="_blank" className="block px-3 py-2 text-sm text-muted-foreground hover:font-medium hover:text-foreground">
                                {t(T.gerer)}
                            </Link>
                        </PopoverContent>
                    </Popover>
                </div>
            </div>

            {mcpTools.length > 0 && (
                <div className="grid gap-1.5">
                    <Label className="flex items-center gap-1.5">
                        {t(T.mcp)}
                        <Info>{t(T.mcpAide)}</Info>
                    </Label>
                    <ul className="divide-y border-y text-sm">
                        {serveursChoisis.map((tool) => (
                            <li key={tool.tool_uuid} className="flex items-center gap-2 py-2">
                                <span className="min-w-0 flex-1 truncate">
                                    {tool.name} <span className="text-muted-foreground">· {(mcpToolFilters[tool.tool_uuid] ?? []).join(", ")}</span>
                                </span>
                                <button
                                    type="button"
                                    disabled={disabled}
                                    aria-label={`${t(T.retirer)} ${tool.name}`}
                                    className="shrink-0 cursor-pointer text-muted-foreground hover:text-foreground"
                                    onClick={() => {
                                        const next = { ...mcpToolFilters };
                                        delete next[tool.tool_uuid];
                                        onMcpToolFiltersChange(next);
                                        onChange(value.filter((id) => id !== tool.tool_uuid));
                                    }}
                                >
                                    <X className="size-3.5" />
                                </button>
                            </li>
                        ))}
                        <li>
                            <Popover>
                                <PopoverTrigger asChild>
                                    <button
                                        type="button"
                                        disabled={disabled}
                                        className="flex w-full cursor-pointer items-center gap-1.5 py-2 text-left text-muted-foreground hover:font-medium hover:text-foreground"
                                    >
                                        <Plus className="size-3.5" /> {t(T.ajouterServeur)}
                                    </button>
                                </PopoverTrigger>
                                <PopoverContent align="start" className="w-96 p-1">
                                    <div className="max-h-72 overflow-y-auto">
                                        {mcpTools.map((tool) => {
                                            const fns = discoveredOf(tool);
                                            const selected = mcpToolFilters[tool.tool_uuid] ?? [];
                                            const busy = !!refreshing[tool.tool_uuid];
                                            const err = refreshError[tool.tool_uuid];
                                            return (
                                                <div key={tool.tool_uuid} className="grid gap-2 px-3 py-2">
                                                    <div className="flex items-center gap-2">
                                                        <span className="min-w-0 flex-1 truncate text-sm font-medium">{tool.name}</span>
                                                        <button
                                                            type="button"
                                                            disabled={busy || disabled}
                                                            aria-label={t(T.actualiser)}
                                                            title={t(T.actualiser)}
                                                            className="cursor-pointer text-muted-foreground hover:text-foreground"
                                                            onClick={() => doRefresh(tool.tool_uuid)}
                                                        >
                                                            <RefreshCw className={`size-3.5 ${busy ? "animate-spin" : ""}`} />
                                                        </button>
                                                    </div>
                                                    {err && <p className="text-xs text-destructive">{err}</p>}
                                                    {fns.length === 0 && !err && <p className="text-xs text-muted-foreground">{t(T.aucuneFonction)}</p>}
                                                    {fns.map((fn) => (
                                                        <label key={fn.name} className="flex cursor-pointer items-start gap-3">
                                                            <Checkbox
                                                                checked={selected.includes(fn.name)}
                                                                disabled={disabled}
                                                                onCheckedChange={(c) => mcpFnToggle(tool.tool_uuid, fn.name, c === true)}
                                                            />
                                                            <span className="flex min-w-0 flex-1 flex-col">
                                                                <span className="text-sm">{fn.name}</span>
                                                                {fn.description && <span className="break-words text-xs text-muted-foreground">{fn.description}</span>}
                                                            </span>
                                                        </label>
                                                    ))}
                                                    {selected
                                                        .filter((n) => !fns.some((f) => f.name === n))
                                                        .map((n) => (
                                                            <label key={`stale-${n}`} className="flex cursor-pointer items-start gap-3 opacity-60">
                                                                <Checkbox checked disabled={disabled} onCheckedChange={() => mcpFnToggle(tool.tool_uuid, n, false)} />
                                                                <span className="text-sm line-through">
                                                                    {n} ({t(T.indisponible)})
                                                                </span>
                                                            </label>
                                                        ))}
                                                </div>
                                            );
                                        })}
                                    </div>
                                </PopoverContent>
                            </Popover>
                        </li>
                    </ul>
                </div>
            )}
        </div>
    );
}
