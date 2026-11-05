import { NodeProps } from "@xyflow/react";
import * as LucideIcons from "lucide-react";
import { Check, Circle, Copy, Flag, type LucideIcon, Play, Square } from "lucide-react";
import Link from "next/link";
import { memo, type ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { useWorkflow } from "@/app/workflow/[workflowId]/contexts/WorkflowContext";
import { useWorkflowStore } from "@/app/workflow/[workflowId]/stores/workflowStore";
import type { NodeSpec } from "@/client/types.gen";
import { DocumentBadges } from "@/components/flow/DocumentBadges";
import { NodeEditForm, useNodeSpecs } from "@/components/flow/renderer";
import { evaluateDisplayOptions } from "@/components/flow/renderer/displayOptions";
import { ToolBadges } from "@/components/flow/ToolBadges";
import { FlowNodeData } from "@/components/flow/types";
import { useBuilderEcran } from "@/components/builder/ecran/store";
import { useLangue } from "@/components/mark/langue/langue";
import { useOuvertureNoeud } from "@/components/mark/agent/ouverture-noeud";
import { BarreAuSurvol, useSurvolDeLEtape } from "@/components/mark/graphe/BarreAuSurvol";
import { BriqueAgent } from "@/components/mark/graphe/BriqueAgent";
import { copieDeLEtape } from "@/components/mark/graphe/dupliquer-etape";
import {
    DeclenchementDeLAction,
    positionEcrite,
    positionLue,
} from "@/components/mark/graphe/DeclenchementDeLAction";
import { EtapeDeRetour } from "@/components/mark/graphe/EtapeDeRetour";
import { type ConditionDeChamp } from "@/components/mark/graphe/EtiquettesEtape";
import { OngletsNoeud } from "@/components/mark/graphe/OngletsNoeud";
import { type FinFigee,PhrasesDeFin } from "@/components/mark/graphe/PhrasesDeFin";
import { OrdreDInjection } from "@/components/mark/graphe/OrdreDInjection";
import { PhrasesDeLEtape } from "@/components/mark/graphe/PhrasesDeLEtape";
import { RetourAuPrincipal } from "@/components/mark/graphe/RetourAuPrincipal";
import {
    PROPRIETE_DU_NOM,
    proprietesDeLaSection,
    proprietesMasquees,
    type SectionNoeud,
    sectionsAMontrer,
} from "@/components/mark/graphe/sections-noeud";
import { TravailDeFond } from "@/components/mark/graphe/TravailDeFond";
import {
    agentQuiAgit,
    caseCochee,
    etapeQuiEcrit,
    valeurAEcrire,
    VeriteDesActions,
} from "@/components/mark/graphe/VeriteDesActions";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAppConfig } from "@/context/AppConfigContext";
import { copyTextToClipboard } from "@/lib/clipboard";
import { cn } from "@/lib/utils";
import { createUuid } from "@/lib/uuid";
import { resolveWebhookBaseUrl } from "@/lib/webhookUrl";

import { NodeContent } from "./common/NodeContent";
import { NodeEditDialog } from "./common/NodeEditDialog";
import { useNodeHandlers } from "./common/useNodeHandlers";

// ─── Static per-spec UI maps ──────────────────────────────────────────────
// Small lookups indexed by spec.name. Keeping these in the renderer (not
// the spec) avoids leaking UI concerns into the backend schema. Add an
// entry when registering a new node type.

type NodeStyleVariant =
    | "start"
    | "agent"
    | "end"
    | "global"
    | "trigger"
    | "webhook"
    | "qa"
    | "integration";

const STYLE_VARIANT_BY_SPEC: Record<string, NodeStyleVariant> = {
    startCall: "start",
    agentNode: "agent",
    endCall: "end",
    globalNode: "global",
    trigger: "trigger",
    webhook: "webhook",
    qa: "qa",
};

const HANDLES_BY_SPEC: Record<string, { source: boolean; target: boolean }> = {
    startCall: { source: true, target: false },
    agentNode: { source: true, target: true },
    endCall: { source: false, target: true },
    globalNode: { source: false, target: false },
    trigger: { source: false, target: false },
    webhook: { source: false, target: false },
    qa: { source: false, target: false },
};

