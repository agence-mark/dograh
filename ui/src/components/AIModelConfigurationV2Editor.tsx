"use client";

import { Info } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";

import type {
    ModelConfigurationPricingResponse,
    OrganizationAiModelConfigurationV2,
} from "@/client/types.gen";
import {
    type ProviderSchema,
    type ServiceConfigurationDefaults,
    ServiceConfigurationForm,
    type ServiceSegment,
} from "@/components/ServiceConfigurationForm";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

// [.mark] U1: the « Dograh-managed » mode is gone (credits and service keys of the upstream cloud). A saved
// configuration in that mode opens on BYOK.
type ModelMode = "realtime" | "byok";

interface DograhDefaults {
    voices: string[];
    allow_custom_input?: boolean;
    speeds: number[];
    speed_range?: {
        min: number;
        max: number;
        step?: number;
    };
    languages: string[];
    // Languages covered by the "multi" (Multilingual / Auto-detect) option.
    multilingual_languages?: string[];
    defaults: {
        voice: string;
        speed: number;
        language: string;
    };
}

export interface ModelConfigurationDefaultsV2 {
    dograh: DograhDefaults;
    byok: {
        pipeline: ServiceConfigurationDefaults;
        realtime: {
            realtime: Record<string, ProviderSchema>;
            llm: Record<string, ProviderSchema>;
            embeddings: Record<string, ProviderSchema>;
            default_providers: ServiceConfigurationDefaults["default_providers"];
        };
    };
}

interface AIModelConfigurationV2EditorProps {
    defaults: ModelConfigurationDefaultsV2;
    configuration?: OrganizationAiModelConfigurationV2 | Record<string, unknown> | null;
    effectiveConfiguration?: Record<string, unknown> | null;
    /** No longer shown (U1: Dograh's « usage pricing » is gone); callers still pass it. */
    pricing?: ModelConfigurationPricingResponse | null;
    onSave: (configuration: OrganizationAiModelConfigurationV2) => Promise<void>;
    submitLabel?: string;
    /** [.mark] Lot 3 (D7): the voice is read only, with this note (see ServiceConfigurationForm). */
    voixVerrouillee?: ReactNode;
}

export function asRecord(value: unknown): Record<string, unknown> | null {
    return value && typeof value === "object" && !Array.isArray(value)
        ? value as Record<string, unknown>
        : null;
}

function isDograhEffectiveConfig(config: Record<string, unknown> | null | undefined): boolean {
    if (!config || config.is_realtime) return false;
    const llm = asRecord(config.llm);
    const tts = asRecord(config.tts);
    const stt = asRecord(config.stt);
    return llm?.provider === "dograh" && tts?.provider === "dograh" && stt?.provider === "dograh";
}

export function byokDefaults(defaults: ModelConfigurationDefaultsV2): ServiceConfigurationDefaults {
    return {
        llm: defaults.byok.pipeline.llm,
        tts: defaults.byok.pipeline.tts,
        stt: defaults.byok.pipeline.stt,
        embeddings: defaults.byok.pipeline.embeddings,
        realtime: defaults.byok.realtime.realtime,
        default_providers: defaults.byok.pipeline.default_providers,
    };
}

function byokConfigToLegacyShape(config: Record<string, unknown> | null): Record<string, unknown> | null {
    if (!config || config.mode !== "byok") return null;
    const byok = asRecord(config.byok);
    if (!byok) return null;

    if (byok.mode === "realtime") {
        const realtime = asRecord(byok.realtime);
        return {
            is_realtime: true,
            realtime: realtime?.realtime,
            llm: realtime?.llm,
            embeddings: realtime?.embeddings,
        };
    }

    const pipeline = asRecord(byok.pipeline);
    return {
        is_realtime: false,
        llm: pipeline?.llm,
        tts: pipeline?.tts,
        stt: pipeline?.stt,
        embeddings: pipeline?.embeddings,
    };
}

