"use client";

import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';
import type { ITimezoneOption } from 'react-timezone-select';

import {
    getCampaignApiV1CampaignCampaignIdGet,
    getCampaignDefaultsApiV1OrganizationsCampaignDefaultsGet,
    listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet,
    updateCampaignApiV1CampaignCampaignIdPatch
} from '@/client/sdk.gen';
import type { CampaignResponse, TrafficVariantRequest } from '@/client/types.gen';
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { echecAffiche } from '@/components/mark/notifications/echec-affiche';
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { UnsavedChangesProvider, useUnsavedChanges, useUnsavedChangesContext } from '@/context/UnsavedChangesContext';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';

import CampaignAdvancedSettings, { getTimezoneValue, type TimeSlot } from '../../CampaignAdvancedSettings';
import TrafficSplitEditor, { trafficSplitError } from '../../TrafficSplitEditor';

type Erreurs = Partial<Record<'nom' | 'repartition' | 'simultanes' | 'cadence' | 'plages', string>>;

/** Quitter la page avec des changements non enregistrés : on prévient. */
export default function EditCampaignPage() {
    return (
        <UnsavedChangesProvider>
            <FormulaireCampagne />
        </UnsavedChangesProvider>
    );
}

function FormulaireCampagne() {
    const { t } = useLangue();
    const [touche, setTouche] = useState(false);
    const [erreurs, setErreurs] = useState<Erreurs>({});
    const effacer = (cle: keyof Erreurs) => setErreurs((x) => (cle in x ? { ...x, [cle]: undefined } : x));
    const { user, getAccessToken, redirectToLogin, loading } = useAuth();
    const router = useRouter();
    const params = useParams();
    const campaignId = parseInt(params.campaignId as string);

    // Loading state
    const [isLoading, setIsLoading] = useState(true);
    const [campaign, setCampaign] = useState<CampaignResponse | null>(null);

    // Form state
    const [campaignName, setCampaignName] = useState('');
    const [variants, setVariants] = useState<TrafficVariantRequest[]>([]);
    const [splitChanged, setSplitChanged] = useState(false);
    const [maxConcurrency, setMaxConcurrency] = useState<string>('');
    const [rateLimitPerSecond, setRateLimitPerSecond] = useState('1');
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [submitError, setSubmitError] = useState<string | null>(null);

    const [outboundBlockedReason, setOutboundBlockedReason] = useState<string | null>(null);

    // Limits state
    const [orgConcurrentLimit, setOrgConcurrentLimit] = useState<number>(2);
    const [fromNumbersCount, setFromNumbersCount] = useState<number>(0);

    // Retry config state
    const [retryEnabled, setRetryEnabled] = useState(true);
    const [maxRetries, setMaxRetries] = useState<string>('2');
    const [retryDelaySeconds, setRetryDelaySeconds] = useState<string>('120');
    const [retryOnBusy, setRetryOnBusy] = useState(true);
    const [retryOnNoAnswer, setRetryOnNoAnswer] = useState(true);
    const [retryOnVoicemail, setRetryOnVoicemail] = useState(true);

    // Schedule config state
    const [scheduleEnabled, setScheduleEnabled] = useState(false);
    const [scheduleTimezone, setScheduleTimezone] = useState<ITimezoneOption | string>('UTC');
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

    // Fetch campaign and populate form
    const fetchCampaign = useCallback(async () => {
        if (!user) return;
        setIsLoading(true);
        try {
            const accessToken = await getAccessToken();
            const headers = { 'Authorization': `Bearer ${accessToken}` };
            const [response, defaultsResponse, configsResponse] = await Promise.all([
                getCampaignApiV1CampaignCampaignIdGet({
                    path: { campaign_id: campaignId },
                    headers,
                }),
                getCampaignDefaultsApiV1OrganizationsCampaignDefaultsGet({ headers }),
                listTelephonyConfigurationsApiV1OrganizationsTelephonyConfigsGet({ headers }),
            ]);

            if (response.error || !response.data) {
                throw new Error(detailFromError(response.error, 'Failed to load campaign'));
            }
            if (defaultsResponse.error || !defaultsResponse.data) {
                throw new Error(detailFromError(defaultsResponse.error, 'Failed to load campaign limits'));
            }
            if (configsResponse.error || !configsResponse.data) {
                throw new Error(detailFromError(configsResponse.error, 'Failed to load telephony configurations'));
            }

            if (response.data) {
                const c = response.data;

                // Redirect if campaign is completed or failed
                if (['completed', 'failed'].includes(c.state)) {
                    router.replace(`/campaigns/${campaignId}`);
                    return;
                }

                // Pinned campaigns use their own caller IDs. Only legacy campaigns
                // without a selected configuration use the organization default.
                const selectedConfig = configsResponse.data.configurations.find(
                    (config) => config.id === c.telephony_configuration_id,
                );
                if (c.telephony_configuration_id != null && !selectedConfig) {
                    throw new Error('The campaign\'s telephony configuration could not be found');
                }
                setOrgConcurrentLimit(defaultsResponse.data.concurrent_call_limit);
                setOutboundBlockedReason(selectedConfig?.outbound_blocked_reason ?? null);
                setFromNumbersCount(selectedConfig
                    ? selectedConfig.phone_number_count ?? 0
                    : defaultsResponse.data.from_numbers_count);
                setCampaign(c);

                // Populate form state
                setCampaignName(c.name);
                setVariants(c.traffic_split?.variants.map(v => ({ workflow_id: v.workflow_id, workflow_definition_id: v.workflow_definition_id, weight: v.weight })) ?? [{ workflow_id: c.workflow_id, workflow_definition_id: null, weight: 100 }]);
                setSplitChanged(false);
                setRateLimitPerSecond(String(c.rate_limit_per_second));
                setMaxConcurrency(c.max_concurrency ? String(c.max_concurrency) : '');

                // Retry config
                setRetryEnabled(c.retry_config.enabled);
                setMaxRetries(String(c.retry_config.max_retries));
                setRetryDelaySeconds(String(c.retry_config.retry_delay_seconds));
                setRetryOnBusy(c.retry_config.retry_on_busy);
                setRetryOnNoAnswer(c.retry_config.retry_on_no_answer);
                setRetryOnVoicemail(c.retry_config.retry_on_voicemail);

                // Schedule config
                if (c.schedule_config) {
                    setScheduleEnabled(c.schedule_config.enabled);
                    setScheduleTimezone(c.schedule_config.timezone);
                    if (c.schedule_config.slots.length > 0) {
                        setTimeSlots(c.schedule_config.slots.map((s: TimeSlot) => ({ ...s })));
                    }
                }

                // Circuit breaker config
                const cb = (c as unknown as { circuit_breaker?: { enabled: boolean; failure_threshold: number; window_seconds: number; min_calls_in_window: number } }).circuit_breaker;
                if (cb) {
                    setCircuitBreakerEnabled(cb.enabled);
                    setCircuitBreakerFailureThreshold(String(Math.round(cb.failure_threshold * 100)));
                    setCircuitBreakerWindowSeconds(String(cb.window_seconds));
                    setCircuitBreakerMinCalls(String(cb.min_calls_in_window));
                }
            }
        } catch (error) {
            console.error('Failed to fetch campaign:', error);
            notifier.echec({ fr: "Campagne illisible. Rechargez la page.", en: "Could not load the campaign. Reload the page." }, { erreur: error });
            router.replace(`/campaigns/${campaignId}`);
        } finally {
            setIsLoading(false);
        }
    }, [user, getAccessToken, campaignId, router]);

    // Initial load
    useEffect(() => {
        if (!loading && user) {
            fetchCampaign();
        }
    }, [fetchCampaign, loading, user]);

    const effectiveLimit = orgConcurrentLimit;

    // Handle form submission
    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setSubmitError(null);

        const fautes: Erreurs = {};
        if (!campaignName.trim()) fautes.nom = t({ fr: "Donnez un nom à la campagne.", en: "Give the campaign a name." });
        if (splitChanged && trafficSplitError(variants)) fautes.repartition = t({ fr: "Corrigez la répartition du trafic.", en: "Fix the traffic split." });

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

        // Validate schedule slots if enabled
        if (scheduleEnabled) {
            if (timeSlots.length === 0) {
                fautes.plages = t({ fr: "Ajoutez au moins une plage horaire.", en: "Add at least one time slot." });
            } else if (timeSlots.some((slot) => slot.start_time >= slot.end_time)) {
                fautes.plages = t({ fr: "Chaque plage doit finir après son début.", en: "Each slot must end after it starts." });
            }
        }
        setErreurs(fautes);
        if (Object.keys(fautes).length > 0) return;

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

            const timezoneValue = getTimezoneValue(scheduleTimezone);
            const scheduleConfig = scheduleEnabled && timeSlots.length > 0
                ? {
                    enabled: true,
                    timezone: timezoneValue,
                    slots: timeSlots,
                }
                : {
                    enabled: false,
                    timezone: timezoneValue,
                    slots: [{ day_of_week: 0, start_time: '09:00', end_time: '17:00' }],
                };

            const circuitBreakerConfig = {
                enabled: circuitBreakerEnabled,
                failure_threshold: (parseInt(circuitBreakerFailureThreshold) || 50) / 100,
                window_seconds: parseInt(circuitBreakerWindowSeconds) || 120,
                min_calls_in_window: parseInt(circuitBreakerMinCalls) || 5,
            };


            const response = await updateCampaignApiV1CampaignCampaignIdPatch({
                path: { campaign_id: campaignId },
                body: {
                    name: campaignName,
                    ...(splitChanged ? { traffic_split: { variants } } : {}),
                    retry_config: retryConfig,
                    max_concurrency: maxConcurrencyValue,
                    rate_limit_per_second: dialRate,
                    schedule_config: scheduleConfig,
                    circuit_breaker: circuitBreakerConfig,
                },
                headers: { 'Authorization': `Bearer ${accessToken}` },
            });

            if (response.error) {
                setSubmitError(echecAffiche(response.error, { fr: "Campagne non modifiée. Vérifiez les réglages et réessayez.", en: "Campaign not updated. Check the settings and try again." }));
                return;
            }

            if (response.data) {
                notifier.succes({ fr: "Campagne modifiée.", en: "Campaign updated." });
                router.push(`/campaigns/${campaignId}`);
            }
        } catch (error) {
            console.error('Failed to update campaign:', error);
            const errorMessage = 'Failed to update campaign';
            setSubmitError(errorMessage);
            notifier.echec({ fr: "Campagne non modifiée. Réessayez dans un instant.", en: "Campaign not updated. Try again in a moment." }, { erreur: errorMessage });
        } finally {
            setIsSubmitting(false);
        }
    };

    // Quitter avec un brouillon : le garde de l'application demande confirmation d'abord.
    const { confirmNavigate } = useUnsavedChangesContext();
    const handleBack = () => {
        confirmNavigate(() => router.push(`/campaigns/${campaignId}`));
    };

    // Quitter avec des changements non enregistrés : le garde de l'application prévient.
    useUnsavedChanges('campagne', touche || splitChanged);

    if (isLoading) {
        return (
            <PageStudio>
                <EtatVide cas="chargement" />
            </PageStudio>
        );
    }

    if (!campaign) {
        return (
            <PageStudio>
                <EtatVide cas="erreur" />
            </PageStudio>
        );
    }

    return (
        <PageStudio>
            <div className="mx-auto max-w-2xl space-y-8">
                <Link
                    href={`/campaigns/${campaignId}`}
                    className="inline-flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground hover:font-semibold hover:text-foreground"
                >
                    <ArrowLeft className="size-4" />
                    {campaign.name}
                </Link>
                <TitrePage
                    titre={t({ en: 'Edit the campaign', fr: 'Modifier la campagne' })}
                    info={t({ en: 'Update name, concurrency, retry, and schedule configuration', fr: "Nom, appels simultanés, nouvelles tentatives et plages horaires" })}
                />
                <form onSubmit={handleSubmit} onChange={() => setTouche(true)} className="space-y-6">
                        {/* Campaign Name */}
                        <div className="space-y-2">
                            <Label htmlFor="campaign-name">{t({ en: 'Campaign name', fr: 'Nom de la campagne' })}</Label>
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

                        <Separator />

                        <TrafficSplitEditor value={variants} onChange={value => { setVariants(value); setSplitChanged(true); effacer('repartition'); }} disabled={isSubmitting} editing />
                        <ErreurChamp>{erreurs.repartition}</ErreurChamp>

                        <CampaignAdvancedSettings
                            maxConcurrency={maxConcurrency}
                            onMaxConcurrencyChange={(v) => { setMaxConcurrency(v); effacer('simultanes'); }}
                            erreurs={erreurs}
                            effectiveLimit={effectiveLimit}
                            orgConcurrentLimit={orgConcurrentLimit}
                            fromNumbersCount={fromNumbersCount}
                            rateLimitPerSecond={rateLimitPerSecond}
                            onRateLimitPerSecondChange={(v) => { setRateLimitPerSecond(v); effacer('cadence'); }}
                            outboundBlockedReason={outboundBlockedReason}
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
                            onTimeSlotsChange={(v) => { setTimeSlots(v); effacer('plages'); }}
                            circuitBreakerEnabled={circuitBreakerEnabled}
                            onCircuitBreakerEnabledChange={setCircuitBreakerEnabled}
                            circuitBreakerFailureThreshold={circuitBreakerFailureThreshold}
                            onCircuitBreakerFailureThresholdChange={setCircuitBreakerFailureThreshold}
                            circuitBreakerWindowSeconds={circuitBreakerWindowSeconds}
                            onCircuitBreakerWindowSecondsChange={setCircuitBreakerWindowSeconds}
                            circuitBreakerMinCalls={circuitBreakerMinCalls}
                            onCircuitBreakerMinCallsChange={setCircuitBreakerMinCalls}
                        />

                        {submitError && (
                            <div role="alert" className="text-sm text-destructive">
                                {submitError}
                            </div>
                        )}

                        <div className="flex gap-4 pt-4">
                            <Button
                                type="submit"
                                disabled={isSubmitting || !campaignName.trim()}
                            >
                                {isSubmitting ? t({ en: 'Saving...', fr: 'Enregistrement...' }) : t({ en: 'Save', fr: 'Enregistrer' })}
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={handleBack}
                                disabled={isSubmitting}
                            >
                                {t({ en: 'Cancel', fr: 'Annuler' })}
                            </Button>
                        </div>
                    </form>
            </div>
        </PageStudio>
    );
}