// ─── Helpers ──────────────────────────────────────────────────────────────

function resolveIcon(name: string): LucideIcon {
    const icons = LucideIcons as unknown as Record<string, LucideIcon>;
    return icons[name] ?? Circle;
}

function seedValues(
    data: FlowNodeData,
    spec: NodeSpec,
): Record<string, unknown> {
    const d = data as unknown as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const prop of spec.properties) {
        out[prop.name] = d[prop.name] ?? prop.default ?? undefined;
    }
    return out;
}

interface TriggerEndpoints {
    production: string;
    test: string;
}

function buildTriggerEndpoints(
    triggerPath: string | undefined,
    baseUrl: string,
): TriggerEndpoints {
    if (!triggerPath) return { production: "", test: "" };
    return {
        production: `${baseUrl}/api/v1/public/agent/${triggerPath}`,
        test: `${baseUrl}/api/v1/public/agent/test/${triggerPath}`,
    };
}

function resolveIntegrationEnabled(
    spec: NodeSpec,
    data: FlowNodeData,
): boolean {
    for (const prop of spec.properties) {
        if (!prop.name.endsWith("enabled")) continue;
        const value = data[prop.name];
        if (typeof value === "boolean") return value;
    }
    return true;
}

function resolveIntegrationSummary(
    spec: NodeSpec,
    data: FlowNodeData,
): string {
    let hasSecret = false;
    for (const prop of spec.properties) {
        if (prop.name === "name" || prop.name.endsWith("enabled")) {
            continue;
        }
        // A configured API key/token/secret is never displayed, but it does
        // prove the node is set up. Remember that so a node whose only real
        // config is a secret (e.g. an integration identified solely by its key)
        // isn't mislabelled "Not configured".
        if (/api[_-]?key|token|secret/i.test(prop.name)) {
            const secret = data[prop.name];
            if (typeof secret === "string" && secret.trim().length > 0) {
                hasSecret = true;
            }
            continue;
        }

        const value = data[prop.name];
        if (typeof value === "string" && value.trim().length > 0) {
            return value.length > 30 ? `${value.slice(0, 30)}...` : value;
        }
        if (typeof value === "number") {
            return String(value);
        }
    }
    return hasSecret ? "Configured" : "Not configured";
}

function getBadgeForSpec(spec: NodeSpec | undefined, variant: NodeStyleVariant, langue: "fr" | "en"): { label: string } {
    const L = (fr: string, en: string) => (langue === "fr" ? fr : en);
    if (!spec) return { label: L("Nœud", "Node") };
    switch (variant) {
        case "start":
            return { label: L("Début", "Start") };
        case "agent":
            return { label: L("Étape", "Step") };
        case "end":
            return { label: L("Fin", "End") };
        case "global":
            return { label: "Global" };
        case "trigger":
            return { label: L("Déclencheur", "Trigger") };
        case "webhook":
            return { label: "Webhook" };
        case "qa":
            return { label: L("Contrôle qualité", "Quality control") };
        case "integration":
            return { label: spec.display_name };
    }
}

/** Le type d'un nœud, dit comme la carte le dit (« Étape », « Fin », « Contrôle qualité »…) : le menu « Nœud » le reprend. */
export function libelleDuType(spec: NodeSpec, langue: "fr" | "en"): string {
    return getBadgeForSpec(spec, STYLE_VARIANT_BY_SPEC[spec.name] ?? "integration", langue).label;
}

/** Le texte de la carte : le prompt sans ses titres, tel que l'étape le dit (la maquette en montre deux lignes). */
function resumeDuPrompt(prompt?: string): string {
    return (prompt ?? "")
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#"))
        .join(" ");
}

// ─── Canvas preview dispatch ──────────────────────────────────────────────