function effectiveConfigToLegacyShape(config: Record<string, unknown> | null): Record<string, unknown> | null {
    if (!config) return null;
    return {
        is_realtime: Boolean(config.is_realtime),
        llm: config.llm,
        tts: config.tts,
        stt: config.stt,
        realtime: config.realtime,
        embeddings: config.embeddings,
    };
}

function emptyByokInitialConfig(isRealtime: boolean): Record<string, unknown> {
    return {
        is_realtime: isRealtime,
    };
}

// The v2 editor surfaces realtime ("Speech to Speech") and pipeline (BYOK) as
// separate tabs, so each tab gets its own initial config. A tab is pre-filled
// only when the saved (or effective) configuration matches that tab's mode;
// otherwise it starts empty so the other tab's data does not leak across.
export function getByokInitialConfig(
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
    wantRealtime: boolean,
): Record<string, unknown> {
    const matchesTab = (config: Record<string, unknown> | null) =>
        config ? Boolean(config.is_realtime) === wantRealtime : false;

    const byokConfiguration = byokConfigToLegacyShape(configuration);
    if (byokConfiguration) {
        return matchesTab(byokConfiguration) ? byokConfiguration : emptyByokInitialConfig(wantRealtime);
    }

    if (configuration?.mode === "dograh" || isDograhEffectiveConfig(effectiveConfiguration)) {
        return emptyByokInitialConfig(wantRealtime);
    }

    const effective = effectiveConfigToLegacyShape(effectiveConfiguration);
    return matchesTab(effective) ? (effective as Record<string, unknown>) : emptyByokInitialConfig(wantRealtime);
}

export function preferredMode(
    configuration: Record<string, unknown> | null,
    effectiveConfiguration: Record<string, unknown> | null,
): ModelMode {
    if (configuration?.mode === "byok") {
        return asRecord(configuration.byok)?.mode === "realtime" ? "realtime" : "byok";
    }
    return Boolean(effectiveConfiguration?.is_realtime) ? "realtime" : "byok";
}

export function hasRequiredApiKey(
    service: ServiceSegment,
    serviceConfiguration: Record<string, unknown>,
    defaults: ServiceConfigurationDefaults,
): boolean {
    const provider = serviceConfiguration.provider as string | undefined;
    if (!provider) return false;
    const providerSchema = service === "realtime"
        ? defaults.realtime?.[provider]
        : defaults[service as "llm" | "tts" | "stt" | "embeddings"]?.[provider];
    const requiresApiKey = providerSchema?.required?.includes("api_key") ?? false;
    if (!requiresApiKey) return true;

    const apiKey = serviceConfiguration.api_key;
    if (Array.isArray(apiKey)) {
        return apiKey.some((key) => typeof key === "string" && key.trim().length > 0);
    }
    return typeof apiKey === "string" && apiKey.trim().length > 0;
}

function requireByokService(
    config: Record<string, unknown>,
    service: ServiceSegment,
    defaults: ServiceConfigurationDefaults,
): Record<string, unknown> {
    const serviceConfiguration = asRecord(config[service]);
    if (
        !serviceConfiguration
        || !serviceConfiguration.provider
        || serviceConfiguration.provider === "dograh"
        || !hasRequiredApiKey(service, serviceConfiguration, defaults)
    ) {
        throw new Error(`${service} configuration is required`);
    }
    return serviceConfiguration;
}

function optionalByokService(config: Record<string, unknown>, service: ServiceSegment): Record<string, unknown> | undefined {
    const serviceConfiguration = asRecord(config[service]);
    if (!serviceConfiguration?.provider || serviceConfiguration.provider === "dograh") return undefined;
    return serviceConfiguration;
}

function ThirdPartyProviderNotice() {
    return (
        <div className="mt-4 flex gap-3 rounded-md bg-muted px-4 py-3 text-sm text-foreground">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            <div>
                <p className="font-medium">Third-party provider data notice</p>
                <p className="mt-1 leading-6">
                    Dograh sends data required by the selected model service. This may include prompts,
                    transcripts, audio, generated text, tool data, and request metadata depending on the
                    provider and service type. Review the provider&apos;s data and retention policies before
                    using sensitive data.
                </p>
            </div>
        </div>
    );
}

