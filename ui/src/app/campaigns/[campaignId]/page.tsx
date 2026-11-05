"use client";

import { format } from 'date-fns';
import { AlertCircle, AlertTriangle, CalendarIcon, Download, Info, Megaphone, Pause, Pencil, Phone, Play, RefreshCw } from 'lucide-react';
import Link from 'next/link';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import {
    downloadCampaignReportApiV1CampaignCampaignIdReportGet,
    getCampaignApiV1CampaignCampaignIdGet,
    getCampaignSourceDownloadUrlApiV1CampaignCampaignIdSourceDownloadUrlGet,
    pauseCampaignApiV1CampaignCampaignIdPausePost,
    redialCampaignApiV1CampaignCampaignIdRedialPost,
    resumeCampaignApiV1CampaignCampaignIdResumePost,
    startCampaignApiV1CampaignCampaignIdStartPost,
} from '@/client/sdk.gen';
import type { CampaignResponse } from '@/client/types.gen';
import { ErreurChamp } from "@/components/mark/erreur-champ";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Info as Infobulle, PointEtat } from "@/components/mark/studio/marques";
import { useBaseEspace } from "@/components/mark/studio/base-espace";
import { PageStudio } from "@/components/mark/studio/shell-studio";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from '@/components/ui/button';
import { Calendar } from '@/components/ui/calendar';
import { Checkbox } from '@/components/ui/checkbox';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Separator } from '@/components/ui/separator';
import { CampaignRuns } from '@/components/workflow-runs';
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { useAuth } from '@/lib/auth';
import { formatDate, formatDateTime } from '@/lib/dateTime';

import CampaignTrafficStats from '../CampaignTrafficStats';
import { etatCampagne } from '../etat-campagne';

/** Une ligne en lecture : le libellé en gris, la valeur à côté (comme les lignes des réglages). */
function Lue({ libelle, children }: { libelle: string; children: React.ReactNode }) {
    return (
        <div className="flex items-center gap-3 py-3 text-sm">
            <span className="w-64 shrink-0 text-muted-foreground">{libelle}</span>
            <span className="min-w-0 flex-1 break-words">{children}</span>
        </div>
    );
}