function CanvasPreview({
    spec,
    data,
    onCopyTrigger,
    triggerCopied,
    onStaleTools,
    onStaleDocuments,
}: {
    spec: NodeSpec;
    data: FlowNodeData;
    onCopyTrigger: () => void;
    triggerCopied: boolean;
    onStaleTools: (uuids: string[]) => void;
    onStaleDocuments: (uuids: string[]) => void;
}) {
    const { config: appConfig } = useAppConfig();
    if (spec.name === "trigger") {
        const endpoint = buildTriggerEndpoints(
            data.trigger_path,
            resolveWebhookBaseUrl(appConfig?.tunnelUrl),
        ).production;
        return (
            <div className="space-y-2">
                <p className="text-xs text-muted-foreground">API Endpoint:</p>
                <div className="flex items-center gap-1">
                    <code className="text-xs break-all bg-muted px-1 py-0.5 rounded flex-1">
                        {endpoint || "Generating..."}
                    </code>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6 shrink-0"
                        onClick={(e) => {
                            e.stopPropagation();
                            onCopyTrigger();
                        }}
                    >
                        {triggerCopied ? (
                            <Check className="h-3 w-3" />
                        ) : (
                            <Copy className="h-3 w-3" />
                        )}
                    </Button>
                </div>
            </div>
        );
    }

    if (spec.name === "webhook") {
        const method = data.http_method || "POST";
        const url = data.endpoint_url || "";
        const enabled = data.enabled !== false;
        const truncated = !url
            ? "Not configured"
            : url.length > 30
            ? url.slice(0, 30) + "..."
            : url;
        return (
            <div className="space-y-2">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                        {method}
                    </span>
                    <span className="text-xs text-muted-foreground truncate flex-1">
                        {truncated}
                    </span>
                </div>
                <StatusDot enabled={enabled} />
            </div>
        );
    }

    if (spec.name === "qa") {
        const llmSource =
            data.qa_use_workflow_llm !== false
                ? "Workflow LLM"
                : `${data.qa_provider || "openai"}/${data.qa_model || "gpt-4.1"}`;
        const enabled = data.qa_enabled !== false;
        return (
            <div className="space-y-2">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                        {llmSource}
                    </span>
                </div>
                <StatusDot enabled={enabled} />
            </div>
        );
    }

    if (spec.category === "integration") {
        const enabled = resolveIntegrationEnabled(spec, data);
        const destination = resolveIntegrationSummary(spec, data);
        return (
            <div className="space-y-2">
                <div className="flex items-center gap-2">
                    <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded">
                        {destination}
                    </span>
                </div>
                <StatusDot enabled={enabled} />
            </div>
        );
    }

    // Défaut : deux lignes du prompt (maquette). Les pastilles d'outils et de documents restent montées, cachées : elles
    // retirent d'elles-mêmes les outils et documents qui n'existent plus ; leur liste se lit dans la fenêtre de l'étape.
    const hasToolRefs = spec.properties.some((p) => p.type === "tool_refs");
    const hasDocRefs = spec.properties.some((p) => p.type === "document_refs");
    return (
        <>
            <p className="line-clamp-2 text-xs text-muted-foreground">{resumeDuPrompt(data.prompt)}</p>
            <div hidden>
                {hasToolRefs && data.tool_uuids && data.tool_uuids.length > 0 && (
                    <ToolBadges
                        toolUuids={data.tool_uuids}
                        onStaleUuidsDetected={onStaleTools}
                        mcpToolFilters={data.mcp_tool_filters}
                    />
                )}
                {hasDocRefs && data.document_uuids && data.document_uuids.length > 0 && (
                    <DocumentBadges documentUuids={data.document_uuids} onStaleUuidsDetected={onStaleDocuments} />
                )}
            </div>
        </>
    );
}

function StatusDot({ enabled }: { enabled: boolean }) {
    return (
        <div className="flex items-center gap-1.5">
            <Circle
                className={`h-2 w-2 ${
                    enabled
                        ? "fill-(--signal-ok) text-(--signal-ok)"
                        : "fill-muted-foreground text-muted-foreground"
                }`}
            />
            <span className="text-xs text-muted-foreground">
                {enabled ? "Enabled" : "Disabled"}
            </span>
        </div>
    );
}

// ─── Trigger webhook URLs (test + production) — rendered inside the dialog ─

function buildCurl(endpoint: string): string {
    return `curl -X POST "${endpoint}" \\
  -H "X-API-Key: YOUR_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"phone_number": "+1234567890", "initial_context": {}}'`;
}

