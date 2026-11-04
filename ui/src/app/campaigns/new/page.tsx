"use client";

import { ChevronDown, ChevronRight } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import type { ITimezoneOption } from 'react-timezone-select';

import {
    createCampaignApiV1CampaignCreatePost,
    getCampaignDefaultsApiV1OrganizationsCampaignDefaultsGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet
} from '@/client/sdk.gen';
import type { TelephonyConfigurationListItem, TrafficVariantRequest } from '@/client/types.gen';
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from '@/components/mark/notifications/echec-affiche';
import { FenetreLibre } from "@/components/mark/studio/fenetre-libre";
import { Info } from "@/components/mark/studio/marques";
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { UnsavedChangesProvider, useUnsavedChanges, useUnsavedChangesContext } from '@/context/UnsavedChangesContext';
import { useAuth } from '@/lib/auth';

import CampaignAdvancedSettings, { getTimezoneValue, type TimeSlot } from '../CampaignAdvancedSettings';
import CsvUploadSelector from '../CsvUploadSelector';
import CampaignsPage from '../page';
import TrafficSplitEditor, { trafficSplitError } from '../TrafficSplitEditor';

type Erreurs = Partial<Record<'nom' | 'repartition' | 'telephonie' | 'source' | 'simultanes' | 'cadence', string>>;

/** Quitter la page avec un brouillon de campagne : on prévient (le garde de l'application intercepte les liens). */
export default function NewCampaignPage() {
    return (
        <UnsavedChangesProvider>
            <FormulaireNouvelleCampagne />
        </UnsavedChangesProvider>
    );
}