export default function CampaignDetailPage() {
    const { t, langue } = useLangue();
    const base = useBaseEspace();
    const [redialErreur, setRedialErreur] = useState<string | null>(null);
    const { user, getAccessToken, redirectToLogin, loading } = useAuth();
    const organizationTimezone = useOrganizationTimezone();
    const router = useRouter();
    const params = useParams();
    const searchParams = useSearchParams();
    const campaignId = parseInt(params.campaignId as string);

    // Redirect if not authenticated
    useEffect(() => {
        if (!loading && !user) {
            redirectToLogin();
        }
    }, [loading, user, redirectToLogin]);

    // Campaign state
    const [campaign, setCampaign] = useState<CampaignResponse | null>(null);
    const [isLoadingCampaign, setIsLoadingCampaign] = useState(true);
    const [aConfirmer, setAConfirmer] = useState<'start' | 'resume' | null>(null);

    // Action state
    const [isExecutingAction, setIsExecutingAction] = useState(false);
    const [isDownloadingReport, setIsDownloadingReport] = useState(false);

    // Report date range state
    const [reportStartDate, setReportStartDate] = useState<Date | undefined>(undefined);
    const [reportStartTime, setReportStartTime] = useState('00:00');
    const [reportEndDate, setReportEndDate] = useState<Date | undefined>(undefined);
    const [reportEndTime, setReportEndTime] = useState('23:59');
    const [isReportPopoverOpen, setIsReportPopoverOpen] = useState(false);

    // Redial dialog state
    const [isRedialDialogOpen, setIsRedialDialogOpen] = useState(false);
    const [redialName, setRedialName] = useState('');
    const [redialOnVoicemail, setRedialOnVoicemail] = useState(true);
    const [redialOnNoAnswer, setRedialOnNoAnswer] = useState(true);
    const [redialOnBusy, setRedialOnBusy] = useState(true);
    const [isRedialing, setIsRedialing] = useState(false);

    // Fetch campaign details
    const fetchCampaign = useCallback(async () => {
        if (loading || !user) return;
        setIsLoadingCampaign(true);
        try {
            const accessToken = await getAccessToken();
            const response = await getCampaignApiV1CampaignCampaignIdGet({
                path: {
                    campaign_id: campaignId,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                setCampaign(response.data);
            }
        } catch (error) {
            console.error('Failed to fetch campaign:', error);
            notifier.echec({ fr: "Détail de la campagne illisible. Rechargez la page.", en: "Could not load the campaign. Reload the page." });
        } finally {
            setIsLoadingCampaign(false);
        }
    }, [user, loading, getAccessToken, campaignId]);

    // Initial load
    useEffect(() => {
        fetchCampaign();
    }, [fetchCampaign]);

    // Handle CSV download
    const handleDownloadCsv = async () => {
        if (!user || !campaign || campaign.source_type !== 'csv') return;

        try {
            const accessToken = await getAccessToken();
            const response = await getCampaignSourceDownloadUrlApiV1CampaignCampaignIdSourceDownloadUrlGet({
                path: {
                    campaign_id: campaignId,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data?.download_url) {
                // Open download URL in new tab
                window.open(response.data.download_url, '_blank');
            } else {
                notifier.echec({ fr: "Téléchargement impossible. Réessayez.", en: "Download failed. Try again." });
            }
        } catch (error) {
            console.error('Failed to download CSV:', error);
            notifier.echec({ fr: "Téléchargement impossible. Réessayez.", en: "Download failed. Try again." });
        }
    };

    // Build ISO datetime string from date + time
    const buildDateTime = (date: Date | undefined, time: string): string | undefined => {
        if (!date) return undefined;
        const [hours, minutes] = time.split(':').map(Number);
        const combined = new Date(date);
        combined.setHours(hours, minutes, 0, 0);
        return combined.toISOString();
    };

    // Handle download report
    const handleDownloadReport = async () => {
        if (!user) return;
        setIsDownloadingReport(true);
        setIsReportPopoverOpen(false);
        try {
            const accessToken = await getAccessToken();
            const startDate = buildDateTime(reportStartDate, reportStartTime);
            const endDate = buildDateTime(reportEndDate, reportEndTime);

            const response = await downloadCampaignReportApiV1CampaignCampaignIdReportGet({
                path: {
                    campaign_id: campaignId,
                },
                query: {
                    start_date: startDate,
                    end_date: endDate,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                },
                parseAs: 'blob',
            });

            if (response.data) {
                const blob = response.data as Blob;
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `campaign_${campaignId}_report.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } else {
                notifier.echec({ fr: "Rapport non téléchargé. Réessayez.", en: "Report not downloaded. Try again." });
            }
        } catch (error) {
            console.error('Failed to download report:', error);
            notifier.echec({ fr: "Rapport non téléchargé. Réessayez.", en: "Report not downloaded. Try again." });
        } finally {
            setIsDownloadingReport(false);
        }
    };

    const handleClearDateRange = () => {
        setReportStartDate(undefined);
        setReportStartTime('00:00');
        setReportEndDate(undefined);
        setReportEndTime('23:59');
    };

    // Handle start campaign
    const handleStart = async () => {
        if (!user) return;
        setIsExecutingAction(true);
        try {
            const accessToken = await getAccessToken();
            const response = await startCampaignApiV1CampaignCampaignIdStartPost({
                path: {
                    campaign_id: campaignId,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                setCampaign(response.data);
                notifier.succes({ fr: "Campagne lancée.", en: "Campaign started." });
            } else if (response.error) {
                // Extract error message from response
                let errorMsg = 'Failed to start campaign';
                if (typeof response.error === 'string') {
                    errorMsg = response.error;
                } else if (response.error && typeof response.error === 'object') {
                    errorMsg = (response.error as unknown as { detail?: string }).detail || JSON.stringify(response.error);
                }
                notifier.echec({ fr: "Campagne non lancée. Vérifiez les réglages et réessayez.", en: "Campaign not started. Check the settings and try again." }, { erreur: errorMsg });
            }
        } catch (error) {
            console.error('Failed to start campaign:', error);
            notifier.echec({ fr: "Campagne non lancée. Réessayez dans un instant.", en: "Campaign not started. Try again in a moment." });
        } finally {
            setIsExecutingAction(false);
        }
    };

    // Handle resume campaign
    const handleResume = async () => {
        if (!user) return;
        setIsExecutingAction(true);
        try {
            const accessToken = await getAccessToken();
            const response = await resumeCampaignApiV1CampaignCampaignIdResumePost({
                path: {
                    campaign_id: campaignId,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                setCampaign(response.data);
                notifier.succes({ fr: "Campagne reprise.", en: "Campaign resumed." });
            } else if (response.error) {
                // Extract error message from response
                let errorMsg = 'Failed to resume campaign';
                if (typeof response.error === 'string') {
                    errorMsg = response.error;
                } else if (response.error && typeof response.error === 'object') {
                    errorMsg = (response.error as unknown as { detail?: string }).detail || JSON.stringify(response.error);
                }
                notifier.echec({ fr: "Campagne non reprise. Vérifiez les réglages et réessayez.", en: "Campaign not resumed. Check the settings and try again." }, { erreur: errorMsg });
            }
        } catch (error) {
            console.error('Failed to resume campaign:', error);
            notifier.echec({ fr: "Campagne non reprise. Réessayez dans un instant.", en: "Campaign not resumed. Try again in a moment." });
        } finally {
            setIsExecutingAction(false);
        }
    };

    // Open redial dialog with default name
    const openRedialDialog = () => {
        if (!campaign) return;
        setRedialName(`${campaign.name} (Redial)`);
        setRedialOnVoicemail(true);
        setRedialOnNoAnswer(true);
        setRedialOnBusy(true);
        setRedialErreur(null);
        setIsRedialDialogOpen(true);
    };

    // Handle redial campaign
    const handleRedial = async () => {
        if (!user || !campaign) return;
        if (!redialOnVoicemail && !redialOnNoAnswer && !redialOnBusy) {
            setRedialErreur(t({ fr: "Cochez au moins un motif de rappel.", en: "Select at least one reason to redial." }));
            return;
        }
        setIsRedialing(true);
        try {
            const accessToken = await getAccessToken();
            const response = await redialCampaignApiV1CampaignCampaignIdRedialPost({
                path: {
                    campaign_id: campaignId,
                },
                body: {
                    name: redialName || null,
                    retry_on_voicemail: redialOnVoicemail,
                    retry_on_no_answer: redialOnNoAnswer,
                    retry_on_busy: redialOnBusy,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                notifier.succes({ fr: "Campagne de rappel créée.", en: "Redial campaign created." });
                setIsRedialDialogOpen(false);
                router.push(`/campaigns/${response.data.id}`);
            } else if (response.error) {
                let errorMsg = 'Failed to create redial campaign';
                if (typeof response.error === 'string') {
                    errorMsg = response.error;
                } else if (response.error && typeof response.error === 'object') {
                    errorMsg = (response.error as unknown as { detail?: string }).detail || JSON.stringify(response.error);
                }
                notifier.echec({ fr: "Rappel non créé. Vérifiez les motifs et réessayez.", en: "Redial not created. Check the reasons and try again." }, { erreur: errorMsg });
            }
        } catch (error) {
            console.error('Failed to redial campaign:', error);
            notifier.echec({ fr: "Rappel non créé. Réessayez dans un instant.", en: "Redial not created. Try again in a moment." });
        } finally {
            setIsRedialing(false);
        }
    };

    // Handle pause campaign
    const handlePause = async () => {
        if (!user) return;
        setIsExecutingAction(true);
        try {
            const accessToken = await getAccessToken();
            const response = await pauseCampaignApiV1CampaignCampaignIdPausePost({
                path: {
                    campaign_id: campaignId,
                },
                headers: {
                    'Authorization': `Bearer ${accessToken}`,
                }
            });

            if (response.data) {
                setCampaign(response.data);
                notifier.succes({ fr: "Campagne en pause.", en: "Campaign paused." });
            }
        } catch (error) {
            console.error('Failed to pause campaign:', error);
            notifier.echec({ fr: "Pause impossible. Réessayez.", en: "Could not pause. Try again." });
        } finally {
            setIsExecutingAction(false);
        }
    };

    const canEdit = campaign && ['created', 'running', 'paused'].includes(campaign.state);

    // Newest entries first. The backend appends chronologically; the UI is more
    // useful when the most recent failure / pause is at the top.
    const sortedLogs = (campaign?.logs ?? []).slice().reverse();

    const getLogIcon = (level: string) => {
        switch (level) {
            case 'error':
                return <AlertCircle className="size-4 text-destructive" />;
            case 'warning':
                return <AlertTriangle className="size-4 text-(--signal-warn)" />;
            default:
                return <Info className="size-4 text-foreground" />;
        }
    };

    const formatLogTimestamp = (ts: string) => {
        const d = new Date(ts);
        if (isNaN(d.getTime())) return ts;
        return formatDateTime(d, organizationTimezone, langue);
    };

    // Lancer ou reprendre une campagne fait partir de vrais appels vers de vraies personnes : on confirme d'abord.
    const confirmerLancement = () => {
        const geste = aConfirmer;
        setAConfirmer(null);
        if (geste === 'start') void handleStart();
        if (geste === 'resume') void handleResume();
    };

    // Render action button based on state
    const renderActionButton = () => {
        if (!campaign || isExecutingAction) return null;

        const editButton = canEdit ? (
            <Button variant="outline" onClick={() => router.push(`/campaigns/${campaignId}/edit`)}>
                <Pencil className="size-4" />
                {t({ en: 'Edit', fr: 'Modifier' })}
            </Button>
        ) : null;

        switch (campaign.state) {
            case 'created':
                return (
                    <div className="flex items-center gap-2">
                        {editButton}
                        <Button onClick={() => setAConfirmer('start')} disabled={isExecutingAction}>
                            <Play className="size-4" />
                            {t({ en: 'Start', fr: 'Lancer' })}
                        </Button>
                    </div>
                );
            case 'running':
                return (
                    <div className="flex items-center gap-2">
                        {editButton}
                        <Button onClick={handlePause} disabled={isExecutingAction}>
                            <Pause className="size-4" />
                            {t({ en: 'Pause', fr: 'Mettre en pause' })}
                        </Button>
                    </div>
                );
            case 'paused':
                return (
                    <div className="flex items-center gap-2">
                        {editButton}
                        <Button onClick={() => setAConfirmer('resume')} disabled={isExecutingAction}>
                            <RefreshCw className="size-4" />
                            {t({ en: 'Resume', fr: 'Reprendre' })}
                        </Button>
                    </div>
                );
            case 'completed':
                if (campaign.redialed_campaign_id) {
                    return null;
                }
                return (
                    <Button onClick={openRedialDialog}>
                        <Phone className="size-4" />
                        {t({ en: 'Redial', fr: 'Relancer les appels' })}
                    </Button>
                );
            default:
                return null;
        }
    };

    if (isLoadingCampaign) {
        return (
            <PageStudio>
                <EtatVide cas="chargement" />
            </PageStudio>
        );
    }

    if (!campaign) {
        return (
            <PageStudio>
                <EtatVide cas="erreur" reessayer={() => void fetchCampaign()} />
            </PageStudio>
        );
    }

    const etat = etatCampagne(campaign.state);
    const jours = [
        { en: 'Mon', fr: 'Lun' },
        { en: 'Tue', fr: 'Mar' },
        { en: 'Wed', fr: 'Mer' },
        { en: 'Thu', fr: 'Jeu' },
        { en: 'Fri', fr: 'Ven' },
        { en: 'Sat', fr: 'Sam' },
        { en: 'Sun', fr: 'Dim' },
    ];
    const oui = t({ en: 'Yes', fr: 'Oui' });
    const non = t({ en: 'No', fr: 'Non' });
    const lienCampagne = (id: number) => (
        <Link href={`/campaigns/${id}`} className="cursor-pointer hover:font-semibold">
            {t({ en: 'Campaign', fr: 'Campagne' })} #{id}
        </Link>
    );

    return (
        <PageStudio>
            <div className="space-y-4">
                <TitrePage
                    retour={{ href: `${base}/campagnes`, libelle: t({ en: 'Back to the campaigns', fr: 'Retour aux campagnes' }) }}
                    titre={campaign.name}
                    phrase={
                        <span className="inline-flex flex-wrap items-center gap-4">
                            <PointEtat etat={etat.point}>{t(etat.libelle)}</PointEtat>
                            <span>
                                {t({ en: 'Created', fr: 'Créée le' })} {formatDate(campaign.created_at, organizationTimezone, langue)}
                            </span>
                        </span>
                    }
                    action={
                        <div className="flex items-center gap-2">
                            <Popover open={isReportPopoverOpen} onOpenChange={setIsReportPopoverOpen}>
                                <PopoverTrigger asChild>
                                    <Button variant="outline" disabled={isDownloadingReport}>
                                        <Download className="size-4" />
                                        {t({ en: 'Report', fr: 'Rapport' })}
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-auto p-4" align="end">
                                    <div className="space-y-4">
                                        <div className="text-sm font-medium">{t({ en: 'Filter by date range', fr: 'Filtrer par période' })}</div>
                                        <div className="grid gap-3">
                                            <div className="space-y-1.5">
                                                <Label className="text-xs">{t({ en: 'From', fr: 'Du' })}</Label>
                                                <div className="flex gap-2">
                                                    <Popover>
                                                        <PopoverTrigger asChild>
                                                            <Button variant="outline" size="sm" className="w-[140px] justify-start text-left font-normal">
                                                                <CalendarIcon className="mr-2 size-3.5" />
                                                                {reportStartDate ? format(reportStartDate, 'dd/MM/yyyy') : t({ en: 'Start date', fr: 'Début' })}
                                                            </Button>
                                                        </PopoverTrigger>
                                                        <PopoverContent className="w-auto p-0" align="start">
                                                            <Calendar
                                                                mode="single"
                                                                selected={reportStartDate}
                                                                onSelect={setReportStartDate}
                                                                disabled={(date) => reportEndDate ? date > reportEndDate : false}
                                                            />
                                                        </PopoverContent>
                                                    </Popover>
                                                    <Input
                                                        type="time"
                                                        aria-label={t({ en: 'Start time', fr: 'Heure de début' })}
                                                        value={reportStartTime}
                                                        onChange={(e) => setReportStartTime(e.target.value)}
                                                        className="h-8 w-[100px] text-xs"
                                                    />
                                                </div>
                                            </div>
                                            <div className="space-y-1.5">
                                                <Label className="text-xs">{t({ en: 'To', fr: 'Au' })}</Label>
                                                <div className="flex gap-2">
                                                    <Popover>
                                                        <PopoverTrigger asChild>
                                                            <Button variant="outline" size="sm" className="w-[140px] justify-start text-left font-normal">
                                                                <CalendarIcon className="mr-2 size-3.5" />
                                                                {reportEndDate ? format(reportEndDate, 'dd/MM/yyyy') : t({ en: 'End date', fr: 'Fin' })}
                                                            </Button>
                                                        </PopoverTrigger>
                                                        <PopoverContent className="w-auto p-0" align="start">
                                                            <Calendar
                                                                mode="single"
                                                                selected={reportEndDate}
                                                                onSelect={setReportEndDate}
                                                                disabled={(date) => reportStartDate ? date < reportStartDate : false}
                                                            />
                                                        </PopoverContent>
                                                    </Popover>
                                                    <Input
                                                        type="time"
                                                        aria-label={t({ en: 'End time', fr: 'Heure de fin' })}
                                                        value={reportEndTime}
                                                        onChange={(e) => setReportEndTime(e.target.value)}
                                                        className="h-8 w-[100px] text-xs"
                                                    />
                                                </div>
                                            </div>
                                        </div>
                                        <Separator />
                                        <div className="flex justify-between">
                                            <Button variant="ghost" size="sm" onClick={handleClearDateRange}>
                                                {t({ en: 'Clear', fr: 'Effacer' })}
                                            </Button>
                                            <Button size="sm" onClick={handleDownloadReport} disabled={isDownloadingReport}>
                                                <Download className="mr-1.5 size-3.5" />
                                                {reportStartDate || reportEndDate
                                                    ? t({ en: 'Download filtered', fr: 'Télécharger la période' })
                                                    : t({ en: 'Download all', fr: 'Tout télécharger' })}
                                            </Button>
                                        </div>
                                    </div>
                                </PopoverContent>
                            </Popover>
                            {renderActionButton()}
                        </div>
                    }
                />
            </div>

            <CampaignTrafficStats campaign={campaign} />

            <section>
                <TitreTableau
                    titre={t({ en: 'Campaign', fr: 'Campagne' })}
                    info={<Infobulle>{t({ en: 'Configuration and source information', fr: 'Configuration et source des contacts' })}</Infobulle>}
                />
                <div className="divide-y border-t">
                    <Lue libelle={t({ en: 'Source type', fr: 'Type de source' })}>
                        {campaign.source_type === 'csv' ? t({ en: 'CSV file', fr: 'Fichier CSV' }) : campaign.source_type.replace('-', ' ')}
                    </Lue>
                    <Lue libelle={campaign.source_type === 'csv' ? t({ en: 'Source file', fr: 'Fichier source' }) : t({ en: 'Source sheet', fr: 'Feuille source' })}>
                        {campaign.source_type === 'csv' ? (
                            <button onClick={handleDownloadCsv} className="cursor-pointer break-all hover:font-semibold">
                                {campaign.source_id.split('/').pop()}
                            </button>
                        ) : (
                            <a href={campaign.source_id} target="_blank" rel="noopener noreferrer" className="cursor-pointer break-all hover:font-semibold">
                                {campaign.source_id}
                            </a>
                        )}
                    </Lue>
                    <Lue libelle={t({ en: 'Telephony configuration', fr: 'Configuration de téléphonie' })}>
                        {campaign.telephony_configuration_id ? (
                            <Link href={`/telephony-configurations/${campaign.telephony_configuration_id}`} className="cursor-pointer hover:font-semibold">
                                {campaign.telephony_configuration_name || `${t({ en: 'Configuration', fr: 'Configuration' })} #${campaign.telephony_configuration_id}`}
                            </Link>
                        ) : (
                            <span className="text-muted-foreground">{t({ en: 'Not assigned', fr: 'Aucune' })}</span>
                        )}
                    </Lue>
                    <Lue libelle={t({ en: 'Progress', fr: 'Avancement' })}>
                        {campaign.executed_count} / {campaign.total_queued_count}
                    </Lue>
                    {campaign.parent_campaign_id && <Lue libelle={t({ en: 'Redial of', fr: 'Relance de' })}>{lienCampagne(campaign.parent_campaign_id)}</Lue>}
                    {campaign.redialed_campaign_id && <Lue libelle={t({ en: 'Redialed as', fr: 'Relancée par' })}>{lienCampagne(campaign.redialed_campaign_id)}</Lue>}
                    {campaign.started_at && (
                        <Lue libelle={t({ en: 'Started at', fr: 'Lancée le' })}>{formatDateTime(campaign.started_at, organizationTimezone, langue)}</Lue>
                    )}
                    {campaign.completed_at && (
                        <Lue libelle={t({ en: 'Completed at', fr: 'Terminée le' })}>{formatDateTime(campaign.completed_at, organizationTimezone, langue)}</Lue>
                    )}
                </div>
            </section>

            <section>
                <TitreTableau
                    titre={t({ en: 'Settings', fr: 'Réglages' })}
                    info={<Infobulle>{t({ en: 'Concurrency, retries and call schedule', fr: 'Appels simultanés, nouvelles tentatives et plages horaires' })}</Infobulle>}
                />
                <div className="divide-y border-t">
                    <Lue libelle={t({ en: 'Max concurrent calls', fr: 'Appels simultanés au plus' })}>
                        {campaign.max_concurrency ? (
                            campaign.max_concurrency
                        ) : (
                            <span className="text-muted-foreground">{t({ en: 'Organization default', fr: "Celui de l'organisation" })}</span>
                        )}
                    </Lue>
                    <Lue libelle={t({ en: 'Retries', fr: 'Nouvelles tentatives' })}>{campaign.retry_config.enabled ? oui : non}</Lue>
                    {campaign.retry_config.enabled && (
                        <>
                            <Lue libelle={t({ en: 'Max retries', fr: 'Tentatives au plus' })}>{campaign.retry_config.max_retries}</Lue>
                            <Lue libelle={t({ en: 'Delay between retries', fr: 'Délai entre deux tentatives' })}>{campaign.retry_config.retry_delay_seconds} s</Lue>
                            <Lue libelle={t({ en: 'Retry on', fr: 'Relancer si' })}>
                                {[
                                    campaign.retry_config.retry_on_busy && t({ en: 'busy', fr: 'occupé' }),
                                    campaign.retry_config.retry_on_no_answer && t({ en: 'no answer', fr: 'sans réponse' }),
                                    campaign.retry_config.retry_on_voicemail && t({ en: 'voicemail', fr: 'messagerie' }),
                                ]
                                    .filter(Boolean)
                                    .join(', ') || '-'}
                            </Lue>
                        </>
                    )}
                    <Lue libelle={t({ en: 'Call schedule', fr: 'Plages horaires' })}>
                        {campaign.schedule_config?.enabled ? oui : <span className="text-muted-foreground">{t({ en: 'Not configured', fr: 'Non configurées' })}</span>}
                    </Lue>
                    {campaign.schedule_config?.enabled && (
                        <>
                            <Lue libelle={t({ en: 'Timezone', fr: 'Fuseau horaire' })}>{campaign.schedule_config.timezone.replace(/_/g, ' ')}</Lue>
                            <Lue libelle={t({ en: 'Time slots', fr: 'Créneaux' })}>
                                <span className="flex flex-wrap gap-x-4 gap-y-1">
                                    {campaign.schedule_config.slots.map((slot, index) => (
                                        <span key={index}>
                                            {t(jours[slot.day_of_week] ?? { en: '?', fr: '?' })} {slot.start_time} - {slot.end_time}
                                        </span>
                                    ))}
                                </span>
                            </Lue>
                        </>
                    )}
                </div>
            </section>

            <section>
                <TitreTableau
                    titre={t({ en: 'Activity log', fr: "Journal d'activité" })}
                    info={<Infobulle>{t({ en: 'Recent state transitions and failures. Newest first.', fr: 'Les changements d\'état et les échecs récents, du plus récent au plus ancien.' })}</Infobulle>}
                />
                {sortedLogs.length === 0 ? (
                    <EtatVide cas="premier" compact icone={Megaphone} titre={t({ en: 'No event recorded yet', fr: 'Aucun événement pour l\'instant' })} />
                ) : (
                    <Tableau
                        colonnes={[
                            { titre: t({ en: 'When', fr: 'Quand' }) },
                            { titre: t({ en: 'Event', fr: 'Événement' }) },
                            { titre: t({ en: 'Message', fr: 'Message' }) },
                        ]}
                    >
                        {sortedLogs.map((entry, idx) => (
                            <Ligne key={`${entry.ts}-${idx}`}>
                                <Cellule principale>
                                    <span className="inline-flex items-center gap-2">
                                        {getLogIcon(entry.level)}
                                        {formatLogTimestamp(entry.ts)}
                                    </span>
                                </Cellule>
                                <Cellule>
                                    <code className="text-xs">{entry.event}</code>
                                </Cellule>
                                <Cellule>
                                    <span className="break-words">{entry.message}</span>
                                    {entry.details && Object.keys(entry.details).length > 0 && (
                                        <details className="mt-1">
                                            <summary className="cursor-pointer text-xs hover:font-semibold">{t({ en: 'Details', fr: 'Détails' })}</summary>
                                            <pre className="mt-1.5 overflow-x-auto text-xs break-words whitespace-pre-wrap">
                                                {JSON.stringify(entry.details, null, 2)}
                                            </pre>
                                        </details>
                                    )}
                                </Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                )}
            </section>

            <section>
                <TitreTableau titre={t({ en: 'Calls of the campaign', fr: 'Appels de la campagne' })} />
                <CampaignRuns campaignId={campaignId} workflowId={campaign.workflow_id} searchParams={searchParams} />
            </section>

            <Dialog open={aConfirmer !== null} onOpenChange={(ouvert) => !ouvert && setAConfirmer(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            {aConfirmer === 'resume'
                                ? t({ en: 'Resume the campaign?', fr: 'Reprendre la campagne ?' })
                                : t({ en: 'Start the campaign?', fr: 'Lancer la campagne ?' })}
                        </DialogTitle>
                        <DialogDescription>
                            {t({
                                en: `Calls leave right away toward the contacts of the file (${(campaign.total_queued_count ?? 0) - (campaign.executed_count ?? 0)} left to call).`,
                                fr: `Les appels partent tout de suite vers les contacts du fichier (${(campaign.total_queued_count ?? 0) - (campaign.executed_count ?? 0)} restant à appeler).`,
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setAConfirmer(null)}>
                            {t({ en: 'Cancel', fr: 'Annuler' })}
                        </Button>
                        <Button onClick={confirmerLancement}>
                            {aConfirmer === 'resume' ? t({ en: 'Resume', fr: 'Reprendre' }) : t({ en: 'Start', fr: 'Lancer' })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>

            <Dialog open={isRedialDialogOpen} onOpenChange={setIsRedialDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>{t({ en: 'Redial the campaign', fr: 'Relancer la campagne' })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: 'Creates a new campaign that re-dials unique subscribers whose last call ended with one of the selected outcomes. Subscribers who were successfully reached on a retry are skipped.',
                                fr: "Crée une campagne qui rappelle les contacts dont le dernier appel a fini par l'un des résultats cochés. Ceux qui ont été joints à une nouvelle tentative sont écartés.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4 py-2">
                        <div className="space-y-1.5">
                            <Label htmlFor="redial-name">{t({ en: 'Name', fr: 'Nom' })}</Label>
                            <Input
                                id="redial-name"
                                value={redialName}
                                onChange={(e) => setRedialName(e.target.value)}
                                placeholder={t({ en: 'Campaign name', fr: 'Nom de la campagne' })}
                            />
                        </div>
                        <div className="space-y-3">
                            <Label>{t({ en: 'Redial when the last call was', fr: 'Rappeler si le dernier appel était' })}</Label>
                            <div className="flex items-center gap-2">
                                <Checkbox
                                    id="redial-voicemail"
                                    checked={redialOnVoicemail}
                                    onCheckedChange={(v) => { setRedialOnVoicemail(v === true); setRedialErreur(null); }}
                                />
                                <Label htmlFor="redial-voicemail" className="cursor-pointer font-normal">
                                    {t({ en: 'Voicemail', fr: 'Messagerie' })}
                                </Label>
                            </div>
                            <div className="flex items-center gap-2">
                                <Checkbox
                                    id="redial-no-answer"
                                    checked={redialOnNoAnswer}
                                    onCheckedChange={(v) => { setRedialOnNoAnswer(v === true); setRedialErreur(null); }}
                                />
                                <Label htmlFor="redial-no-answer" className="cursor-pointer font-normal">
                                    {t({ en: 'No answer', fr: 'Sans réponse' })}
                                </Label>
                            </div>
                            <div className="flex items-center gap-2">
                                <Checkbox
                                    id="redial-busy"
                                    checked={redialOnBusy}
                                    onCheckedChange={(v) => { setRedialOnBusy(v === true); setRedialErreur(null); }}
                                />
                                <Label htmlFor="redial-busy" className="cursor-pointer font-normal">
                                    {t({ en: 'Busy', fr: 'Occupé' })}
                                </Label>
                            </div>
                        </div>
                        <ErreurChamp>{redialErreur}</ErreurChamp>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setIsRedialDialogOpen(false)} disabled={isRedialing}>
                            {t({ en: 'Cancel', fr: 'Annuler' })}
                        </Button>
                        <Button onClick={handleRedial} disabled={isRedialing}>
                            {isRedialing ? t({ en: 'Creating...', fr: 'Création...' }) : t({ en: 'Create the redial campaign', fr: 'Créer la campagne de relance' })}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </PageStudio>
    );
}
