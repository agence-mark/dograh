"use client";

import { ExternalLink, Plus, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";

import { getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet } from '@/client/sdk.gen';
import { ChampEtiquettes } from "@/components/mark/ChampEtiquettes";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { VoiceSelector } from "@/components/VoiceSelector";
import { LANGUAGE_DISPLAY_NAMES } from "@/constants/languages";
import { useUserConfig } from "@/context/UserConfigContext";
import type { ModelOverrides } from "@/types/workflow-configurations";

export type ServiceSegment = "llm" | "tts" | "stt" | "embeddings" | "realtime";

interface SchemaProperty {
    type?: string;
    // An optional field (`x | None` in Pydantic) carries `default: null`, which
    // is not a value to put in an input — see the reset() below.
    // [.mark] string[] : une liste peut porter un defaut (ex. [] ou une liste
    // de termes), et il doit arriver au champ a etiquettes tel quel.
    default?: string | number | boolean | string[] | null;
    anyOf?: SchemaProperty[];
    minimum?: number;
    maximum?: number;
    enum?: string[];
    examples?: string[];
    model_options?: Record<string, string[]>;
    allow_custom_input?: boolean;
    $ref?: string;
    description?: string;
    format?: string;
    multiline?: boolean;
    docs_url?: string;
    // [.mark] The models that accept this setting. Absent = every model.
    models?: string[];
    // [.mark] The models that do NOT accept it — everything else does.
    // ⛔ The two are not interchangeable: a white list stops at the models
    // the dropdown happens to offer, and the model field takes free input.
    // A setting that belongs to every model EXCEPT one family has to be
    // written as an exclusion, or a client pinned to an older model loses it.
    hidden_for_models?: string[];
    // [.mark] Shown, never editable. ⛔ The real lock is server-side; this
    // only stops the screen from suggesting the value is a choice.
    readonly?: boolean;
}

export interface ProviderSchema {
    title?: string;
    description?: string;
    provider_docs_url?: string;
    properties: Record<string, SchemaProperty>;
    required?: string[];
    $defs?: Record<string, SchemaProperty>;
    [key: string]: unknown;
}

interface FormValues {
    // [.mark] string[] : une liste a etiquettes (redact, replace, keywords...).
    [key: string]: string | number | boolean | string[];
}

export interface ServiceConfigurationDefaults {
    llm: Record<string, ProviderSchema>;
    tts: Record<string, ProviderSchema>;
    stt: Record<string, ProviderSchema>;
    embeddings: Record<string, ProviderSchema>;
    realtime?: Record<string, ProviderSchema>;
    default_providers: Partial<Record<ServiceSegment, string>>;
}

const STANDARD_TABS: { key: ServiceSegment; label: string }[] = [
    { key: "llm", label: "LLM" },
    { key: "tts", label: "Voice" },
    { key: "stt", label: "Transcriber" },
    { key: "embeddings", label: "Embedding" },
];

const REALTIME_TABS: { key: ServiceSegment; label: string }[] = [
    { key: "realtime", label: "Realtime Model" },
    { key: "llm", label: "LLM" },
    { key: "embeddings", label: "Embedding" },
];

const OVERRIDE_STANDARD_TABS: { key: ServiceSegment; label: string }[] = [
    { key: "llm", label: "LLM" },
    { key: "tts", label: "Voice" },
    { key: "stt", label: "Transcriber" },
];

const OVERRIDE_REALTIME_TABS: { key: ServiceSegment; label: string }[] = [
    { key: "realtime", label: "Realtime Model" },
    { key: "llm", label: "LLM" },
];

// Display names for Sarvam voices
const VOICE_DISPLAY_NAMES: Record<string, string> = {
    "anushka": "Anushka (Female)",
    "manisha": "Manisha (Female)",
    "vidya": "Vidya (Female)",
    "arya": "Arya (Female)",
    "abhilash": "Abhilash (Male)",
    "karun": "Karun (Male)",
    "hitesh": "Hitesh (Male)",
};

export interface ServiceConfigurationFormProps {
    mode: 'global' | 'override';
    currentOverrides?: ModelOverrides;
    onSave: (config: Record<string, unknown>) => Promise<void>;
    /** Text for the submit button. Defaults to "Save Configuration". */
    submitLabel?: string;
    configurationDefaults?: ServiceConfigurationDefaults | null;
    initialConfig?: Record<string, unknown> | null;
    /**
     * When set, locks the realtime/pipeline mode to this value and hides the
     * in-form toggle. The v2 editor uses this to surface realtime
     * ("Speech to Speech") and pipeline (BYOK) as separate top-level tabs.
     * Leave undefined to keep the user-controllable toggle (legacy + overrides).
     */
    forceRealtime?: boolean;
}

function getProviderDisplayName(
    provider: string | undefined,
    providerSchema: ProviderSchema | undefined,
): string | undefined {
    if (!provider) return provider;
    return providerSchema?.title || provider;
}

function getGlobalSummary(
    config: Record<string, unknown> | null | undefined,
    providerSchema: ProviderSchema | undefined,
): string {
    if (!config) return "Not configured";
    const provider = config.provider as string | undefined;
    const model = config.model as string | undefined;
    if (!provider) return "Not configured";
    const providerLabel = getProviderDisplayName(provider, providerSchema);
    return model ? `${providerLabel} / ${model}` : providerLabel || provider;
}

function getSchemaDropdownOptions(
    schema: SchemaProperty | undefined,
    modelValue?: string,
): string[] | undefined {
    let dropdownOptions = schema?.enum || schema?.examples;

    if (schema?.model_options && modelValue && schema.model_options[modelValue]) {
        dropdownOptions = schema.model_options[modelValue];
    }

    return dropdownOptions;
}

// An optional field carries `default: null` in the schema, and a stored one
// comes back as null too. Handing null to an input makes React drop it to
// uncontrolled; "" is what an empty field looks like in the DOM.
function emptyIfNull(value: unknown): string | number | boolean | string[] {
    // [.mark] string[] passes through untouched: a list loaded from the saved
    // configuration has to reach the tag field as a list, not as a string.
    return value === null || value === undefined ? "" : (value as string | number | boolean | string[]);
}

function isNumeric(schema: SchemaProperty | undefined): boolean {
    return schema?.type === "number" || schema?.type === "integer";
}

function isArray(schema: SchemaProperty | undefined): boolean {
    return schema?.type === "array";
}

// [.mark] A list of strings, required (`list[str]`) or optional
// (`list[str] | None`, an anyOf). Without this the field falls through to the
// final branch and renders as a free text box, where the client has to guess
// the separator — a guess that is wrong for values containing one.
function getArraySchema(schema: SchemaProperty | undefined): SchemaProperty | undefined {
    if (isArray(schema)) return schema;
    return schema?.anyOf?.find(option => isArray(option));
}

function isBoolean(schema: SchemaProperty | undefined): boolean {
    return schema?.type === "boolean";
}

// [.mark] A boolean, required (`bool`) or optional (`bool | None`, which
// Pydantic writes as an anyOf). Without this the field falls through to the
// final branch and renders as a FREE TEXT BOX: the client types "true" by
// hand, or "vrai", and the API receives a string where it expects a boolean.
// ⛔ Nothing here is specific to one provider — `return_timestamps` on
// HuggingFace is already in that state upstream.
function getBooleanSchema(schema: SchemaProperty | undefined): SchemaProperty | undefined {
    if (isBoolean(schema)) return schema;
    return schema?.anyOf?.find(option => isBoolean(option));
}

function getNumberSchema(schema: SchemaProperty | undefined): SchemaProperty | undefined {
    // "integer" counts too: an optional whole number (max_tokens, seed) is
    // typed `integer | null` by Pydantic. Without it the field falls back to a
    // text input, which loses the min/max hints AND the empty-string-to-
    // undefined conversion below — an untouched optional field would then be
    // submitted as "" and rejected by the API.
    if (isNumeric(schema)) return schema;
    return schema?.anyOf?.find(option => isNumeric(option));
}

export function ServiceConfigurationForm({
    mode,
    currentOverrides,
    onSave,
    submitLabel,
    configurationDefaults,
    initialConfig,
    forceRealtime,
}: ServiceConfigurationFormProps) {
    const [apiError, setApiError] = useState<string | null>(null);
    const [isSaving, setIsSaving] = useState(false);
    const [isRealtime, setIsRealtime] = useState(forceRealtime ?? false);
    const { userConfig } = useUserConfig();
    const [schemas, setSchemas] = useState<Record<ServiceSegment, Record<string, ProviderSchema>>>({
        llm: {},
        tts: {},
        stt: {},
        embeddings: {},
        realtime: {},
    });
    const [serviceProviders, setServiceProviders] = useState<Record<ServiceSegment, string>>({
        llm: "",
        tts: "",
        stt: "",
        embeddings: "",
        realtime: "",
    });
    const [apiKeys, setApiKeys] = useState<Record<ServiceSegment, string[]>>({
        llm: [""],
        tts: [""],
        stt: [""],
        embeddings: [""],
        realtime: [""],
    });
    const [isCustomInput, setIsCustomInput] = useState<Record<string, boolean>>({});

    // Override-specific state: which services have the override toggle enabled
    const [enabledOverrides, setEnabledOverrides] = useState<Record<string, boolean>>({
        llm: false,
        tts: false,
        stt: false,
        realtime: false,
    });

    const {
        register,
        handleSubmit,
        formState: { },
        reset,
        getValues,
        setValue,
        watch
    } = useForm();

    // Build effective config source: overlay overrides onto global config
    const configSource = useMemo(() => {
        const baseConfig = initialConfig ?? userConfig;
        if (mode === 'global' || !currentOverrides) return baseConfig;
        // Merge overrides onto global config for form initialization
        const merged = { ...baseConfig } as Record<string, unknown>;
        const overrideServices: (keyof ModelOverrides)[] = ["llm", "tts", "stt", "realtime"];
        for (const svc of overrideServices) {
            if (svc === "is_realtime") continue;
            const overrideVal = currentOverrides[svc];
            if (overrideVal && typeof overrideVal === "object") {
                const globalVal = (baseConfig as Record<string, unknown> | null)?.[svc] as Record<string, unknown> | undefined;
                merged[svc] = { ...globalVal, ...overrideVal };
            }
        }
        if (currentOverrides.is_realtime !== undefined) {
            merged.is_realtime = currentOverrides.is_realtime;
        }
        return merged as typeof userConfig;
    }, [mode, userConfig, currentOverrides, initialConfig]);

    useEffect(() => {
        const fetchConfigurations = async () => {
            let defaultsData = configurationDefaults;
            if (!defaultsData) {
                const response = await getDefaultConfigurationsApiV1UserConfigurationsDefaultsGet();
                if (!response.data) {
                    console.error("Failed to fetch configurations");
                    return;
                }
                defaultsData = response.data as unknown as ServiceConfigurationDefaults;
            }

            const realtimeSchemas = (defaultsData.realtime || {}) as Record<string, ProviderSchema>;
            const pickDefaultProvider = (
                service: ServiceSegment,
                schemaMap: Record<string, ProviderSchema>,
            ) => {
                const preferred = defaultsData.default_providers?.[service];
                if (preferred && schemaMap[preferred]) return preferred;
                return Object.keys(schemaMap)[0] || "";
            };

            setSchemas({
                llm: defaultsData.llm,
                tts: defaultsData.tts,
                stt: defaultsData.stt,
                embeddings: defaultsData.embeddings,
                realtime: realtimeSchemas,
            });

            // Restore realtime toggle (skip when the parent locks the mode)
            const configData = configSource as Record<string, unknown> | null;
            if (forceRealtime === undefined && configData?.is_realtime) {
                setIsRealtime(true);
            }

            const defaultValues: Record<string, string | number | boolean | string[]> = {};
            const selectedProviders: Record<ServiceSegment, string> = {
                llm: pickDefaultProvider("llm", defaultsData.llm),
                tts: pickDefaultProvider("tts", defaultsData.tts),
                stt: pickDefaultProvider("stt", defaultsData.stt),
                embeddings: pickDefaultProvider("embeddings", defaultsData.embeddings),
                realtime: "",
            };

            const realtimeProviderKeys = Object.keys(realtimeSchemas);
            if (realtimeProviderKeys.length > 0) {
                selectedProviders.realtime = realtimeProviderKeys[0];
            }

            const loadedApiKeys: Record<ServiceSegment, string[]> = {
                llm: [""],
                tts: [""],
                stt: [""],
                embeddings: [""],
                realtime: [""],
            };

            const setServicePropertyValues = (service: ServiceSegment) => {
                const src = service === "realtime"
                    ? (configSource as Record<string, unknown> | null)?.realtime as Record<string, unknown> | undefined
                    : (configSource as Record<string, unknown> | null)?.[service] as Record<string, unknown> | undefined;

                const schemaSource = service === "realtime"
                    ? realtimeSchemas
                    : defaultsData[service as "llm" | "tts" | "stt" | "embeddings"] as Record<string, ProviderSchema> | undefined;

                if (src?.provider) {
                    Object.entries(src).forEach(([field, value]) => {
                        if (field === "api_key") {
                            if (mode === 'override') {
                                // In override mode, only load API keys from the override itself
                                const overrideVal = currentOverrides?.[service as keyof ModelOverrides];
                                const overrideApiKey = overrideVal && typeof overrideVal === "object"
                                    ? (overrideVal as Record<string, unknown>).api_key
                                    : undefined;
                                if (overrideApiKey) {
                                    loadedApiKeys[service] = Array.isArray(overrideApiKey)
                                        ? overrideApiKey as string[]
                                        : [overrideApiKey as string];
                                } else {
                                    loadedApiKeys[service] = [""];
                                }
                            } else {
                                if (Array.isArray(value)) {
                                    loadedApiKeys[service] = (value as string[]).length > 0 ? value as string[] : [""];
                                } else {
                                    loadedApiKeys[service] = value ? [value as string] : [""];
                                }
                            }
                        } else if (field !== "provider") {
                            defaultValues[`${service}_${field}`] = emptyIfNull(value);
                        }
                    });
                    selectedProviders[service] = src.provider as string;
                    const properties = schemaSource?.[selectedProviders[service]]?.properties as Record<string, SchemaProperty>;
                    if (properties) {
                        Object.entries(properties).forEach(([field, schema]) => {
                            const key = `${service}_${field}`;
                            if (field !== "provider" && field !== "api_key" && schema.default !== undefined && !(key in defaultValues)) {
                                defaultValues[key] = emptyIfNull(schema.default);
                            }
                        });
                    }
                } else {
                    const properties = schemaSource?.[selectedProviders[service]]?.properties as Record<string, SchemaProperty>;
                    if (properties) {
                        Object.entries(properties).forEach(([field, schema]) => {
                            if (field !== "provider" && schema.default !== undefined) {
                                defaultValues[`${service}_${field}`] = emptyIfNull(schema.default);
                            }
                        });
                    }
                }
            };

            setServicePropertyValues("llm");
            setServicePropertyValues("tts");
            setServicePropertyValues("stt");
            setServicePropertyValues("embeddings");
            setServicePropertyValues("realtime");

            // Detect custom inputs
            const detectedCustomInput: Record<string, boolean> = {};
            const allSchemas = { ...defaultsData, realtime: realtimeSchemas } as unknown as Record<string, Record<string, ProviderSchema>>;
            (["llm", "tts", "stt", "embeddings", "realtime"] as ServiceSegment[]).forEach(service => {
                const provider = selectedProviders[service];
                const providerSchema = allSchemas[service]?.[provider];
                if (!providerSchema) return;

                const src = service === "realtime"
                    ? (configSource as Record<string, unknown> | null)?.realtime as Record<string, unknown> | undefined
                    : (configSource as Record<string, unknown> | null)?.[service] as Record<string, unknown> | undefined;

                Object.entries(providerSchema.properties).forEach(([field, schema]) => {
                    const actualSchema = (schema as SchemaProperty).$ref && providerSchema.$defs
                        ? providerSchema.$defs[(schema as SchemaProperty).$ref!.split('/').pop() || '']
                        : schema as SchemaProperty;

                    if (!actualSchema?.allow_custom_input) return;

                    const savedValue = src?.[field] as string | undefined;
                    const modelValue = src?.model as string | undefined;
                    const dropdownOptions = getSchemaDropdownOptions(actualSchema, modelValue);
                    if (savedValue && dropdownOptions && !dropdownOptions.includes(savedValue)) {
                        detectedCustomInput[`${service}_${field}`] = true;
                    }
                });
            });

            // Initialize override toggles
            if (mode === 'override') {
                setEnabledOverrides({
                    llm: !!currentOverrides?.llm,
                    tts: !!currentOverrides?.tts,
                    stt: !!currentOverrides?.stt,
                    realtime: !!currentOverrides?.realtime,
                });
            }

            reset(defaultValues);
            setApiKeys(loadedApiKeys);
            setServiceProviders(selectedProviders);
            setIsCustomInput(detectedCustomInput);
        };
        fetchConfigurations();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [reset, configSource, configurationDefaults]);

    // Reset voice when TTS model changes if the provider has model-dependent voice options
    const ttsModel = watch("tts_model");
    useEffect(() => {
        const voiceSchema = schemas?.tts?.[serviceProviders.tts]?.properties?.voice;
        const modelOptions = voiceSchema?.model_options;
        if (!modelOptions || !ttsModel) return;

        const validVoices = modelOptions[ttsModel as string];
        const currentVoice = getValues("tts_voice") as string;
        const isCustomVoice = !!isCustomInput.tts_voice;
        if (validVoices && currentVoice && !validVoices.includes(currentVoice) && !isCustomVoice) {
            setValue("tts_voice", validVoices[0], { shouldDirty: true });
        }
    }, [ttsModel, serviceProviders.tts, setValue, getValues, schemas, isCustomInput.tts_voice]);

    // Reset language when STT model changes if the provider has model-dependent language options
    const sttModel = watch("stt_model");
    useEffect(() => {
        const languageSchema = schemas?.stt?.[serviceProviders.stt]?.properties?.language;
        const modelOptions = languageSchema?.model_options;
        if (!modelOptions || !sttModel) return;

        const validLanguages = modelOptions[sttModel as string];
        const currentLanguage = getValues("stt_language") as string;
        if (validLanguages && currentLanguage && !validLanguages.includes(currentLanguage)) {
            setValue("stt_language", validLanguages[0], { shouldDirty: true });
        }
    }, [sttModel, serviceProviders.stt, setValue, getValues, schemas]);

    const handleProviderChange = (service: ServiceSegment, providerName: string) => {
        if (!providerName) return;

        const currentValues = getValues();
        const preservedValues: Record<string, string | number | boolean | string[]> = {};

        Object.keys(currentValues).forEach(key => {
            if (!key.startsWith(`${service}_`)) {
                preservedValues[key] = currentValues[key];
            }
        });

        if (schemas?.[service]?.[providerName]) {
            const providerSchema = schemas[service][providerName];
            Object.entries(providerSchema.properties).forEach(([field, schema]: [string, SchemaProperty]) => {
                if (field !== "provider" && schema.default !== undefined) {
                    preservedValues[`${service}_${field}`] = emptyIfNull(schema.default);
                }
            });
        }

        preservedValues[`${service}_provider`] = providerName;
        reset(preservedValues);
        setServiceProviders(prev => ({ ...prev, [service]: providerName }));
        setApiKeys(prev => ({ ...prev, [service]: [""] }));

        setIsCustomInput(prev => {
            const next = { ...prev };
            Object.keys(next).forEach(key => {
                if (key.startsWith(`${service}_`)) delete next[key];
            });
            return next;
        });
    };

    const buildServiceConfig = (service: ServiceSegment, data: FormValues) => {
        // [.mark] `boolean` belongs here: a switch posts a real boolean, and
        // the previous type only held because the cast below lied about it.
        const config: Record<string, string | number | boolean | string[]> = {
            provider: serviceProviders[service],
        };
        const keys = apiKeys[service].map(k => k.trim()).filter(k => k.length > 0);
        if (keys.length > 0) {
            config.api_key = mode === 'override' ? keys[0] : keys;
        }
        const schemasParFournisseur = () => schemas?.[service]?.[serviceProviders[service]];
        const properties = schemasParFournisseur()?.properties;

        // [.mark] An override must carry only what it CHANGES.
        //
        // Sending the whole block defeats the point of a per-service override
        // in miniature: an agent that changes one setting would also freeze the
        // model, the language and every other setting at their value of the
        // day, and would stop following its client from then on — silently.
        //
        // 🔑 The server already merges field by field when the provider is
        // unchanged (resolve_effective_config), so sending LESS makes the agent
        // inherit MORE. ⛔ When the provider DOES change, the server rebuilds
        // the section from the override alone, so there the whole block has to
        // go or the agent ends up with nothing but one field.
        const configDuClient = (userConfig as Record<string, unknown> | null)?.[service] as
            | Record<string, unknown>
            | undefined;
        const heriteChampParChamp =
            mode === 'override'
            && !!configDuClient
            && configDuClient.provider === serviceProviders[service];

        // [.mark] The rendering resolves $ref before reading a field's flags,
        // so the save has to resolve it too. A read-only field declared behind
        // a $ref was drawn disabled and posted anyway.
        const schemaResolu = (field: string): SchemaProperty | undefined => {
            const brut = properties?.[field];
            if (brut?.$ref) {
                const schemas = schemasParFournisseur();
                return schemas?.$defs?.[brut.$ref.split('/').pop() || ''] ?? brut;
            }
            return brut;
        };

        const valeurHeritee = (field: string): unknown => {
            // What the server would apply for this field if we said nothing:
            // the client's value, or the schema default when the client has
            // none of its own.
            if (configDuClient && field in configDuClient) return configDuClient[field];
            return properties?.[field]?.default;
        };

        const identiqueAHerite = (field: string, value: unknown): boolean => {
            const heritee = valeurHeritee(field);
            // An untouched field holds "" where the inherited value is absent.
            const vide = (v: unknown) => v === "" || v === null || v === undefined;
            if (vide(value) && vide(heritee)) return true;
            return JSON.stringify(value) === JSON.stringify(heritee);
        };
        Object.entries(data).forEach(([property, value]) => {
            if (!property.startsWith(`${service}_`)) return;
            const field = property.slice(service.length + 1);
            if (field === "api_key" || field === "provider") return;
            // An optional numeric field left empty comes back as undefined
            // (setValueAs below). Sending the key anyway would post `null` where
            // the schema expects a number or nothing at all.
            if (value === undefined) return;
            // Same rule for an optional field of any other type: a schema
            // default of null means "not set", so an empty input is left out
            // rather than posted as "". Required fields keep going through, so
            // a missing one is still refused by the API rather than silently
            // replaced by a default.
            // ⚠️ In override mode, "left out" means INHERITED from the
            // organisation, not "set to empty" — the same way an empty numeric
            // field already behaved. Forcing an empty value where the client
            // has one is no longer possible from the override screen; it stays
            // possible from the organisation screen, which replaces the whole
            // service block.
            if (value === "" && properties?.[field]?.default === null) return;
            // [.mark] A read-only field is never posted: the server imposes
            // its value whatever arrives, so storing a copy would only create
            // a second place where the truth could drift.
            if (schemaResolu(field)?.readonly) return;
            // [.mark] An override carries only what it changes, so the agent
            // keeps inheriting the rest.
            if (heriteChampParChamp && identiqueAHerite(field, value)) return;
            config[field] = value as string | number | boolean | string[];
        });
        return config;
    };

    const onSubmit = async (data: FormValues) => {
        setApiError(null);
        setIsSaving(true);

        try {
            if (mode === 'override') {
                // Build model_overrides for enabled services only
                const modelOverrides: Record<string, unknown> = {};
                const services = isRealtime ? ["realtime", "llm"] : ["llm", "tts", "stt"];
                for (const svc of services) {
                    if (enabledOverrides[svc]) {
                        modelOverrides[svc] = buildServiceConfig(svc as ServiceSegment, data);
                    }
                }
                // Include is_realtime if it differs from global
                const globalIsRealtime = !!(userConfig as Record<string, unknown> | null)?.is_realtime;
                if (isRealtime !== globalIsRealtime) {
                    modelOverrides.is_realtime = isRealtime;
                }
                await onSave({
                    model_overrides: Object.keys(modelOverrides).length > 0 ? modelOverrides : undefined,
                });
            } else {
                // Global mode: save all services
                const saveConfig: Record<string, unknown> = {
                    llm: buildServiceConfig("llm", data),
                    tts: buildServiceConfig("tts", data),
                    stt: buildServiceConfig("stt", data),
                    is_realtime: isRealtime,
                };
                if (serviceProviders.realtime) {
                    saveConfig.realtime = buildServiceConfig("realtime", data);
                }
                const embeddingsKeys = apiKeys.embeddings.map(k => k.trim()).filter(k => k.length > 0);
                if (embeddingsKeys.length > 0) {
                    saveConfig.embeddings = buildServiceConfig("embeddings", data);
                }
                await onSave(saveConfig);
            }
            setApiError(null);
        } catch (error: unknown) {
            if (error instanceof Error) {
                setApiError(error.message);
            } else {
                setApiError('An unknown error occurred');
            }
        } finally {
            setIsSaving(false);
        }
    };

    const getConfigFields = (service: ServiceSegment): string[] => {
        const currentProvider = serviceProviders[service];
        const providerSchema = schemas?.[service]?.[currentProvider];
        if (!providerSchema) return [];
        const currentModel = watch(`${service}_model`) as string | undefined;
        return Object.keys(providerSchema.properties).filter(field => {
            if (field === "provider" || field === "api_key") return false;
            const schema = providerSchema.properties[field];
            const actualSchema = schema?.$ref && providerSchema.$defs
                ? providerSchema.$defs[schema.$ref.split('/').pop() || '']
                : schema;
            // [.mark] A field can name the models that accept it. Absent means
            // every model, so no existing field changes behaviour.
            // ⛔ A setting shown, filled in, sent and ignored by the model is
            // what we ruled out for top_k. `model_options` filters the VALUES
            // of a dropdown; it cannot hide a field.
            // 🔑 Hiding is a screen decision, not a data decision: the value
            // stays in the form and is still saved, so switching back to the
            // model that accepts it does not silently reset it.
            const caches = actualSchema?.hidden_for_models;
            if (caches && currentModel && caches.includes(currentModel)) return false;
            const models = actualSchema?.models;
            if (!models || models.length === 0) return true;
            if (!currentModel) return true;
            return models.includes(currentModel);
        });
    };

    const renderServiceFields = (service: ServiceSegment) => {
        const currentProvider = serviceProviders[service];
        const providerSchema = schemas?.[service]?.[currentProvider];
        const availableProviders = schemas?.[service] ? Object.keys(schemas[service]) : [];
        const configFields = getConfigFields(service);

        return (
            <div className="space-y-6">
                <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                        <Label>Provider</Label>
                        <Select
                            value={currentProvider}
                            onValueChange={(providerName) => {
                                handleProviderChange(service, providerName);
                            }}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select provider" />
                            </SelectTrigger>
                            <SelectContent>
                                {availableProviders.map((provider) => (
                                    <SelectItem key={provider} value={provider}>
                                        {getProviderDisplayName(provider, schemas?.[service]?.[provider])}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        {(providerSchema?.description || providerSchema?.provider_docs_url) && (
                            <p className="text-xs text-muted-foreground">
                                {providerSchema?.description}{" "}
                                {providerSchema?.provider_docs_url && (
                                    <a
                                        href={providerSchema.provider_docs_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="inline-flex items-center gap-0.5 underline"
                                    >
                                        Learn more <ExternalLink className="h-3 w-3" />
                                    </a>
                                )}
                            </p>
                        )}
                    </div>

                    {currentProvider && providerSchema && configFields[0] && (
                        <div className="space-y-2">
                            <Label className="capitalize">{configFields[0].replace(/_/g, ' ')}</Label>
                            {renderField(service, configFields[0], providerSchema)}
                        </div>
                    )}
                </div>

                {currentProvider && providerSchema && configFields.length > 1 && (
                    <div className="grid grid-cols-2 gap-4">
                        {configFields.slice(1).map((field) => {
                            const fieldSchema = providerSchema.properties[field];
                            const actualFieldSchema = fieldSchema?.$ref && providerSchema.$defs
                                ? providerSchema.$defs[fieldSchema.$ref.split('/').pop() || '']
                                : fieldSchema;
                            const fullWidth = actualFieldSchema?.multiline;
                            return (
                                <div key={field} className={`space-y-2 ${fullWidth ? "col-span-2" : ""}`}>
                                    <Label className="capitalize">{field.replace(/_/g, ' ')}</Label>
                                    {renderField(service, field, providerSchema)}
                                </div>
                            );
                        })}
                    </div>
                )}

                {currentProvider && providerSchema && providerSchema.properties.api_key && (
                    <div className="space-y-2">
                        <Label>{mode === 'override' ? 'API Key (leave empty to use global)' : 'API Key(s)'}</Label>
                        {renderFieldDescription("api_key", providerSchema)}
                        {apiKeys[service].map((key, index) => (
                            <div key={index} className="flex gap-2">
                                <Input
                                    type="text"
                                    placeholder="Enter API key"
                                    value={key}
                                    onChange={(e) => {
                                        const newKeys = [...apiKeys[service]];
                                        newKeys[index] = e.target.value;
                                        setApiKeys(prev => ({ ...prev, [service]: newKeys }));
                                    }}
                                />
                                {apiKeys[service].length > 1 && (
                                    <Button
                                        type="button"
                                        variant="ghost"
                                        size="icon"
                                        className="shrink-0"
                                        onClick={() => {
                                            setApiKeys(prev => ({
                                                ...prev,
                                                [service]: prev[service].filter((_, i) => i !== index),
                                            }));
                                        }}
                                    >
                                        <X className="h-4 w-4" />
                                    </Button>
                                )}
                            </div>
                        ))}
                        {mode !== 'override' && (
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                    setApiKeys(prev => ({
                                        ...prev,
                                        [service]: [...prev[service], ""],
                                    }));
                                }}
                            >
                                <Plus className="h-4 w-4 mr-1" /> Add API Key
                            </Button>
                        )}
                    </div>
                )}
            </div>
        );
    };

    const renderFieldDescription = (field: string, providerSchema: ProviderSchema) => {
        const schema = providerSchema.properties[field];
        if (!schema) return null;
        const actualSchema = schema.$ref && providerSchema.$defs
            ? providerSchema.$defs[schema.$ref.split('/').pop() || '']
            : schema;
        if (!actualSchema?.description && !actualSchema?.docs_url) return null;
        return (
            <p className="text-xs text-muted-foreground">
                {actualSchema?.description}{" "}
                {actualSchema?.docs_url && (
                    <a
                        href={actualSchema.docs_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-0.5 underline"
                    >
                        Supported languages <ExternalLink className="h-3 w-3" />
                    </a>
                )}
            </p>
        );
    };

    const renderField = (service: ServiceSegment, field: string, providerSchema: ProviderSchema) => {
        return (
            <>
                {renderFieldInput(service, field, providerSchema)}
                {renderFieldDescription(field, providerSchema)}
            </>
        );
    };

    const renderFieldInput = (service: ServiceSegment, field: string, providerSchema: ProviderSchema) => {
        const schema = providerSchema.properties[field];
        const actualSchema = schema.$ref && providerSchema.$defs
            ? providerSchema.$defs[schema.$ref.split('/').pop() || '']
            : schema;
        const dropdownOptions = getSchemaDropdownOptions(
            actualSchema,
            watch(`${service}_model`) as string | undefined,
        );
        const numberSchema = getNumberSchema(actualSchema);

        if (service === "tts" && field === "voice" && !actualSchema?.allow_custom_input) {
            if (!dropdownOptions) {
                return (
                    <VoiceSelector
                        provider={serviceProviders.tts}
                        value={watch(`${service}_${field}`) as string || ""}
                        onChange={(voiceId) => {
                            setValue(`${service}_${field}`, voiceId, { shouldDirty: true });
                        }}
                        model={watch("tts_model") as string || undefined}
                    />
                );
            }
        }

        // [.mark] A compliance value: shown so the pair (what we control, what
        // we do not) can be read in one place, never editable.
        // 🔴 This is NOT the lock. The factory imposes these values whatever a
        // configuration says; disabling the control only stops the screen from
        // suggesting they are a choice.
        if (actualSchema?.readonly) {
            const fieldKey = `${service}_${field}`;
            const valeur = watch(fieldKey);
            if (getBooleanSchema(actualSchema)) {
                return (
                    <div className="flex h-9 items-center">
                        <Switch id={fieldKey} checked={valeur === true} disabled />
                    </div>
                );
            }
            return <Input type="text" value={String(valeur ?? "")} readOnly disabled />;
        }

        // [.mark] A list is a tag field, not a text box: the client adds one
        // term at a time instead of guessing a separator.
        if (getArraySchema(actualSchema)) {
            const fieldKey = `${service}_${field}`;
            const valeur = watch(fieldKey);
            // An untouched optional list holds "" (see emptyIfNull).
            const valeurs = Array.isArray(valeur) ? (valeur as string[]) : [];
            return (
                <ChampEtiquettes
                    id={fieldKey}
                    valeurs={valeurs}
                    placeholder={`Enter ${field.replace(/_/g, " ")}`}
                    onChange={(nouvelles) => {
                        // ⛔ An emptied list goes back to "" and not to [],
                        // so buildServiceConfig leaves it out. Posting [] would
                        // mean "the client explicitly wants none", which is a
                        // different request from sending nothing at all.
                        setValue(fieldKey, nouvelles.length > 0 ? nouvelles : "", {
                            shouldDirty: true,
                        });
                    }}
                />
            );
        }

        // [.mark] A boolean is a switch, not a text box. Placed before the
        // dropdown branch so the declared TYPE wins over any examples someone
        // might hang on the field later.
        if (getBooleanSchema(actualSchema)) {
            const fieldKey = `${service}_${field}`;
            // An untouched optional boolean holds "" (see emptyIfNull), which
            // reads as off. ⛔ Only a real `true` turns the switch on, so a
            // stray "false" string from an older save cannot show as on.
            const coche = watch(fieldKey) === true;
            return (
                <div className="flex h-9 items-center">
                    <Switch
                        id={fieldKey}
                        checked={coche}
                        onCheckedChange={(checked) => {
                            // 🔑 A real boolean, never the string a text box
                            // would have posted. And `false` is stored as
                            // `false`, not as "": switching a setting OFF on
                            // purpose is a choice, and it must survive the
                            // "empty means inherited" rule in
                            // buildServiceConfig.
                            setValue(fieldKey, checked, { shouldDirty: true });
                        }}
                    />
                </div>
            );
        }

        if (actualSchema?.allow_custom_input && dropdownOptions && dropdownOptions.length > 0) {
            const fieldKey = `${service}_${field}`;
            const currentValue = watch(fieldKey) as string || "";
            const options = dropdownOptions;

            if (isCustomInput[fieldKey]) {
                return (
                    <div className="space-y-2">
                        <Input
                            type="text"
                            placeholder={`Enter ${field}`}
                            value={currentValue}
                            onChange={(e) => {
                                setValue(fieldKey, e.target.value, { shouldDirty: true });
                            }}
                        />
                        <div className="flex items-center space-x-2">
                            <Checkbox
                                id={`custom-input-${fieldKey}`}
                                checked={true}
                                onCheckedChange={(checked) => {
                                    setIsCustomInput(prev => ({ ...prev, [fieldKey]: checked as boolean }));
                                    if (!checked && options.length > 0) {
                                        setValue(fieldKey, options[0], { shouldDirty: true });
                                    }
                                }}
                            />
                            <Label htmlFor={`custom-input-${fieldKey}`} className="text-sm font-normal cursor-pointer">
                                Enter Custom Value
                            </Label>
                        </div>
                    </div>
                );
            }

            return (
                <div className="space-y-2">
                    <Select
                        value={currentValue}
                        onValueChange={(value) => {
                            if (!value) return;
                            setValue(fieldKey, value, { shouldDirty: true });
                        }}
                    >
                        <SelectTrigger className="w-full">
                            <SelectValue placeholder={`Select ${field}`} />
                        </SelectTrigger>
                        <SelectContent>
                            {options.map((value: string) => (
                                <SelectItem key={value} value={value}>
                                    {value}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    <div className="flex items-center space-x-2">
                        <Checkbox
                            id={`custom-input-${fieldKey}-dropdown`}
                            checked={false}
                            onCheckedChange={(checked) => {
                                setIsCustomInput(prev => ({ ...prev, [fieldKey]: checked as boolean }));
                            }}
                        />
                        <Label htmlFor={`custom-input-${fieldKey}-dropdown`} className="text-sm font-normal cursor-pointer">
                            Enter Custom Value
                        </Label>
                    </div>
                </div>
            );
        }

        if (dropdownOptions && dropdownOptions.length > 0) {
            const getDisplayName = (value: string) => {
                if (field === "language") {
                    return LANGUAGE_DISPLAY_NAMES[value] || value;
                }
                if (field === "voice") {
                    return VOICE_DISPLAY_NAMES[value] || value.charAt(0).toUpperCase() + value.slice(1);
                }
                return value;
            };

            return (
                <Select
                    value={watch(`${service}_${field}`) as string || ""}
                    onValueChange={(value) => {
                        if (!value) return;
                        setValue(`${service}_${field}`, value, { shouldDirty: true });
                    }}
                >
                    <SelectTrigger className="w-full">
                        <SelectValue placeholder={`Select ${field}`} />
                    </SelectTrigger>
                    <SelectContent>
                        {dropdownOptions.map((value: string) => (
                            <SelectItem key={value} value={value}>
                                {getDisplayName(value)}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            );
        }

        if (actualSchema?.multiline) {
            return (
                <Textarea
                    rows={6}
                    className="font-mono text-xs"
                    placeholder={`Enter ${field}`}
                    {...register(`${service}_${field}`, {
                        required: service !== "embeddings" && providerSchema.required?.includes(field),
                    })}
                />
            );
        }

        return (
            <Input
                type={numberSchema ? "number" : "text"}
                {...(numberSchema && {
                    step: "any",
                    min: numberSchema.minimum,
                    max: numberSchema.maximum,
                })}
                placeholder={`Enter ${field}`}
                {...register(`${service}_${field}`, {
                    required: service !== "embeddings" && providerSchema.required?.includes(field),
                    ...(numberSchema && {
                        setValueAs: (value: string) => value === "" ? undefined : Number(value),
                    }),
                })}
            />
        );
    };

    const handleOverrideToggle = (service: string, enabled: boolean) => {
        setEnabledOverrides(prev => ({ ...prev, [service]: enabled }));
    };

    const renderOverrideToggle = (service: ServiceSegment, label: string) => {
        const globalVal = (userConfig as Record<string, unknown> | null)?.[service] as Record<string, unknown> | null | undefined;
        const isEnabled = enabledOverrides[service];
        const globalProvider = globalVal?.provider as string | undefined;
        const globalProviderSchema = globalProvider ? schemas?.[service]?.[globalProvider] : undefined;

        return (
            <div className="flex items-center justify-between p-3 border rounded-md bg-muted/20 mb-4">
                <div className="space-y-0.5">
                    <Label htmlFor={`override-${service}`} className="text-sm cursor-pointer font-medium">
                        Override {label}
                    </Label>
                    {!isEnabled && (
                        <p className="text-xs text-muted-foreground">
                            Using global: {getGlobalSummary(globalVal, globalProviderSchema)}
                        </p>
                    )}
                </div>
                <Switch
                    id={`override-${service}`}
                    checked={isEnabled}
                    onCheckedChange={(checked) => handleOverrideToggle(service, checked)}
                />
            </div>
        );
    };

    const getVisibleTabs = () => {
        if (mode === 'override') {
            return isRealtime ? OVERRIDE_REALTIME_TABS : OVERRIDE_STANDARD_TABS;
        }
        return isRealtime ? REALTIME_TABS : STANDARD_TABS;
    };

    const visibleTabs = getVisibleTabs();
    const defaultTab = isRealtime ? "realtime" : "llm";

    return (
        <form onSubmit={handleSubmit(onSubmit)}>
            {/* Realtime toggle — hidden when the parent locks the mode (v2 tabs) */}
            {forceRealtime === undefined && (
                <div className="flex items-center justify-between mb-4 p-4 border rounded-lg">
                    <div>
                        <Label htmlFor="realtime-toggle" className="text-sm font-medium">
                            Realtime Mode
                        </Label>
                        <p className="text-xs text-muted-foreground mt-0.5">
                            Uses a single speech-to-speech model (no separate STT/TTS). An LLM is still required for variable extraction and QA.
                        </p>
                    </div>
                    <Switch
                        id="realtime-toggle"
                        checked={isRealtime}
                        onCheckedChange={setIsRealtime}
                    />
                </div>
            )}

            <Card>
                <CardContent className="pt-6">
                    <Tabs key={defaultTab} defaultValue={defaultTab} className="w-full">
                        <TabsList className="grid w-full mb-6" style={{ gridTemplateColumns: `repeat(${visibleTabs.length}, 1fr)` }}>
                            {visibleTabs.map(({ key, label }) => (
                                <TabsTrigger key={key} value={key}>
                                    {label}
                                </TabsTrigger>
                            ))}
                        </TabsList>

                        {visibleTabs.map(({ key, label }) => (
                            <TabsContent key={key} value={key} className="mt-0">
                                {mode === 'override' && renderOverrideToggle(key, label)}
                                {(mode === 'global' || enabledOverrides[key]) && renderServiceFields(key)}
                            </TabsContent>
                        ))}
                    </Tabs>
                </CardContent>
            </Card>

            {apiError && <p className="text-red-500 mt-4">{apiError}</p>}

            <Button type="submit" className="w-full mt-6" disabled={isSaving}>
                {isSaving ? "Saving..." : (submitLabel || "Save Configuration")}
            </Button>
        </form>
    );
}