export function AIModelConfigurationV2Editor({
    defaults,
    configuration,
    effectiveConfiguration,
    onSave,
    submitLabel = "Save Configuration",
    voixVerrouillee,
}: AIModelConfigurationV2EditorProps) {
    const defaultsForByok = useMemo(() => byokDefaults(defaults), [defaults]);
    const [mode, setMode] = useState<ModelMode>("byok");
    const [realtimeInitialConfig, setRealtimeInitialConfig] = useState<Record<string, unknown> | null>(null);
    const [pipelineInitialConfig, setPipelineInitialConfig] = useState<Record<string, unknown> | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const rawConfiguration = asRecord(configuration);
        const rawEffectiveConfiguration = asRecord(effectiveConfiguration);
        setMode(preferredMode(rawConfiguration, rawEffectiveConfiguration));
        setRealtimeInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, true));
        setPipelineInitialConfig(getByokInitialConfig(rawConfiguration, rawEffectiveConfiguration, false));
    }, [configuration, effectiveConfiguration]);

    const saveByokConfiguration = async (config: Record<string, unknown>) => {
        setError(null);
        const isRealtime = Boolean(config.is_realtime);
        const llm = requireByokService(config, "llm", defaultsForByok);
        const embeddings = optionalByokService(config, "embeddings");
        const body: OrganizationAiModelConfigurationV2 = {
            version: 2,
            mode: "byok",
            byok: isRealtime
                ? {
                    mode: "realtime",
                    realtime: {
                        realtime: requireByokService(config, "realtime", defaultsForByok) as never,
                        llm: llm as never,
                        ...(embeddings ? { embeddings: embeddings as never } : {}),
                    },
                }
                : {
                    mode: "pipeline",
                    pipeline: {
                        llm: llm as never,
                        tts: requireByokService(config, "tts", defaultsForByok) as never,
                        stt: requireByokService(config, "stt", defaultsForByok) as never,
                        ...(embeddings ? { embeddings: embeddings as never } : {}),
                    },
                },
        };

        await onSave(body);
    };

    return (
        <div className="space-y-6">
            {error && (
                <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                    {error}
                </div>
            )}

            <Tabs value={mode} onValueChange={(value) => setMode(value as ModelMode)} className="space-y-6">
                <TabsList className="grid w-full grid-cols-2">
                    <TabsTrigger value="realtime">Speech to Speech</TabsTrigger>
                    <TabsTrigger value="byok">BYOK</TabsTrigger>
                </TabsList>

                <TabsContent value="realtime" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        A single speech-to-speech model handles the conversation in realtime (no separate transcriber or voice). An LLM is still required for variable extraction and QA.
                    </p>
                    <ServiceConfigurationForm
                        key={`realtime-${JSON.stringify(realtimeInitialConfig)}`}
                        mode="global"
                        forceRealtime
                        configurationDefaults={defaultsForByok}
                        initialConfig={realtimeInitialConfig}
                        submitLabel={submitLabel}
                        onSave={saveByokConfiguration}
                        voixVerrouillee={voixVerrouillee}
                    />
                    <ThirdPartyProviderNotice />
                </TabsContent>

                <TabsContent value="byok" className="mt-0">
                    <p className="mb-4 text-sm text-muted-foreground">
                        Configure separate transcriber, LLM, and voice providers using your own API keys. An embeddings model can also be configured for knowledge retrieval.
                    </p>
                    <ServiceConfigurationForm
                        key={`byok-${JSON.stringify(pipelineInitialConfig)}`}
                        mode="global"
                        forceRealtime={false}
                        configurationDefaults={defaultsForByok}
                        initialConfig={pipelineInitialConfig}
                        submitLabel={submitLabel}
                        onSave={saveByokConfiguration}
                        voixVerrouillee={voixVerrouillee}
                    />
                    <ThirdPartyProviderNotice />
                </TabsContent>
            </Tabs>
        </div>
    );
}
