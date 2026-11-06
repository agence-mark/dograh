"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Download, Globe, PhoneIncoming, Search } from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import TimezoneSelect, { type ITimezoneOption } from 'react-timezone-select';

import { downloadUsageRunsReportApiV1OrganizationsUsageRunsReportGet, getDailyUsageBreakdownApiV1OrganizationsUsageDailyBreakdownGet, getPreferencesApiV1OrganizationsPreferencesGet, getUsageHistoryApiV1OrganizationsUsageRunsGet, getWorkflowsSummaryApiV1WorkflowSummaryGet, savePreferencesApiV1OrganizationsPreferencesPut } from '@/client/sdk.gen';
import type { DailyUsageBreakdownResponse, OrganizationPreferences, UsageHistoryResponse, WorkflowSummaryResponse } from '@/client/types.gen';
import { CallTypeCell } from '@/components/CallTypeCell';
import { DailyUsageTable } from '@/components/DailyUsageTable';
import { FilterBuilder } from '@/components/filters/FilterBuilder';
import { useLangue } from '@/components/mark/langue/langue';
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { NoteJuge } from '@/components/mark/studio/marques';
import { BarrePagination } from '@/components/mark/studio/pagination';
import { PageStudio } from '@/components/mark/studio/shell-studio';
import { Cellule, Ligne, Tableau } from '@/components/mark/studio/tableau';
import { TitrePage } from '@/components/mark/studio/titre-page';
import { MediaPreviewButton, MediaPreviewDialog } from '@/components/MediaPreviewDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useUserConfig } from '@/context/UserConfigContext';
import { useDispositionCodes } from '@/hooks/useDispositionCodes';
import { detailFromError } from '@/lib/apiError';
import { useAuth } from '@/lib/auth';
import { getLocalTimezone } from '@/lib/dateTime';
import { DateRelative } from '@/components/mark/studio/date-relative';
import { usageFilterAttributes, withDispositionCodeOptions } from '@/lib/filterAttributes';
import { decodeFiltersFromURL, encodeFiltersToURL } from '@/lib/filters';
import type { ActiveFilter, DateRangeValue, FilterAttribute, NumberFilterOption } from '@/types/filters';

const buildUsageFilterAttributes = (
    agentOptions: NumberFilterOption[] | null,
    isLoadingAgentOptions: boolean,
    dispositionCodes: string[]
): FilterAttribute[] => {
    return withDispositionCodeOptions(usageFilterAttributes, dispositionCodes).map(attribute => {
        if (attribute.id !== 'workflowId') {
            return attribute;
        }

        return {
            ...attribute,
            label: 'Agent',
            type: 'numberSelect',
            config: {
                ...attribute.config,
                placeholder: 'Select an agent',
                numberSelectLabel: 'Agent',
                ...(agentOptions || isLoadingAgentOptions
                    ? {
                        numberSelectOptions: agentOptions ?? [],
                        numberSelectOptionsLoading: isLoadingAgentOptions,
                    }
                    : {}),
            },
        } satisfies FilterAttribute;
    });
};