function ClickToCopy({
    value,
    children,
    className,
    title,
}: {
    value: string;
    children: React.ReactNode;
    className?: string;
    title?: string;
}) {
    const [copied, setCopied] = useState(false);
    const onCopy = async () => {
        if (!value) return;
        try {
            await copyTextToClipboard(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };
    return (
        <button
            type="button"
            onClick={onCopy}
            title={title ?? "Click to copy"}
            className={cn(
                "group relative text-left transition-colors hover:bg-accent/60 cursor-pointer disabled:cursor-default",
                className,
            )}
            disabled={!value}
        >
            {children}
            <span
                aria-hidden={!copied}
                className={cn(
                    "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded bg-foreground/90 px-1.5 py-0.5 text-[10px] font-medium text-background shadow transition-opacity",
                    copied ? "opacity-100" : "opacity-0",
                )}
            >
                Copied!
            </span>
        </button>
    );
}

function UrlPanel({
    endpoint,
    helperText,
}: {
    endpoint: string;
    helperText: string;
}) {
    const curl = endpoint ? buildCurl(endpoint) : "";
    return (
        <div className="grid gap-2 pt-2">
            <div className="flex items-center gap-2">
                <span className="text-xs font-mono bg-muted px-1.5 py-0.5 rounded shrink-0">
                    POST
                </span>
                <ClickToCopy
                    value={endpoint}
                    title="Click to copy URL"
                    className="flex-1 bg-muted rounded px-2 py-1"
                >
                    <code className="text-xs break-all">
                        {endpoint || "Generating..."}
                    </code>
                </ClickToCopy>
            </div>
            <p className="text-xs text-muted-foreground">{helperText}</p>
            <p className="text-sm font-medium pt-2">Example Request</p>
            <ClickToCopy
                value={curl}
                title="Click to copy curl"
                className="block w-full bg-muted rounded"
            >
                <pre className="text-xs px-3 py-2 overflow-x-auto whitespace-pre-wrap">
                    {curl || "Generating..."}
                </pre>
            </ClickToCopy>
        </div>
    );
}

function TriggerWebhookUrls({ endpoints }: { endpoints: TriggerEndpoints }) {
    return (
        <div className="grid gap-2">
            <p className="text-sm font-medium">Webhook URLs</p>
            <p className="text-xs text-muted-foreground">
                Test mode runs the latest draft so you can verify changes before
                publishing. Production runs the published agent. Both require an
                API key in the X-API-Key header.{" "}
                <Link
                    href="/api-keys"
                    target="_blank"
                    className="text-primary underline hover:no-underline"
                >
                    Get your API key
                </Link>
            </p>
            <Tabs defaultValue="test" className="w-full">
                <TabsList>
                    <TabsTrigger value="test">Test URL</TabsTrigger>
                    <TabsTrigger value="production">Production URL</TabsTrigger>
                </TabsList>
                <TabsContent value="test">
                    <UrlPanel
                        endpoint={endpoints.test}
                        helperText="Runs the latest draft, falling back to the published agent when no draft exists."
                    />
                </TabsContent>
                <TabsContent value="production">
                    <UrlPanel
                        endpoint={endpoints.production}
                        helperText="Runs the published agent."
                    />
                </TabsContent>
            </Tabs>
        </div>
    );
}

// ─── GenericNode ──────────────────────────────────────────────────────────

interface GenericNodeProps extends NodeProps {
    data: FlowNodeData;
    type: string;
}

export const GenericNode = memo(({ data, selected, id, type }: GenericNodeProps) => {
    // Per-type metadata that StartCall/EndCall used to set via `additionalData`
    // (is_start / is_end). Pulled from the spec name here.
    const additionalData = useMemo<Record<string, boolean> | undefined>(() => {
        const out: Record<string, boolean> = {};
        if (type === "startCall") out.is_start = true;
        if (type === "endCall") out.is_end = true;
        return Object.keys(out).length > 0 ? out : undefined;
    }, [type]);

    const { open, setOpen, handleSaveNodeData, handleDeleteNode } = useNodeHandlers({
        id,
        additionalData,
    });
    // [.mark] E36 : la barre du canevas (« Prompt général ») demande l'ouverture de cette fenêtre.
    const demandeOuverture = useOuvertureNoeud((s) => s.demande);
    useEffect(() => {
        if (demandeOuverture?.id === id) setOpen(true);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [demandeOuverture?.cle]);
    const { saveWorkflow, tools, documents, recordings, champsFiche, outilsQuiEcrivent, agentPrincipalId, estPrincipal, travailActif, readOnly: lectureSeule } =
        useWorkflow();
    // [.mark] Partie 3, sous-lot 20 : la barre au survol et ses gestes.
    const { survol, entrer: entrerSurvol, sortir: sortirSurvol } = useSurvolDeLEtape();
    const ajouterUneEtape = useWorkflowStore((s) => s.addNode);
    // fiabilite-de-la-conversation: the start step shows « Truth of actions » as soon as the agent acts anywhere.
    const agentAgit = useWorkflowStore((s) => agentQuiAgit(s.nodes, travailActif === true));
    const { bySpecName } = useNodeSpecs();
    const { config: appConfig } = useAppConfig();
    const spec = bySpecName.get(type);
    const dupliquerLEtape = useCallback(() => {
        const copie = copieDeLEtape(useWorkflowStore.getState().nodes, id, "(copie)", bySpecName.get(type)?.graph_constraints?.max_instances);
        if (copie) ajouterUneEtape(copie);
    }, [id, type, bySpecName, ajouterUneEtape]);
    const webhookBaseUrl = resolveWebhookBaseUrl(appConfig?.tunnelUrl);

    // ── Form state ─────────────────────────────────────────────────────
    // mcp_tool_filters is not a spec property, so seedValues won't carry it;
    // seed merges it back in alongside the spec-derived values.
    const seed = useCallback(
        () =>
            spec
                ? {
                      ...seedValues(data, spec),
                      mcp_tool_filters: data.mcp_tool_filters,
                      // [.mark] Lot 12: two node data the generated form does not draw (their widgets
                      // are ours): the return to the main agent, and the closing sentences.
                      // Lot 2 d'orchestrateur-trois-cerveaux: and the return step of the main agent.
                      retour_au_principal: data.retour_au_principal,
                      etape_de_retour: data.etape_de_retour,
                      // modules-et-cerveaux (lot 5): the step's background work box.
                      travail_de_fond: data.travail_de_fond,
                      // correctifs-apres-banc-commun (lot 5): the step's "truth of actions" box (empty = on).
                      verite_des_actions: data.verite_des_actions,
                      // correctifs-apres-banc-commun (lots 6 and 7): the action trigger menu (empty = free), its request
                      // template, and the conditions of the step's fields.
                      declenchement_de_l_action: data.declenchement_de_l_action,
                      demande_type: data.demande_type,
                      conditions_de_champs: data.conditions_de_champs,
                      fins: data.fins,
                  }
                : {},
        [data, spec],
    );

    const [values, setValues] = useState<Record<string, unknown>>(seed);
    // [.mark] Lot 11 de correctifs-apres-banc-commun (F-2): « Truth of actions » is on by default when the step writes.
    const etapeEcrit = etapeQuiEcrit(
        (values.tool_uuids as string[] | undefined) ?? [],
        tools ?? [],
        outilsQuiEcrivent ?? [],
        travailActif === true && values.travail_de_fond === true,
    );

    // Re-seed once the spec arrives (initial fetch race).
    useEffect(() => {
        if (spec && Object.keys(values).length === 0) {
            setValues(seed());
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [spec]);

    // ── Trigger auto-UUID + canvas copy state ──────────────────────────
    const [triggerCopied, setTriggerCopied] = useState(false);
    const handleCopyTrigger = useCallback(async () => {
        const endpoint = buildTriggerEndpoints(data.trigger_path, webhookBaseUrl).production;
        if (!endpoint) return;
        try {
            await copyTextToClipboard(endpoint);
            setTriggerCopied(true);
            setTimeout(() => setTriggerCopied(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    }, [data.trigger_path, webhookBaseUrl]);

    // For trigger nodes without a path yet, generate one and persist.
    useEffect(() => {
        if (type !== "trigger") return;
        if (data.trigger_path) return;
        const newPath = createUuid();
        handleSaveNodeData({ ...data, trigger_path: newPath });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [type]);

    // ── Stale tool/document cleanup (was duplicated in Start/Agent) ─────
    const handleStaleTools = useCallback(
        async (staleUuids: string[]) => {
            const cleaned = (data.tool_uuids ?? []).filter(
                (u) => !staleUuids.includes(u),
            );
            handleSaveNodeData({
                ...data,
                tool_uuids: cleaned.length > 0 ? cleaned : undefined,
            });
            await saveWorkflow();
        },
        [data, handleSaveNodeData, saveWorkflow],
    );
    const handleStaleDocuments = useCallback(
        async (staleUuids: string[]) => {
            const cleaned = (data.document_uuids ?? []).filter(
                (u) => !staleUuids.includes(u),
            );
            handleSaveNodeData({
                ...data,
                document_uuids: cleaned.length > 0 ? cleaned : undefined,
            });
            await saveWorkflow();
        },
        [data, handleSaveNodeData, saveWorkflow],
    );

    // ── Dirty / save / open handlers ────────────────────────────────────
    const propertyNames = useMemo(
        () => spec?.properties.map((p) => p.name) ?? [],
        [spec],
    );

    const isDirty = useMemo(() => {
        if (!spec) return false;
        const baseline = seedValues(data, spec);
        if (propertyNames.some((n) => values[n] !== baseline[n])) return true;
        if ((values.retour_au_principal ?? false) !== (data.retour_au_principal ?? false)) return true;
        if ((values.etape_de_retour ?? false) !== (data.etape_de_retour ?? false)) return true;
        if ((values.travail_de_fond ?? false) !== (data.travail_de_fond ?? false)) return true;
        if ((values.verite_des_actions ?? null) !== (data.verite_des_actions ?? null)) return true;
        if ((values.declenchement_de_l_action ?? "libre") !== (data.declenchement_de_l_action ?? "libre")) return true;
        if ((values.demande_type ?? "") !== (data.demande_type ?? "")) return true;
        if (JSON.stringify(values.conditions_de_champs ?? null) !== JSON.stringify(data.conditions_de_champs ?? null)) return true;
        if (JSON.stringify(values.fins ?? null) !== JSON.stringify(data.fins ?? null)) return true;
        return (
            JSON.stringify(values.mcp_tool_filters ?? {}) !==
            JSON.stringify(data.mcp_tool_filters ?? {})
        );
    }, [values, data, spec, propertyNames]);

    const handleSave = async () => {
        if (!spec) return;
        handleSaveNodeData({
            ...data,
            ...(values as Partial<FlowNodeData>),
        });
        setOpen(false);
        await saveWorkflow();
    };

    const handleOpenChange = (newOpen: boolean) => {
        if (newOpen && spec) setValues(seed());
        setOpen(newOpen);
    };

    useEffect(() => {
        if (open && spec) setValues(seed());
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [data, open]);

    // ── Render ──────────────────────────────────────────────────────────
    const styleVariant =
        STYLE_VARIANT_BY_SPEC[type] ??
        (spec?.category === "integration" ? "integration" : "agent");
    const handles =
        HANDLES_BY_SPEC[type] ??
        (spec?.category === "integration"
            ? { source: false, target: false }
            : { source: true, target: true });
    const { langue } = useLangue();
    const badge = getBadgeForSpec(spec, styleVariant, langue);
    const Icon = styleVariant === "start" ? Play : styleVariant === "agent" ? Square : styleVariant === "end" ? Flag : spec ? resolveIcon(spec.icon) : Circle;

    const fallbackTitle = spec?.display_name ?? "Node";

    // ── [.mark] La fenêtre du nœud, à onglets par sujet (E15) ─────────────
    // Chaque onglet n'existe que si le type de nœud porte des champs ou des blocs de ce sujet.
    const fenetre = (() => {
        if (!open || !spec) return null;
        const masque = proprietesMasquees(type, { estPrincipal, fins: values.fins });
        const contexte = {
            tools: tools ?? [],
            documents: documents ?? [],
            recordings: recordings ?? [],
            champsFiche: champsFiche ?? [],
            conditionsDeChamps: values.conditions_de_champs as ConditionDeChamp[] | undefined,
            onConditionsDeChampsChange: (next: ConditionDeChamp[] | undefined) =>
                setValues((prev) => ({ ...prev, conditions_de_champs: next })),
            // [.mark] Lot 8 : les outils rattachés à l'étape (pour « pas dans l'étape ») et la correction en un clic. Le nœud global n'est
            // pas une étape : un outil qu'il cite n'est pas contrôlé ici (le contrôle de publication le juge).
            etape:
                type === "globalNode"
                    ? null
                    : {
                          outils: Array.isArray(values.tool_uuids) ? (values.tool_uuids as string[]) : [],
                          rattacher: (uuid: string) =>
                              setValues((prev) => {
                                  const actuels = Array.isArray(prev.tool_uuids) ? (prev.tool_uuids as string[]) : [];
                                  return actuels.includes(uuid) ? prev : { ...prev, tool_uuids: [...actuels, uuid] };
                              }),
                      },
            mcpToolFilters: (values.mcp_tool_filters as Record<string, string[]> | undefined) ?? {},
            onMcpToolFiltersChange: (next: Record<string, string[]>) =>
                setValues((prev) => ({
                    ...prev,
                    mcp_tool_filters: Object.keys(next).length > 0 ? next : undefined,
                })),
        };
        const formulaire = (noms: string[]) => (
            <NodeEditForm spec={spec} values={values} onChange={setValues} masquer={masque} seulement={noms} context={contexte} />
        );
        const visibles = spec.properties
            .filter((p) => !masque.includes(p.name) && evaluateDisplayOptions(p.display_options, values))
            .map((p) => p.name);
        const outilsDeLEtape = ((values.tool_uuids as string[] | undefined) ?? []).length > 0;
        const etapeAgit = type === "agentNode" || type === "startCall";

        // Les blocs .mark rangés par sujet : mêmes conditions qu'avant, seule leur place change.
        const blocs: Partial<Record<SectionNoeud, ReactNode[]>> = {};
        const poser = (section: SectionNoeud, bloc: ReactNode) => {
            (blocs[section] ??= []).push(bloc);
        };
        if (etapeAgit) {
            poser(
                "agents",
                <BriqueAgent
                    key="brique"
                    outilsUuids={(values.tool_uuids as string[] | undefined) ?? []}
                    onChange={(uuids) => setValues((prev) => ({ ...prev, tool_uuids: uuids.length > 0 ? uuids : undefined }))}
                />,
            );
        }
        if (type === "agentNode" && typeof agentPrincipalId === "number") {
            poser(
                "agents",
                <RetourAuPrincipal
                    key="retour"
                    agentPrincipalId={agentPrincipalId}
                    coche={values.retour_au_principal === true}
                    onChange={(coche) => setValues((prev) => ({ ...prev, retour_au_principal: coche ? true : undefined }))}
                />,
            );
        }
        if (type === "agentNode" && estPrincipal) {
            poser(
                "agents",
                <EtapeDeRetour
                    key="etape-retour"
                    coche={values.etape_de_retour === true}
                    onChange={(coche) => setValues((prev) => ({ ...prev, etape_de_retour: coche ? true : undefined }))}
                />,
            );
        }
        if (etapeAgit && travailActif) {
            poser(
                "outils",
                <TravailDeFond
                    key="travail"
                    coche={values.travail_de_fond === true}
                    onChange={(coche) => setValues((prev) => ({ ...prev, travail_de_fond: coche ? true : undefined }))}
                />,
            );
        }
        if (etapeAgit && (outilsDeLEtape || (travailActif && values.travail_de_fond === true) || (type === "startCall" && agentAgit))) {
            poser(
                "garde",
                <VeriteDesActions
                    key="verite"
                    coche={caseCochee(values.verite_des_actions, etapeEcrit)}
                    onChange={(coche) => setValues((prev) => ({ ...prev, verite_des_actions: valeurAEcrire(coche, etapeEcrit) }))}
                />,
            );
        }
        if (etapeAgit && (outilsDeLEtape || (travailActif && values.travail_de_fond === true))) {
            poser(
                "garde",
                <DeclenchementDeLAction
                    key="declenchement"
                    position={positionLue(values.declenchement_de_l_action)}
                    demandeType={typeof values.demande_type === "string" ? values.demande_type : ""}
                    automatiquePossible={travailActif === true && values.travail_de_fond === true}
                    champsDeclares={String(values.champs_etape ?? "").trim() !== ""}
                    onChange={(position) => setValues((prev) => ({ ...prev, declenchement_de_l_action: positionEcrite(position) }))}
                    onDemandeTypeChange={(texte) =>
                        setValues((prev) => ({ ...prev, demande_type: texte.trim() === "" ? undefined : texte }))
                    }
                />,
            );
        }
        if (etapeAgit) {
            poser(
                "phrases",
                <PhrasesDeLEtape key="phrases-etape" etapeId={id} etapeNom={typeof values.name === "string" ? values.name : data.name ?? ""} />,
            );
        }
        if (type === "endCall") {
            poser(
                "phrases",
                <PhrasesDeFin
                    key="phrases-fin"
                    fins={values.fins as FinFigee[] | undefined}
                    champsFiche={champsFiche ?? []}
                    onChange={(fins) => setValues((prev) => ({ ...prev, fins }))}
                />,
            );
        }
        if (type === "startCall") {
            poser("avant", <OrdreDInjection key="ordre-d-injection" />);
        }
        if (type === "trigger") {
            poser("requete", <TriggerWebhookUrls key="urls" endpoints={buildTriggerEndpoints(data.trigger_path, webhookBaseUrl)} />);
        }

        const sections = sectionsAMontrer(visibles, Object.keys(blocs) as SectionNoeud[]).map((section) => {
            const noms = proprietesDeLaSection(visibles, section);
            return {
                id: section,
                contenu: (
                    <>
                        {noms.length > 0 && formulaire(noms)}
                        {blocs[section]}
                    </>
                ),
            };
        });
        return (
            <OngletsNoeud sections={sections} />
        );
    })();

    return (
        <>
            <NodeContent
                selected={selected}
                invalid={data.invalid}
                selected_through_edge={data.selected_through_edge}
                hovered_through_edge={data.hovered_through_edge}
                runtimeActive={data.runtime_active}
                title={data.name || fallbackTitle}
                icon={<Icon />}
                badgeLabel={badge.label}
                hasSourceHandle={handles.source}
                hasTargetHandle={handles.target}
                onDoubleClick={() => setOpen(true)}
                onMouseEnter={entrerSurvol}
                onMouseLeave={sortirSurvol}
                statistique={data.stats_part == null ? undefined : `${data.stats_part} %`}
            >
                {spec && (
                    <CanvasPreview
                        spec={spec}
                        data={data}
                        onCopyTrigger={handleCopyTrigger}
                        triggerCopied={triggerCopied}
                        onStaleTools={handleStaleTools}
                        onStaleDocuments={handleStaleDocuments}
                    />
                )}
            </NodeContent>

            {/* [.mark] Partie 3, sous-lot 20 : la barre au survol (modifier, dupliquer, relier, supprimer confirmé). */}
            <BarreAuSurvol
                visible={selected || survol}
                nom={String(data.name || fallbackTitle)}
                peutDupliquer={type !== "startCall" && spec?.graph_constraints?.max_instances == null}
                peutSupprimer={type !== "startCall"}
                lectureSeule={lectureSeule}
                onModifier={() => setOpen(true)}
                onDupliquer={dupliquerLEtape}
                onRelier={() =>
                    notifier.information({
                        fr: "Tirez depuis le point sous l'étape jusqu'à une autre étape.",
                        en: "Drag from the dot under the step to another step.",
                    })
                }
                onSupprimer={handleDeleteNode}
                onEntrer={entrerSurvol}
                onSortir={sortirSurvol}
            />

            <NodeEditDialog
                open={open}
                onOpenChange={handleOpenChange}
                nodeData={data}
                title={data.name || fallbackTitle}
                onSave={handleSave}
                isDirty={isDirty}
                typeLabel={badge.label}
                nom={String(values.name ?? data.name ?? "")}
                onNomChange={spec?.properties.some((p) => p.name === PROPRIETE_DU_NOM) ? (nom) => setValues((prev) => ({ ...prev, name: nom })) : undefined}
                onDemanderAuBuilder={() => {
                    useBuilderEcran.getState().ouvrir();
                    useBuilderEcran.getState().citer({ id, nom: String(values.name ?? data.name ?? id) });
                    setOpen(false);
                }}
            >
                {open && spec && fenetre}
            </NodeEditDialog>
        </>
    );
});

GenericNode.displayName = "GenericNode";