function FormulaireNouvelleCampagne() {
    const { t } = useLangue();
    const [touche, setTouche] = useState(false);
    const [erreurs, setErreurs] = useState<Erreurs>({});
    const effacer = (cle: keyof Erreurs) => setErreurs((x) => (cle in x ? { ...x, [cle]: undefined } : x));
    const { user, getAccessToken, redirectToLogin, loading } = useAuth();
    const router = useRouter();

    // Form state
    const [campaignName, setCampaignName] = useState('');
    const [variants, setVariants] = useState<TrafficVariantRequest[]>([{ workflow_id: 0, workflow_definition_id: null, weight: 100 }]);
    const [sourceType, setSourceType] = useState<'csv'>('csv');
    const [sourceId, setSourceId] = useState('');
    const [selectedFileName, setSelectedFileName] = useState('');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [createError, setCreateError] = useState<string | null>(null);

    // Telephony configurations state
    const [telephonyConfigs, setTelephonyConfigs] = useState<TelephonyConfigurationListItem[]>([]);
    const [selectedTelephonyConfigId, setSelectedTelephonyConfigId] = useState<string>('');
    const [isLoadingTelephonyConfigs, setIsLoadingTelephonyConfigs] = useState(true);

    // Advanced settings state
    const [showAdvancedSettings, setShowAdvancedSettings] = useState(false);
    const [orgConcurrentLimit, setOrgConcurrentLimit] = useState<number>(2);
    const [fromNumbersCount, setFromNumbersCount] = useState<number>(0);
    const [maxConcurrency, setMaxConcurrency] = useState<string>('');
    const [rateLimitPerSecond, setRateLimitPerSecond] = useState('1');
    // Retry config state
    const [retryEnabled, setRetryEnabled] = useState(true);
    const [maxRetries, setMaxRetries] = useState<string>('2');
    const [retryDelaySeconds, setRetryDelaySeconds] = useState<string>('120');
    const [retryOnBusy, setRetryOnBusy] = useState(true);
    const [retryOnNoAnswer, setRetryOnNoAnswer] = useState(true);
    const [retryOnVoicemail, setRetryOnVoicemail] = useState(true);
    // Schedule config state
    const [scheduleEnabled, setScheduleEnabled] = useState(false);
    const [scheduleTimezone, setScheduleTimezone] = useState<ITimezoneOption | string>(() => {
        try {
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        } catch {
            return 'UTC';
        }
    });
    const [timeSlots, setTimeSlots] = useState<TimeSlot[]>([
        { day_of_week: 0, start_time: '09:00', end_time: '17:00' },
    ]);
    // Circuit breaker config state
    const [circuitBreakerEnabled, setCircuitBreakerEnabled] = useState(true);
    const [circuitBreakerFailureThreshold, setCircuitBreakerFailureThreshold] = useState<string>('50');
    const [circuitBreakerWindowSeconds, setCircuitBreakerWindowSeconds] = useState<string>('120');
    const [circuitBreakerMinCalls, setCircuitBreakerMinCalls] = useState<string>('5');

    // Redirect if not authenticated
    useEffect(() => {
        if (!loading && !user) {
            redirectToLogin();
        }
    }, [loading, user, redirectToLogin]);

    // Fetch telephony configurations
    const fetchTelephonyConfigs = useCallback(async () => {
        if (!user) return;
        try {
            const accessToken = await getAccessToken();
            const response = await listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet({
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                const configs = response.data.configurations ?? [];
                setTelephonyConfigs(configs);
                const defaultConfig = configs.find((c) => c.is_default_outbound) ?? configs[0];
                if (defaultConfig) {
                    setSelectedTelephonyConfigId(String(defaultConfig.id));
                }
            }
        } catch (error) {
            console.error('Failed to fetch telephony configurations:', error);
            notifier.echec({ fr: "Configurations de téléphonie illisibles. Rechargez la page.", en: "Could not load telephony configurations. Reload the page." });
        } finally {
            setIsLoadingTelephonyConfigs(false);
        }
    }, [user, getAccessToken]);

    // Fetch campaign limits
    const fetchCampaignDefaults = useCallback(async () => {
        if (!user) return;
        try {
            const accessToken = await getAccessToken();
            const response = await getCampaignDefaultsApiV1OrganizationsCampaignDefaultsGet({
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                setOrgConcurrentLimit(response.data.concurrent_call_limit);
                setFromNumbersCount(response.data.from_numbers_count);

                const last = (response.data as { last_campaign_settings?: {
                    retry_config?: { enabled: boolean; max_retries: number; retry_delay_seconds: number; retry_on_busy: boolean; retry_on_no_answer: boolean; retry_on_voicemail: boolean };
                    max_concurrency?: number | null;
                    rate_limit_per_second?: number;
                    schedule_config?: { enabled: boolean; timezone: string; slots: TimeSlot[] } | null;
                    circuit_breaker?: { enabled: boolean; failure_threshold: number; window_seconds: number; min_calls_in_window: number } | null;
                } | null }).last_campaign_settings;

                if (last) {
                    setRateLimitPerSecond(String(last.rate_limit_per_second ?? 1));
                    // Pre-populate from last campaign
                    if (last.retry_config) {
                        setRetryEnabled(last.retry_config.enabled);
                        setMaxRetries(String(last.retry_config.max_retries));
                        setRetryDelaySeconds(String(last.retry_config.retry_delay_seconds));
                        setRetryOnBusy(last.retry_config.retry_on_busy);
                        setRetryOnNoAnswer(last.retry_config.retry_on_no_answer);
                        setRetryOnVoicemail(last.retry_config.retry_on_voicemail);
                    } else {
                        const retryConfig = response.data.default_retry_config;
                        setRetryEnabled(retryConfig.enabled);
                        setMaxRetries(String(retryConfig.max_retries));
                        setRetryDelaySeconds(String(retryConfig.retry_delay_seconds));
                        setRetryOnBusy(retryConfig.retry_on_busy);
                        setRetryOnNoAnswer(retryConfig.retry_on_no_answer);
                        setRetryOnVoicemail(retryConfig.retry_on_voicemail);
                    }
                    if (last.max_concurrency) {
                        setMaxConcurrency(String(last.max_concurrency));
                    }
                    if (last.schedule_config) {
                        setScheduleEnabled(last.schedule_config.enabled);
                        setScheduleTimezone(last.schedule_config.timezone);
                        setTimeSlots(last.schedule_config.slots);
                    }
                    if (last.circuit_breaker) {
                        setCircuitBreakerEnabled(last.circuit_breaker.enabled);
                        setCircuitBreakerFailureThreshold(String(Math.round(last.circuit_breaker.failure_threshold * 100)));
                        setCircuitBreakerWindowSeconds(String(last.circuit_breaker.window_seconds));
                        setCircuitBreakerMinCalls(String(last.circuit_breaker.min_calls_in_window));
                    }
                } else {
                    // No previous campaign — use defaults
                    const retryConfig = response.data.default_retry_config;
                    setRetryEnabled(retryConfig.enabled);
                    setMaxRetries(String(retryConfig.max_retries));
                    setRetryDelaySeconds(String(retryConfig.retry_delay_seconds));
                    setRetryOnBusy(retryConfig.retry_on_busy);
                    setRetryOnNoAnswer(retryConfig.retry_on_no_answer);
                    setRetryOnVoicemail(retryConfig.retry_on_voicemail);
                }
            }
        } catch (error) {
            console.error('Failed to fetch campaign limits:', error);
        }
    }, [user, getAccessToken]);

    // Initial load
    useEffect(() => {
        if (!loading && user) {
            fetchCampaignDefaults();
            fetchTelephonyConfigs();
        }
    }, [fetchCampaignDefaults, fetchTelephonyConfigs, user, loading]);

    // Phone-number count for the selected telephony config drives concurrency
    // bounds. Falls back to the campaign-defaults endpoint's count (org default
    // config) until the configs list resolves.
    const selectedTelephonyConfig = telephonyConfigs.find(
        (c) => String(c.id) === selectedTelephonyConfigId,
    );
    const availableFromNumbersCount = selectedTelephonyConfig?.phone_number_count ?? fromNumbersCount;

    const effectiveLimit = orgConcurrentLimit;

    // Handle form submission
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setCreateError(null);

        const fautes: Erreurs = {};
        if (!campaignName) fautes.nom = t({ fr: "Donnez un nom à la campagne.", en: "Give the campaign a name." });
        if (trafficSplitError(variants)) fautes.repartition = t({ fr: "Corrigez la répartition du trafic.", en: "Fix the traffic split." });
        if (!selectedTelephonyConfigId) fautes.telephonie = t({ fr: "Choisissez une configuration de téléphonie.", en: "Choose a telephony configuration." });
        if (!sourceId) fautes.source = t({ fr: "Choisissez un fichier de contacts.", en: "Choose a contacts file." });

        const maxConcurrencyValue = maxConcurrency ? Number(maxConcurrency) : null;
        if (maxConcurrencyValue !== null && (
            !Number.isInteger(maxConcurrencyValue) || maxConcurrencyValue < 1 || maxConcurrencyValue > effectiveLimit
        )) {
            fautes.simultanes = t({ fr: `Appels simultanés : entre 1 et ${effectiveLimit}.`, en: `Concurrent calls: between 1 and ${effectiveLimit}.` });
        }
        const dialRate = Number(rateLimitPerSecond);
        if (!Number.isInteger(dialRate) || dialRate < 1 || dialRate > orgConcurrentLimit) {
            fautes.cadence = t({ fr: `Appels par seconde : entre 1 et ${orgConcurrentLimit}.`, en: `Calls per second: between 1 and ${orgConcurrentLimit}.` });
        }
        setErreurs(fautes);
        if (Object.keys(fautes).length > 0) {
            if (fautes.simultanes || fautes.cadence) setShowAdvancedSettings(true);
            return;
        }

        setIsSubmitting(true);

        try {
            const accessToken = await getAccessToken();

            const retryConfig = {
                enabled: retryEnabled,
                max_retries: parseInt(maxRetries) || 2,
                retry_delay_seconds: parseInt(retryDelaySeconds) || 120,
                retry_on_busy: retryOnBusy,
                retry_on_no_answer: retryOnNoAnswer,
                retry_on_voicemail: retryOnVoicemail,
            };

            // Build schedule_config if enabled
            const timezoneValue = getTimezoneValue(scheduleTimezone);
            const scheduleConfig = scheduleEnabled && timeSlots.length > 0
                ? {
                    enabled: true,
                    timezone: timezoneValue,
                    slots: timeSlots,
                }
                : undefined;

            // Build circuit_breaker config
            const circuitBreakerConfig = {
                enabled: circuitBreakerEnabled,
                failure_threshold: (parseInt(circuitBreakerFailureThreshold) || 50) / 100,
                window_seconds: parseInt(circuitBreakerWindowSeconds) || 120,
                min_calls_in_window: parseInt(circuitBreakerMinCalls) || 5,
            };


            const response = await createCampaignApiV1CampaignCreatePost({
                body: {
                    name: campaignName,
                    traffic_split: { variants },
                    source_type: sourceType,
                    source_id: sourceId,
                    telephony_configuration_id: parseInt(selectedTelephonyConfigId),
                    retry_config: retryConfig,
                    max_concurrency: maxConcurrencyValue,
                    rate_limit_per_second: dialRate,
                    schedule_config: scheduleConfig,
                    circuit_breaker: circuitBreakerConfig,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.error) {
                // Extract error message from API response
                setCreateError(echecAffiche(response.error, { fr: "Campagne non créée. Vérifiez les réglages et réessayez.", en: "Campaign not created. Check the settings and try again." }));
                return;
            }

            if (response.data) {
                setTouche(false);
                notifier.succes({ fr: "Campagne créée.", en: "Campaign created." });
                router.push(`/campaigns/${response.data.id}`);
            }
        } catch (error: unknown) {
            console.error('Failed to create campaign:', error);
            const errorMessage = 'Failed to create campaign';
            setCreateError(errorMessage);
            notifier.echec({ fr: "Campagne non créée. Réessayez dans un instant.", en: "Campaign not created. Try again in a moment." }, { erreur: errorMessage });
        } finally {
            setIsSubmitting(false);
        }
    };

    useUnsavedChanges('campagne', touche || campaignName.trim() !== '' || sourceId !== '');

    // Handle back navigation
    // Quitter avec un brouillon : le garde de l'application demande confirmation d'abord.
    const { confirmNavigate } = useUnsavedChangesContext();
    const handleBack = () => {
        confirmNavigate(() => router.push('/campaigns'));
    };

    // Handle CSV file upload
    const handleFileUploaded = (fileKey: string, fileName: string) => {
        setSourceId(fileKey);
        setSelectedFileName(fileName);
        setCreateError(null);
    };

    return (
        <>
            {/* La liste reste derrière, comme la maquette : la création est une fenêtre centrée posée dessus. */}
            <CampaignsPage />
            <FenetreLibre
                ouverte
                fermer={handleBack}
                titre={t({ en: 'New campaign', fr: 'Nouvelle campagne' })}
                info={t({ en: 'Set up a campaign to run calls in series from a file.', fr: 'Prépare des appels sortants en série, depuis un fichier.' })}
                corps={
                    <form id="nouvelle-campagne" onSubmit={handleSubmit} onChange={() => setTouche(true)} className="divide-y [&>*]:py-4">
                            <div className="space-y-2">
                                <Label htmlFor="campaign-name" className="flex items-center gap-1.5">
                                    {t({ en: 'Campaign name', fr: 'Nom de la campagne' })}
                                    <Info>{t({ en: 'Choose a descriptive name for your campaign', fr: 'Un nom qui dit ce que la campagne fait' })}</Info>
                                </Label>
                                <Input
                                    id="campaign-name"
                                    placeholder={t({ en: 'Campaign name', fr: 'Nom de la campagne' })}
                                    value={campaignName}
                                    onChange={(e) => {
                                        setCampaignName(e.target.value);
                                        effacer('nom');
                                    }}
                                    maxLength={255}
                                    required
                                    aria-invalid={!!erreurs.nom}
                                    aria-describedby={erreurs.nom ? 'campaign-name-erreur' : undefined}
                                />
                                <ErreurChamp id="campaign-name-erreur">{erreurs.nom}</ErreurChamp>
                            </div>

                            <TrafficSplitEditor value={variants} onChange={(v) => { setVariants(v); effacer('repartition'); }} disabled={isSubmitting} />
                            <ErreurChamp>{erreurs.repartition}</ErreurChamp>

                            <div className="space-y-2">
                                <Label htmlFor="telephony-config" className="flex items-center gap-1.5">
                                    {t({ en: 'Telephony configuration', fr: 'Configuration de téléphonie' })}
                                    <Info>{t({ en: "Outbound calls for this campaign will use this configuration's caller IDs", fr: "Les appels sortants de la campagne partent des numéros de cette configuration" })}</Info>
                                </Label>
                                {!isLoadingTelephonyConfigs && telephonyConfigs.length === 0 ? (
                                    <div className="py-2 text-sm text-muted-foreground">
                                        {t({ en: 'No telephony configuration yet.', fr: 'Aucune configuration de téléphonie.' })}{' '}
                                        <Link href="/telephony-configurations" className="cursor-pointer text-foreground hover:font-semibold">
                                            {t({ en: 'Add one', fr: 'En ajouter une' })}
                                        </Link>
                                    </div>
                                ) : (
                                    <Select
                                        value={selectedTelephonyConfigId}
                                        onValueChange={setSelectedTelephonyConfigId}
                                        required
                                    >
                                        <SelectTrigger id="telephony-config">
                                            <SelectValue placeholder={t({ en: 'Choose a configuration', fr: 'Choisir une configuration' })} />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {isLoadingTelephonyConfigs ? (
                                                <SelectItem value="loading" disabled>
                                                    {t({ en: 'Loading configurations...', fr: 'Chargement des configurations...' })}
                                                </SelectItem>
                                            ) : (
                                                telephonyConfigs.map((config) => (
                                                    <SelectItem
                                                        key={config.id}
                                                        value={config.id.toString()}
                                                    >
                                                        {config.name} ({config.provider})
                                                        {config.is_default_outbound ? ` - ${t({ en: 'default', fr: 'par défaut' })}` : ''}
                                                    </SelectItem>
                                                ))
                                            )}
                                        </SelectContent>
                                    </Select>
                                )}
                                <ErreurChamp>{erreurs.telephonie}</ErreurChamp>
                            </div>

                            <div className="space-y-2">
                                <Label htmlFor="source-type" className="flex items-center gap-1.5">
                                    {t({ en: 'Data source', fr: 'Source des contacts' })}
                                    <Info>{t({ en: 'Choose where your contact data is stored', fr: 'Où se trouvent les contacts à appeler' })}</Info>
                                </Label>
                                <Select
                                    value={sourceType}
                                    onValueChange={(value) => {
                                        setSourceType(value as 'csv');
                                        setSourceId('');
                                        setSelectedFileName('');
                                    }}
                                    required
                                >
                                    <SelectTrigger id="source-type">
                                        <SelectValue placeholder={t({ en: 'Choose a source', fr: 'Choisir une source' })} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="csv">{t({ en: 'CSV file', fr: 'Fichier CSV' })}</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>

                            <CsvUploadSelector
                                onFileUploaded={handleFileUploaded}
                                selectedFileName={selectedFileName}
                            />
                            <ErreurChamp>{erreurs.source}</ErreurChamp>

                            {/* Advanced Settings */}
                            <Collapsible
                                open={showAdvancedSettings}
                                onOpenChange={setShowAdvancedSettings}
                                className="border-t"
                            >
                                <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between py-4 hover:font-semibold">
                                    <span className="font-medium">{t({ en: 'Advanced settings', fr: 'Réglages avancés' })}</span>
                                    {showAdvancedSettings ? (
                                        <ChevronDown className="h-4 w-4" />
                                    ) : (
                                        <ChevronRight className="h-4 w-4" />
                                    )}
                                </CollapsibleTrigger>
                                <CollapsibleContent className="pb-4">
                                    <CampaignAdvancedSettings
                                        maxConcurrency={maxConcurrency}
                                        onMaxConcurrencyChange={(v) => { setMaxConcurrency(v); effacer('simultanes'); }}
                                        erreurs={erreurs}
                                        effectiveLimit={effectiveLimit}
                                        orgConcurrentLimit={orgConcurrentLimit}
                                        fromNumbersCount={availableFromNumbersCount}
                                        rateLimitPerSecond={rateLimitPerSecond}
                                        onRateLimitPerSecondChange={(v) => { setRateLimitPerSecond(v); effacer('cadence'); }}
                                        outboundBlockedReason={selectedTelephonyConfig?.outbound_blocked_reason}
                                        retryEnabled={retryEnabled}
                                        onRetryEnabledChange={setRetryEnabled}
                                        maxRetries={maxRetries}
                                        onMaxRetriesChange={setMaxRetries}
                                        retryDelaySeconds={retryDelaySeconds}
                                        onRetryDelaySecondsChange={setRetryDelaySeconds}
                                        retryOnBusy={retryOnBusy}
                                        onRetryOnBusyChange={setRetryOnBusy}
                                        retryOnNoAnswer={retryOnNoAnswer}
                                        onRetryOnNoAnswerChange={setRetryOnNoAnswer}
                                        retryOnVoicemail={retryOnVoicemail}
                                        onRetryOnVoicemailChange={setRetryOnVoicemail}
                                        scheduleEnabled={scheduleEnabled}
                                        onScheduleEnabledChange={setScheduleEnabled}
                                        scheduleTimezone={scheduleTimezone}
                                        onScheduleTimezoneChange={setScheduleTimezone}
                                        timeSlots={timeSlots}
                                        onTimeSlotsChange={setTimeSlots}
                                        circuitBreakerEnabled={circuitBreakerEnabled}
                                        onCircuitBreakerEnabledChange={setCircuitBreakerEnabled}
                                        circuitBreakerFailureThreshold={circuitBreakerFailureThreshold}
                                        onCircuitBreakerFailureThresholdChange={setCircuitBreakerFailureThreshold}
                                        circuitBreakerWindowSeconds={circuitBreakerWindowSeconds}
                                        onCircuitBreakerWindowSecondsChange={setCircuitBreakerWindowSeconds}
                                        circuitBreakerMinCalls={circuitBreakerMinCalls}
                                        onCircuitBreakerMinCallsChange={setCircuitBreakerMinCalls}
                                    />
                                </CollapsibleContent>
                            </Collapsible>

                            {createError && (
                                <div role="alert" className="text-sm text-destructive">
                                    {createError}
                                </div>
                            )}


                        </form>
                }
                actions={
                    <>
                        <Button type="button" variant="outline" onClick={handleBack} disabled={isSubmitting}>
                            {t({ en: 'Cancel', fr: 'Annuler' })}
                        </Button>
                        <Button
                            type="submit"
                            form="nouvelle-campagne"
                            disabled={isSubmitting || !campaignName || !!trafficSplitError(variants) || !sourceId || !selectedTelephonyConfigId}
                        >
                            {isSubmitting ? t({ en: 'Creating...', fr: 'Création...' }) : t({ en: 'Create the campaign', fr: 'Créer la campagne' })}
                        </Button>
                    </>
                }
            />
        </>
    );
}