export default function UsagePage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { t, langue } = useLangue();
    const { organizationPricing } = useUserConfig();
    const auth = useAuth();

    // Usage history state
    const [usageHistory, setUsageHistory] = useState<UsageHistoryResponse | null>(null);
    const [isLoadingHistory, setIsLoadingHistory] = useState(false);
    const [historyFailed, setHistoryFailed] = useState(false);
    const [currentPage, setCurrentPage] = useState(() => {
        const pageParam = searchParams.get('page');
        return pageParam ? parseInt(pageParam, 10) : 1;
    });
    const [isExecutingFilters, setIsExecutingFilters] = useState(false);
    // Sort state (initialized from URL). Sorting is server-side because the
    // listing is paginated — sorting the current page client-side would only
    // reorder the 50 rows in hand.
    const [sortBy, setSortBy] = useState<string | null>(() => {
        return searchParams.get('sort_by') || null;
    });
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>(() => {
        return searchParams.get('sort_order') === 'asc' ? 'asc' : 'desc';
    });
    // [.mark] C4 : recherche dans les transcriptions (3 lettres au moins, envoyée après une courte pause). `recherche` est ce
    // qu'on tape, `rechercheAppliquee` ce qui part au serveur (et dans l'adresse).
    const [recherche, setRecherche] = useState(() => searchParams.get('q') ?? '');
    const [rechercheAppliquee, setRechercheAppliquee] = useState(() => searchParams.get('q') ?? '');
    const rechercheRef = useRef(rechercheAppliquee);
    rechercheRef.current = rechercheAppliquee;
    const [isDownloadingReport, setIsDownloadingReport] = useState(false);
    const [agentFilterOptions, setAgentFilterOptions] = useState<NumberFilterOption[] | null>(null);
    const [isLoadingAgentFilterOptions, setIsLoadingAgentFilterOptions] = useState(false);
    const { codes: dispositionCodes } = useDispositionCodes();
    const availableUsageFilterAttributes = useMemo(
        () => buildUsageFilterAttributes(agentFilterOptions, isLoadingAgentFilterOptions, dispositionCodes),
        [agentFilterOptions, isLoadingAgentFilterOptions, dispositionCodes]
    );

    // Daily usage breakdown state (only for paid orgs)
    const [dailyUsage, setDailyUsage] = useState<DailyUsageBreakdownResponse | null>(null);
    const [isLoadingDaily, setIsLoadingDaily] = useState(false);

    // Initialize filters from URL. `activeFilters` tracks the in-progress
    // edits in the FilterBuilder; `appliedFilters` is what's actually been
    // committed via Apply (and what drives fetching + the download button).
    const [activeFilters, setActiveFilters] = useState<ActiveFilter[]>(() => {
        return decodeFiltersFromURL(searchParams, availableUsageFilterAttributes);
    });
    const [appliedFilters, setAppliedFilters] = useState<ActiveFilter[]>(() => {
        return decodeFiltersFromURL(searchParams, availableUsageFilterAttributes);
    });

    // Media preview dialog
    const mediaPreview = MediaPreviewDialog();

    // Timezone state - initialize with empty string to avoid hydration mismatch
    const localTimezone = getLocalTimezone();
    const [selectedTimezone, setSelectedTimezone] = useState<ITimezoneOption | string>('');
    const [savingTimezone, setSavingTimezone] = useState(false);
    const [preferences, setPreferences] = useState<OrganizationPreferences>({});
    const [preferencesLoading, setPreferencesLoading] = useState(true);
    const timezoneSelectId = useId(); // Stable ID for react-select to prevent hydration mismatch

    // Translate the FilterBuilder state into the query-param shape the
    // backend expects. Shared between the listing fetch and the CSV export
    // so they stay in lockstep.
    const buildUsageQueryParams = (filters?: ActiveFilter[]) => {
        let filterParam: string | undefined;
        let startDate = '';
        let endDate = '';

        if (filters && filters.length > 0) {
            const dateRangeFilter = filters.find(f => f.attribute.id === 'dateRange');
            if (dateRangeFilter && dateRangeFilter.value) {
                const dateValue = dateRangeFilter.value as DateRangeValue;
                if (dateValue.from) startDate = dateValue.from.toISOString();
                if (dateValue.to) endDate = dateValue.to.toISOString();
            }

            const otherFilters = filters.filter(f => f.attribute.id !== 'dateRange');
            if (otherFilters.length > 0) {
                const filterData = otherFilters.map(filter => ({
                    attribute: filter.attribute.id,
                    type: filter.attribute.type === 'numberSelect' ? 'number' : filter.attribute.type,
                    value: filter.value,
                }));
                filterParam = JSON.stringify(filterData);
            }
        }

        return {
            ...(startDate && { start_date: startDate }),
            ...(endDate && { end_date: endDate }),
            ...(filterParam && { filters: filterParam }),
        };
    };

    // Fetch usage history
    const fetchUsageHistory = useCallback(async (
        page: number,
        filters?: ActiveFilter[],
        sortByParam?: string | null,
        sortOrderParam?: 'asc' | 'desc'
    ) => {
        if (!auth.isAuthenticated) return;
        setIsLoadingHistory(true);
        try {
            const response = await getUsageHistoryApiV1OrganizationsUsageRunsGet({
                query: {
                    page,
                    limit: 50,
                    ...buildUsageQueryParams(filters),
                    ...(rechercheRef.current && { q: rechercheRef.current }),
                    ...(sortByParam && { sort_by: sortByParam }),
                    ...(sortOrderParam && { sort_order: sortOrderParam }),
                },
            });

            setHistoryFailed(Boolean(response.error) || !response.data);
            if (response.data) {
                setUsageHistory(response.data);
            }
        } catch (error) {
            console.error('Failed to fetch usage history:', error);
            setHistoryFailed(true);
        } finally {
            setIsLoadingHistory(false);
        }
    }, [auth.isAuthenticated]);

    // Fetch daily usage breakdown
    const fetchDailyUsage = useCallback(async () => {
        if (!auth.isAuthenticated || !organizationPricing?.price_per_second_usd) return;

        setIsLoadingDaily(true);
        try {
            const response = await getDailyUsageBreakdownApiV1OrganizationsUsageDailyBreakdownGet({
                query: { days: 7 },
            });

            if (response.data) {
                setDailyUsage(response.data);
            }
        } catch (error) {
            console.error('Failed to fetch daily usage:', error);
        } finally {
            setIsLoadingDaily(false);
        }
    }, [auth.isAuthenticated, organizationPricing]);

    const fetchAgentFilterOptions = useCallback(async () => {
        if (!auth.isAuthenticated) return;

        setIsLoadingAgentFilterOptions(true);
        try {
            const response = await getWorkflowsSummaryApiV1WorkflowSummaryGet({
                query: {
                    status: 'active',
                },
            });
            if (response.error) {
                throw new Error(detailFromError(response.error, 'Failed to load agents'));
            }

            const options = [...(response.data ?? [])]
                .sort((a: WorkflowSummaryResponse, b: WorkflowSummaryResponse) => (
                    a.name.localeCompare(b.name) || a.id - b.id
                ))
                .map((workflow: WorkflowSummaryResponse) => ({
                    label: `${workflow.name || 'Untitled Agent'} (#${workflow.id})`,
                    value: workflow.id,
                }));
            setAgentFilterOptions(options);
        } catch (error) {
            console.error('Failed to fetch agent filter options:', error);
            setAgentFilterOptions(null);
        } finally {
            setIsLoadingAgentFilterOptions(false);
        }
    }, [auth.isAuthenticated]);

    const fetchPreferences = useCallback(async () => {
        if (!auth.isAuthenticated) return;

        setPreferencesLoading(true);
        try {
            const response = await getPreferencesApiV1OrganizationsPreferencesGet();
            const nextPreferences: OrganizationPreferences = response.data || {};
            setPreferences(nextPreferences);
            setSelectedTimezone(nextPreferences.timezone || localTimezone);
        } catch (error) {
            console.error('Failed to fetch organization preferences:', error);
            setSelectedTimezone(localTimezone);
        } finally {
            setPreferencesLoading(false);
        }
    }, [auth.isAuthenticated, localTimezone]);

    // Download a CSV of all runs matching the current filters.
    const handleDownloadReport = async () => {
        if (!auth.isAuthenticated) return;
        setIsDownloadingReport(true);
        try {
            const response = await downloadUsageRunsReportApiV1OrganizationsUsageRunsReportGet({
                query: buildUsageQueryParams(appliedFilters),
                parseAs: 'blob',
            });

            if (response.data) {
                const blob = response.data as Blob;
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'usage_runs_report.csv';
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } else {
                notifier.echec({ fr: "Rapport non téléchargé. Réessayez.", en: "Report not downloaded. Try again." });
            }
        } catch (error) {
            console.error('Failed to download usage report:', error);
            notifier.echec({ fr: "Rapport non téléchargé. Réessayez.", en: "Report not downloaded. Try again." });
        } finally {
            setIsDownloadingReport(false);
        }
    };

    // Handle timezone change
    const handleTimezoneChange = async (timezone: ITimezoneOption | string) => {
        setSelectedTimezone(timezone);
        setSavingTimezone(true);
        const previousTimezone = preferences.timezone || localTimezone;
        try {
            const tzValue = typeof timezone === 'string' ? timezone : timezone.value;
            const response = await savePreferencesApiV1OrganizationsPreferencesPut({
                body: {
                    timezone: tzValue,
                },
            });
            if (response.error) {
                throw new Error('Failed to save timezone');
            }
            setPreferences(response.data || { ...preferences, timezone: tzValue });
        } catch (error) {
            console.error('Failed to save timezone:', error);
            setSelectedTimezone(previousTimezone);
        } finally {
            setSavingTimezone(false);
        }
    };

    // Update timezone when organization preferences load.
    useEffect(() => {
        fetchPreferences();
    }, [fetchPreferences]);

    useEffect(() => {
        fetchAgentFilterOptions();
    }, [fetchAgentFilterOptions]);

    useEffect(() => {
        setActiveFilters(currentFilters => {
            let changed = false;
            const nextFilters = currentFilters.map(filter => {
                const updatedAttribute = availableUsageFilterAttributes.find(
                    attribute => attribute.id === filter.attribute.id
                );

                if (!updatedAttribute || updatedAttribute === filter.attribute) {
                    return filter;
                }

                changed = true;
                return {
                    ...filter,
                    attribute: updatedAttribute,
                };
            });

            return changed ? nextFilters : currentFilters;
        });
    }, [availableUsageFilterAttributes]);

    // La recherche part 400 ms après la dernière frappe, à partir de 3 lettres ; vider la case efface la recherche.
    useEffect(() => {
        const terme = recherche.trim();
        if (terme === rechercheAppliquee || (terme.length > 0 && terme.length < 3)) return;
        const minuteur = setTimeout(() => {
            rechercheRef.current = terme;
            setRechercheAppliquee(terme);
            setCurrentPage(1);
            updateUrlParams({ page: 1, filters: appliedFilters, sortBy, sortOrder });
        }, 400);
        return () => clearTimeout(minuteur);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [recherche]);

    // Initial load - fetch when auth becomes available
    useEffect(() => {
        if (auth.isAuthenticated) {
            fetchUsageHistory(currentPage, appliedFilters, sortBy, sortOrder);
        }
    }, [auth.isAuthenticated, currentPage, appliedFilters, sortBy, sortOrder, rechercheAppliquee, fetchUsageHistory]);

    // Fetch daily usage when organizationPricing becomes available
    useEffect(() => {
        if (auth.isAuthenticated && organizationPricing?.price_per_second_usd) {
            fetchDailyUsage();
        }
    }, [auth.isAuthenticated, organizationPricing, fetchDailyUsage]);

    // Update URL with query parameters
    const updateUrlParams = useCallback((params: {
        page?: number;
        filters?: ActiveFilter[];
        sortBy?: string | null;
        sortOrder?: 'asc' | 'desc';
    }) => {
        const newParams = new URLSearchParams();

        if (params.page !== undefined) {
            newParams.set('page', params.page.toString());
        }

        if (rechercheRef.current) {
            newParams.set('q', rechercheRef.current);
        }

        if (params.sortBy) {
            newParams.set('sort_by', params.sortBy);
            newParams.set('sort_order', params.sortOrder || 'desc');
        }

        // Add filters to URL if present
        if (params.filters && params.filters.length > 0) {
            const filterString = encodeFiltersToURL(params.filters);
            if (filterString) {
                const filterParams = new URLSearchParams(filterString);
                filterParams.forEach((value, key) => newParams.set(key, value));
            }
        }

        router.push(`/usage?${newParams.toString()}`);
    }, [router]);

    const handleApplyFilters = useCallback(async () => {
        setIsExecutingFilters(true);
        setCurrentPage(1); // Reset to first page when applying filters
        setAppliedFilters(activeFilters);
        updateUrlParams({ page: 1, filters: activeFilters, sortBy, sortOrder });
        await fetchUsageHistory(1, activeFilters, sortBy, sortOrder);
        setIsExecutingFilters(false);
    }, [activeFilters, fetchUsageHistory, updateUrlParams, sortBy, sortOrder]);

    const handleFiltersChange = useCallback((filters: ActiveFilter[]) => {
        setActiveFilters(filters);
    }, []);

    const handleClearFilters = useCallback(async () => {
        setIsExecutingFilters(true);
        setCurrentPage(1);
        setActiveFilters([]);
        setAppliedFilters([]);
        updateUrlParams({ page: 1, filters: [], sortBy, sortOrder }); // Clear filters from URL
        await fetchUsageHistory(1, [], sortBy, sortOrder); // Fetch all runs without filters
        setIsExecutingFilters(false);
    }, [fetchUsageHistory, updateUrlParams, sortBy, sortOrder]);

    // Handle page change
    const handlePageChange = (newPage: number) => {
        setCurrentPage(newPage);
        updateUrlParams({ page: newPage, filters: appliedFilters, sortBy, sortOrder });
        fetchUsageHistory(newPage, appliedFilters, sortBy, sortOrder);
    };

    // Toggle sort direction on repeat clicks, otherwise start descending.
    // The fetch effect above picks up the new state; page resets to 1 because
    // the ordering of every page changes.
    const handleSort = useCallback((field: string) => {
        const newSortOrder = sortBy === field && sortOrder === 'desc' ? 'asc' : 'desc';
        setSortBy(field);
        setSortOrder(newSortOrder);
        setCurrentPage(1);
        updateUrlParams({ page: 1, filters: appliedFilters, sortBy: field, sortOrder: newSortOrder });
    }, [sortBy, sortOrder, appliedFilters, updateUrlParams]);

    const timezoneValue = typeof selectedTimezone === 'string' ? selectedTimezone : selectedTimezone.value;
    const effectiveTimezone = timezoneValue || localTimezone;

    // Format duration for display
    const formatDuration = (seconds: number) => {
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        if (minutes === 0) return `${remainingSeconds}s`;
        if (remainingSeconds === 0) return `${minutes}m`;
        return `${minutes}m ${remainingSeconds}s`;
    };

    const lignes = usageHistory?.runs ?? [];
    const avecCout = Boolean(organizationPricing?.price_per_second_usd);
    // Les en-têtes « Durée », « Version » et « Note » trient : la flèche dit le sens courant.
    const enteteTriable = (champ: string, titre: string) => (
        <button type="button" className="inline-flex cursor-pointer items-center gap-1 hover:font-semibold" onClick={() => handleSort(champ)}>
            {titre}
            {sortBy === champ ? (
                sortOrder === 'asc' ? <ArrowUp className="size-3.5" /> : <ArrowDown className="size-3.5" />
            ) : (
                <ArrowUpDown className="size-3.5" />
            )}
        </button>
    );
    const enteteDuree = enteteTriable('duration', t({ en: 'Duration', fr: 'Durée' }));
    const canaux: Record<string, { en: string; fr: string }> = {
        site: { en: 'Site', fr: 'Site' },
        telephony: { en: 'Phone', fr: 'Téléphone' },
        web: { en: 'Web', fr: 'Web' },
        chat: { en: 'Chat', fr: 'Écrit' },
        simulated: { en: 'Simulated', fr: 'Simulé' },
    };

    return (
        <PageStudio>
            <TitrePage
                titre={t({ en: 'Conversations', fr: 'Conversations' })}
                info={t({
                    en: 'Every call across all the agents, tests included. Use the filters to narrow them down. The search reads the 2,000 most recent calls of the period (the last 30 days unless you set a start date), 3 letters at least.',
                    fr: "Tous les appels, essais compris, tous les agents confondus. Les filtres resserrent la liste. La recherche lit les 2 000 appels les plus récents de la période (les 30 derniers jours sans date de début), 3 lettres au moins.",
                })}
                action={
                    <div className="flex items-center gap-2">
                        <Globe className="size-4 text-muted-foreground" aria-hidden />
                        <div className="w-[300px]">
                                        <TimezoneSelect
                                            instanceId={timezoneSelectId}
                                            value={selectedTimezone}
                                            onChange={handleTimezoneChange}
                                            isDisabled={savingTimezone || preferencesLoading}
                                            placeholder={preferencesLoading ? "Loading..." : "Select timezone"}
                                            styles={{
                                                control: (base, state) => ({
                                                    ...base,
                                                    minHeight: '36px',
                                                    fontSize: '14px',
                                                    backgroundColor: 'var(--background)',
                                                    borderColor: state.isFocused ? 'var(--ring)' : 'var(--border)',
                                                    boxShadow: state.isFocused ? '0 0 0 2px color-mix(in srgb, var(--ring) 20%, transparent)' : 'none',
                                                    '&:hover': {
                                                        borderColor: 'var(--border)',
                                                    },
                                                }),
                                                menu: (base) => ({
                                                    ...base,
                                                    zIndex: 9999,
                                                    backgroundColor: 'var(--popover)',
                                                    border: '1px solid var(--border)',
                                                    boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
                                                }),
                                                menuList: (base) => ({
                                                    ...base,
                                                    backgroundColor: 'var(--popover)',
                                                    padding: 0,
                                                }),
                                                option: (base, state) => ({
                                                    ...base,
                                                    backgroundColor: state.isSelected
                                                        ? 'var(--accent)'
                                                        : state.isFocused
                                                        ? 'var(--accent)'
                                                        : 'var(--popover)',
                                                    color: 'var(--foreground)',
                                                    cursor: 'pointer',
                                                    '&:active': {
                                                        backgroundColor: 'var(--accent)',
                                                    },
                                                }),
                                                singleValue: (base) => ({
                                                    ...base,
                                                    color: 'var(--foreground)',
                                                }),
                                                input: (base) => ({
                                                    ...base,
                                                    color: 'var(--foreground)',
                                                }),
                                                placeholder: (base) => ({
                                                    ...base,
                                                    color: 'var(--muted-foreground)',
                                                }),
                                                indicatorSeparator: (base) => ({
                                                    ...base,
                                                    backgroundColor: 'var(--border)',
                                                }),
                                                dropdownIndicator: (base) => ({
                                                    ...base,
                                                    color: 'var(--muted-foreground)',
                                                    '&:hover': {
                                                        color: 'var(--foreground)',
                                                    },
                                                }),
                                            }}
                                        />
                        </div>
                    </div>
                }
            />

            {avecCout && <DailyUsageTable data={dailyUsage} isLoading={isLoadingDaily} />}

            <div className="space-y-3">
                <div className="relative w-full max-w-72">
                    <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                    <Input
                        value={recherche}
                        onChange={(e) => setRecherche(e.target.value)}
                        maxLength={80}
                        aria-label={t({ en: 'Search in the transcripts', fr: 'Chercher dans les transcriptions' })}
                        placeholder={t({ en: 'Search a word in the transcripts', fr: 'Chercher un mot dans les transcriptions' })}
                        className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
                    />
                </div>
                <FilterBuilder
                    availableAttributes={availableUsageFilterAttributes}
                    activeFilters={activeFilters}
                    onFiltersChange={handleFiltersChange}
                    onApplyFilters={handleApplyFilters}
                    onClearFilters={handleClearFilters}
                    isExecuting={isExecutingFilters}
                />
                {appliedFilters.length > 0 && (
                    <div className="flex justify-end">
                        <Button variant="outline" size="sm" onClick={handleDownloadReport} disabled={isDownloadingReport}>
                            <Download className="size-4" />
                            {isDownloadingReport
                                ? t({ en: 'Preparing...', fr: 'Préparation...' })
                                : t({ en: 'Download filtered results', fr: 'Télécharger les résultats filtrés' })}
                        </Button>
                    </div>
                )}
            </div>

            {historyFailed && !isLoadingHistory ? (
                <EtatVide cas="erreur" reessayer={() => void fetchUsageHistory(currentPage, appliedFilters, sortBy, sortOrder)} />
            ) : isLoadingHistory && usageHistory === null ? (
                <EtatVide cas="chargement" />
            ) : lignes.length > 0 ? (
                <div className={isLoadingHistory ? 'opacity-60' : undefined}>
                    <Tableau
                        colonnes={[
                            { titre: t({ en: 'When', fr: 'Quand' }) },
                            { titre: t({ en: 'Agent', fr: 'Agent' }) },
                            { titre: enteteTriable('version', t({ en: 'Version', fr: 'Version' })) },
                            { titre: t({ en: 'Caller', fr: 'Client' }) },
                            { titre: t({ en: 'Reason', fr: 'Motif' }) },
                            { titre: t({ en: 'Summary', fr: 'Résumé' }) },
                            { titre: t({ en: 'Channel', fr: 'Canal' }) },
                            { titre: t({ en: 'Outcome', fr: 'Issue' }) },
                            { titre: enteteDuree, droite: true },
                            { titre: t({ en: 'Latency', fr: 'Latence' }), droite: true },
                            { titre: enteteTriable('judge_note', t({ en: 'Grade', fr: 'Note' })), droite: true },
                            { titre: t({ en: 'Judged by', fr: 'Jugé par' }) },
                            ...(avecCout ? [{ titre: t({ en: 'Cost (USD)', fr: 'Coût (USD)' }), droite: true }] : []),
                            { titre: t({ en: 'Media', fr: 'Médias' }), droite: true },
                        ]}
                    >
                        {lignes.map((run) => (
                            <Ligne key={run.id} href={`/workflow/${run.workflow_id}/run/${run.id}`}>
                                <Cellule principale sous={`#${run.id}`}>
                                    <DateRelative valeur={run.created_at} fuseau={effectiveTimezone} />
                                </Cellule>
                                <Cellule>{run.workflow_name || t({ en: 'Unknown', fr: 'Inconnu' })}</Cellule>
                                <Cellule>{run.version != null ? `v${run.version}` : '-'}</Cellule>
                                <Cellule sous={run.client ? (run.call_type === 'inbound' ? run.caller_number : run.called_number) || undefined : undefined}>
                                    {run.client || (run.call_type === 'inbound' ? run.caller_number : run.called_number) || '-'}
                                </Cellule>
                                <Cellule>{run.motif || '-'}</Cellule>
                                <Cellule className="max-w-72 whitespace-normal">
                                    {/* N3b : la synthèse de l'après-appel réduite à deux phrases, sinon le résumé du modèle ; jamais rien d'inventé. */}
                                    <span data-resume-appel={run.resume_source ?? "aucun"} title={run.resume ?? undefined} className="line-clamp-2">
                                        {run.resume || '-'}
                                    </span>
                                </Cellule>
                                <Cellule>
                                    <span className="inline-flex items-center gap-2">
                                        <CallTypeCell mode={run.mode} callType={run.call_type} />
                                        {run.canal && canaux[run.canal] ? t(canaux[run.canal]) : ''}
                                    </span>
                                </Cellule>
                                <Cellule>{run.disposition || '-'}</Cellule>
                                <Cellule droite>{formatDuration(run.call_duration_seconds)}</Cellule>
                                <Cellule droite>
                                    {/* N3a : la latence moyenne d'un tour et le pire tour, rangées à la fin de l'appel ; un appel sans mesure le dit. */}
                                    {(() => {
                                        const l = run.latence as { moyenne_ms?: number; pire_ms?: number } | null | undefined;
                                        return l && typeof l.moyenne_ms === 'number' ? (
                                            <span data-latence="mesuree" title={`${t({ en: 'worst turn', fr: 'pire tour' })} ${((l.pire_ms ?? l.moyenne_ms) / 1000).toFixed(1)} s`} className="tabular-nums">
                                                {(l.moyenne_ms / 1000).toFixed(1)} s
                                            </span>
                                        ) : (
                                            <span data-latence="non-mesuree" className="text-muted-foreground">
                                                {t({ en: 'not measured', fr: 'non mesuré' })}
                                            </span>
                                        );
                                    })()}
                                </Cellule>
                                <Cellule droite><NoteJuge note={run.note_juge ?? null} /></Cellule>
                                <Cellule>{run.juge_par || '-'}</Cellule>
                                {avecCout && (
                                    <Cellule droite>
                                        {run.charge_usd !== undefined && run.charge_usd !== null ? `$${run.charge_usd.toFixed(2)}` : '-'}
                                    </Cellule>
                                )}
                                <Cellule droite>
                                    {/* Le bouton ouvre l'aperçu : il ne doit pas ouvrir la ligne. */}
                                    <span className="inline-flex" onClick={(e) => e.stopPropagation()}>
                                        <MediaPreviewButton
                                            recordingUrl={run.recording_url}
                                            transcriptUrl={run.transcript_url}
                                            runId={run.id}
                                            onOpenPreview={mediaPreview.openPreview}
                                        />
                                    </span>
                                </Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                    {appliedFilters.length > 0 && usageHistory && (
                        <p className="pt-3 text-sm text-muted-foreground">
                            {t({ en: 'Total for the filtered period:', fr: 'Total de la période filtrée :' })}{' '}
                            <span className="font-medium text-foreground">
                                {usageHistory.total_dograh_tokens.toLocaleString()} Dograh Tokens
                            </span>
                            {' · '}
                            <span className="font-medium text-foreground">{formatDuration(usageHistory.total_duration_seconds)}</span>
                        </p>
                    )}
                    {usageHistory && (
                        <BarrePagination
                            total={usageHistory.total_count}
                            page={currentPage - 1}
                            parPage={50}
                            changerPage={(p) => handlePageChange(p + 1)}
                        />
                    )}
                </div>
            ) : appliedFilters.length > 0 || rechercheAppliquee ? (
                <EtatVide cas="filtre" recherche={rechercheAppliquee} effacer={() => { setRecherche(''); rechercheRef.current = ''; setRechercheAppliquee(''); void handleClearFilters(); }} />
            ) : (
                <EtatVide cas="premier" icone={PhoneIncoming} titre={t({ en: 'No call yet', fr: 'Aucun appel encore' })} />
            )}

            {mediaPreview.dialog}
        </PageStudio>
    );
}
