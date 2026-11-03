'use client';

import {
    Check,
    ChevronRight,
    Copy,
    Download,
    ExternalLink,
    Phone,
    Star,
} from 'lucide-react';
import Link from 'next/link';
import { useParams, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import WorkflowLayout from '@/app/workflow/WorkflowLayout';
import {
    getWorkflowApiV1WorkflowFetchWorkflowIdGet,
    getWorkflowRunApiV1WorkflowWorkflowIdRunsRunIdGet,
} from '@/client/sdk.gen';
import { BoutonCreerUnTest } from '@/components/builder/tests/BoutonCreerUnTest';
import { BilanGreffier } from '@/components/mark/BilanGreffier';
import { JournalDesEvenements } from '@/components/mark/conversation/JournalDesEvenements';
import { LecteurConversation } from '@/components/mark/conversation/LecteurConversation';
import { titreDeLaConversation } from '@/components/mark/conversation/titre';
import { FenetreDuRun, LigneNue, useAnalyseDuRun, VueTranscription } from '@/components/mark/fenetre-du-run/FenetreDuRun';
import { PhrasesDuCode } from '@/components/mark/groupe/PhrasesDuCode';
import { TraceDesAgents } from '@/components/mark/groupe/TraceDesAgents';
import { useLangue } from '@/components/mark/langue/langue';
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from '@/components/mark/studio/etat-vide';
import { useNomEspace } from '@/components/mark/studio/nom-espace';
import { OngletsPage } from '@/components/mark/studio/onglets-page';
import { EnteteStudio, PageStudio } from '@/components/mark/studio/shell-studio';
import { MediaPreviewButton, MediaPreviewDialog } from '@/components/MediaPreviewDialog';
import { Button } from '@/components/ui/button';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { ConversationRailFrame, RealtimeFeedback, WorkflowRunLogs } from '@/components/workflow/conversation';
import { WORKFLOW_RUN_MODES } from '@/constants/workflowRunModes';
import { useOrganizationTimezone } from '@/hooks/useOrganizationTimezone';
import { useAuth } from '@/lib/auth';
import { copyTextToClipboard } from '@/lib/clipboard';
import { formatDateTime } from '@/lib/dateTime';
import { downloadFile } from '@/lib/files';

interface WorkflowRunResponse {
    mode: string;
    created_at: string | null;
    is_completed: boolean;
    transcript_url: string | null;
    recording_url: string | null;
    user_recording_url: string | null;
    bot_recording_url: string | null;
    cost_info: {
        dograh_token_usage?: number | null;
        call_duration_seconds?: number | null;
    } | null;
    initial_context: Record<string, string | number | boolean | object> | null;
    gathered_context: Record<string, string | number | boolean | object> | null;
    logs: WorkflowRunLogs | null;
    annotations: Record<string, unknown> | null;
    /** [.mark] V1b : la version de l'agent jouée et la note du juge (route de l'appel). */
    version_number: number | null;
    note_juge: number | null;
}

type Contexte = Record<string, string | number | boolean | object> | null;

/** Le canal de l'appel, dit comme la maquette (Navigateur, Clavier, Téléphone…). */
function libelleDuCanal(mode: string | null | undefined, t: (texte: { en: string; fr: string }) => string) {
    if (!mode) return '';
    if (mode === WORKFLOW_RUN_MODES.SMALL_WEBRTC || mode === WORKFLOW_RUN_MODES.WEBRTC) return t({ en: 'Browser', fr: 'Navigateur' });
    if (mode === WORKFLOW_RUN_MODES.TEXTCHAT) return t({ en: 'Keyboard', fr: 'Clavier' });
    if (mode === WORKFLOW_RUN_MODES.SIMULATED) return t({ en: 'Simulated caller', fr: 'Appelant simulé' });
    return t({ en: 'Phone', fr: 'Téléphone' });
}

function formatDuration(seconds?: number | null, langue: 'fr' | 'en' = 'en') {
    if (seconds == null || Number.isNaN(seconds)) return '–';
    const total = Math.round(seconds);
    const mins = Math.floor(total / 60);
    const secs = total % 60;
    // [.mark] K2b : « 1 min 14 s » en français (maquette), « 1m 14s » en anglais.
    if (langue === 'fr') return mins === 0 ? `${secs} s` : `${mins} min ${secs} s`;
    if (mins === 0) return `${secs}s`;
    return `${mins}m ${secs}s`;
}

function getTranscriptMetrics(logs: WorkflowRunLogs | null, gatheredContext: Contexte) {
    const events = logs?.realtime_feedback_events ?? [];
    const userTurns = events.filter((event) => event.type === 'rtf-user-transcription' && event.payload.final).length;
    const botTurns = events.filter((event) => event.type === 'rtf-bot-text').length;
    const toolCalls = events.filter((event) => event.type === 'rtf-function-call-end').length;
    const nodeNames = new Set(
        events
            .map((event) => event.payload.node_name)
            .filter((nodeName): nodeName is string => Boolean(nodeName))
    );
    const visitedNodes = Array.isArray(gatheredContext?.nodes_visited)
        ? gatheredContext.nodes_visited.length
        : nodeNames.size;

    return { userTurns, botTurns, toolCalls, visitedNodes };
}

function CopyDebugIdButton({ label, value }: { label: string; value: string }) {
    const [copied, setCopied] = useState(false);
    const { t } = useLangue();

    const handleCopy = async () => {
        try {
            await copyTextToClipboard(value);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };

    return (
        <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-3 py-2">
            <div className="min-w-0">
                <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-muted-foreground">{label}</p>
                <p className="font-mono text-sm font-semibold text-foreground">{value}</p>
            </div>
            <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-7 w-7 shrink-0"
                onClick={handleCopy}
                aria-label={`${t({ en: 'Copy', fr: 'Copier' })} : ${label}`}
            >
                {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
        </div>
    );
}

/** Les mesures de l'appel, en lignes nues (l'onglet Coûts). */
function RunMetricsSection({
    costInfo,
    logs,
    gatheredContext,
}: {
    costInfo: WorkflowRunResponse['cost_info'];
    logs: WorkflowRunLogs | null;
    gatheredContext: Contexte;
}) {
    const metrics = getTranscriptMetrics(logs, gatheredContext);
    const { t, langue } = useLangue();

    return (
        <section data-testid="mesures-de-l-appel">
            <p className="pb-1 text-base font-semibold">{t({ en: 'Run metrics', fr: "Mesures de l'appel" })}</p>
            <div className="divide-y divide-border">
                <LigneNue libelle={t({ en: 'Duration', fr: 'Durée' })}>{formatDuration(costInfo?.call_duration_seconds, langue)}</LigneNue>
                <LigneNue libelle={t({ en: 'Caller turns', fr: "Tours de l'appelant" })}>{metrics.userTurns}</LigneNue>
                <LigneNue libelle={t({ en: 'Agent turns', fr: "Tours de l'agent" })}>{metrics.botTurns}</LigneNue>
                <LigneNue libelle={t({ en: 'Tool calls', fr: "Appels d'outils" })}>{metrics.toolCalls}</LigneNue>
                <LigneNue libelle={t({ en: 'Steps visited', fr: 'Étapes visitées' })}>{metrics.visitedNodes}</LigneNue>
            </div>
        </section>
    );
}

/** Un contexte (initial, recueilli, contrôle qualité) en lignes nues : une clé, sa valeur ; « Copier » rend le JSON entier. */
function ContextDisplay({ title, context }: { title: string; context: Contexte }) {
    const [copied, setCopied] = useState(false);
    const { t } = useLangue();

    const handleCopy = async () => {
        if (!context) return;
        try {
            await copyTextToClipboard(JSON.stringify(context, null, 2));
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };

    const entrees = context ? Object.entries(context) : [];

    return (
        <section data-testid="contexte-de-l-appel">
            <div className="flex min-h-9 items-center justify-between pb-1">
                <p className="text-base font-semibold">{title}</p>
                {entrees.length > 0 && (
                    <Button variant="ghost" size="sm" onClick={handleCopy} className="gap-2">
                        {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        {copied ? t({ en: 'Copied', fr: 'Copié' }) : t({ en: 'Copy', fr: 'Copier' })}
                    </Button>
                )}
            </div>
            {entrees.length === 0 ? (
                <p className="py-3 text-sm text-muted-foreground">{t({ en: 'No data', fr: 'Aucune donnée' })}</p>
            ) : (
                <div className="divide-y divide-border">
                    {entrees.map(([cle, valeur]) => (
                        <LigneNue key={cle} libelle={<span className="break-all font-mono text-xs">{cle}</span>}>
                            {typeof valeur === 'object' && valeur !== null ? (
                                <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">{JSON.stringify(valeur, null, 2)}</pre>
                            ) : (
                                <span className="break-words">{String(valeur)}</span>
                            )}
                        </LigneNue>
                    ))}
                </div>
            )}
        </section>
    );
}

/**
 * [.mark] U1 : l'adresse d'une conversation est `/conversations/<runId>?agent=<workflowId>` (aucune route d'API ne
 * donne l'agent d'une conversation à partir de son seul numéro) ; l'ancienne `/workflow/<id>/run/<runId>` y redirige.
 */
function useParametresDeLaConversation() {
    const params = useParams<{ workflowId?: string; runId: string }>();
    const agent = useSearchParams()?.get('agent');
    return { runId: params.runId, workflowId: params.workflowId ?? agent ?? '' };
}

export default function WorkflowRunPage() {
    const params = useParametresDeLaConversation();
    // [.mark] builder lot 6 : la page « À trier » ouvre l'appel sur la réplique à tester (?creer_test=<rang>).
    const demande = Number(useSearchParams()?.get('creer_test'));
    const rangDemande = Number.isInteger(demande) && demande >= 1 ? demande : undefined;
    const [isLoading, setIsLoading] = useState(true);
    const [enErreur, setEnErreur] = useState(false);
    const auth = useAuth();
    const organizationTimezone = useOrganizationTimezone();
    const [workflowRun, setWorkflowRun] = useState<WorkflowRunResponse | null>(null);
    const [workflowName, setWorkflowName] = useState<string | null>(null);
    const { t: tp, langue } = useLangue();
    const nomEspace = useNomEspace('labo', null);
    // [.mark] U3 : l'analyse du run est lue UNE fois, les onglets s'en partagent les blocs.
    const analyse = useAnalyseDuRun(Number(params.workflowId), Number(params.runId));

    // Redirect if not authenticated
    useEffect(() => {
        if (!auth.loading && !auth.isAuthenticated) {
            auth.redirectToLogin();
        }
    }, [auth]);

    const { openPreview, dialog } = MediaPreviewDialog();

    const lireLAppel = useCallback(async () => {
        if (!auth.isAuthenticated || auth.loading) return;

        setIsLoading(true);
        setEnErreur(false);
        setWorkflowName(null);
        const workflowId = Number(params.workflowId);
        const runId = Number(params.runId);

        try {
            const [runResponse, workflowResponse] = await Promise.all([
                getWorkflowRunApiV1WorkflowWorkflowIdRunsRunIdGet({
                    path: {
                        workflow_id: workflowId,
                        run_id: runId,
                    },
                }),
                getWorkflowApiV1WorkflowFetchWorkflowIdGet({
                    path: {
                        workflow_id: workflowId,
                    },
                }),
            ]);

            setWorkflowName(workflowResponse.data?.name ?? null);
            if (runResponse.error) setEnErreur(true);
            // La version et la note viennent de la route de l'appel ; le client d'API généré les porte une fois régénéré.
            const lu = (runResponse.data ?? {}) as { version_number?: number | null; note_juge?: number | null };
            const runData = {
                mode: runResponse.data?.mode ?? '',
                created_at: runResponse.data?.created_at ?? null,
                is_completed: runResponse.data?.is_completed ?? false,
                transcript_url: runResponse.data?.transcript_url ?? null,
                recording_url: runResponse.data?.recording_url ?? null,
                user_recording_url: runResponse.data?.user_recording_url ?? null,
                bot_recording_url: runResponse.data?.bot_recording_url ?? null,
                cost_info: runResponse.data?.cost_info ?? null,
                initial_context: runResponse.data?.initial_context as Record<string, string> | null ?? null,
                gathered_context: runResponse.data?.gathered_context as Record<string, string> | null ?? null,
                logs: runResponse.data?.logs as WorkflowRunLogs | null ?? null,
                annotations: runResponse.data?.annotations as Record<string, unknown> | null ?? null,
                version_number: lu.version_number ?? null,
                note_juge: lu.note_juge ?? null,
            };
            setWorkflowRun(runData);
        } catch {
            setEnErreur(true);
        } finally {
            setIsLoading(false);
        }
    }, [params.workflowId, params.runId, auth.isAuthenticated, auth.loading]);

    useEffect(() => {
        void lireLAppel();
    }, [lireLAppel]);

    let returnValue = null;
    const isTextChatRun = workflowRun?.mode === WORKFLOW_RUN_MODES.TEXTCHAT;
    const showRunDetailsView = Boolean(workflowRun?.is_completed || isTextChatRun);
    const workflowId = String(params.workflowId);
    const runId = String(params.runId);

    if (isLoading) {
        returnValue = (
            <PageStudio>
                <EtatVide cas="chargement" lignes={5} />
            </PageStudio>
        );
    }
    else if (enErreur) {
        returnValue = (
            <PageStudio>
                <EtatVide cas="erreur" reessayer={() => void lireLAppel()} />
            </PageStudio>
        );
    }
    else if (showRunDetailsView) {
        // [.mark] U3 : la page d'une conversation. Tout ce que montrait la fenêtre du run reste là, rangé en sept onglets
        // (Transcription, Journal des événements, Agents et outils, Phrases du code, Coûts, Contrôle qualité, Contexte),
        // « créer un test depuis cette réplique » dans la Transcription. Les volets restent montés ; l'analyse du run
        // est lue une seule fois et partagée entre les onglets.
        // V1b : la forme de la maquette (titre « Motif · Issue », lecteur, transcription et colonne de droite).
        const analyseLue = { analyse: analyse.analyse, erreur: analyse.erreur };
        const idAgent = Number(params.workflowId);
        const idRun = Number(params.runId);
        const nomDeLAgent = workflowName ?? `${tp({ en: 'Agent', fr: 'Agent' })} ${workflowId}`;
        const note = workflowRun?.note_juge ?? null;
        const noteDite = note === null ? null : langue === 'fr' ? String(note).replace('.', ',') : String(note);
        returnValue = (
            <PageStudio>
                <div data-page-conversation>
                    <EnteteStudio
                        nom={
                            <nav aria-label={tp({ en: 'Breadcrumb', fr: "Fil d'Ariane" })} className="flex min-w-0 flex-1 items-center gap-1.5 text-sm">
                                <Link href="/labo" className="truncate text-muted-foreground hover:font-medium hover:text-foreground">
                                    {nomEspace ?? tp({ en: 'Labo', fr: 'Labo' })}
                                </Link>
                                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
                                <Link href="/labo/conversations" className="truncate text-muted-foreground hover:font-medium hover:text-foreground">
                                    {tp({ en: 'Conversations', fr: 'Conversations' })}
                                </Link>
                                <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />
                                <span className="truncate font-medium">{tp({ en: 'Call no.', fr: 'Appel n°' })} {runId}</span>
                            </nav>
                        }
                        actions={
                            <>
                                <Button variant="outline" size="sm" asChild>
                                    <Link href={`/agents/${params.workflowId}`}>{tp({ en: 'Open the agent', fr: "Ouvrir l'agent" })}</Link>
                                </Button>
                                {!isTextChatRun && (
                                    <Button
                                        variant="outline"
                                        size="sm"
                                        onClick={() => downloadFile(workflowRun?.transcript_url ?? null)}
                                        disabled={!workflowRun?.transcript_url || !auth.isAuthenticated}
                                    >
                                        <Download className="size-3.5" /> {tp({ en: 'Transcript', fr: 'Transcription' })}
                                    </Button>
                                )}
                            </>
                        }
                    />
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
                        <h1 className="w-full text-2xl font-semibold tracking-tight" data-titre-conversation>
                            {titreDeLaConversation(workflowRun?.gathered_context ?? null, nomDeLAgent)}
                        </h1>
                        <span className="text-muted-foreground">
                            {nomDeLAgent}
                            {workflowRun?.version_number != null && ` · v${workflowRun.version_number}`}
                        </span>
                        <span className="text-muted-foreground">
                            {[
                                libelleDuCanal(workflowRun?.mode, tp),
                                workflowRun?.created_at ? formatDateTime(workflowRun.created_at, organizationTimezone, langue) : '',
                                workflowRun?.cost_info?.call_duration_seconds != null
                                    ? formatDuration(workflowRun.cost_info.call_duration_seconds, langue)
                                    : '',
                            ]
                                .filter(Boolean)
                                .join(' · ')}
                        </span>
                        {noteDite !== null && (
                            <span className="flex items-center gap-1.5" data-note-du-juge>
                                <Star className="size-4 fill-current text-(--acc)" /> {tp({ en: 'judge', fr: 'juge' })} {noteDite}/5
                            </span>
                        )}
                        <span className="ml-auto flex gap-2">
                            <CopyDebugIdButton label={tp({ en: 'Agent ID', fr: "N° de l'agent" })} value={workflowId} />
                            <CopyDebugIdButton label={tp({ en: 'Run ID', fr: "N° de l'appel" })} value={runId} />
                        </span>
                    </div>
                </div>

                <LecteurConversation
                    pisteAppelant={workflowRun?.user_recording_url ?? null}
                    pisteAgent={workflowRun?.bot_recording_url ?? null}
                    enregistrement={workflowRun?.recording_url ?? null}
                    ecrit={isTextChatRun}
                />

                <div className="space-y-6">
                    {/* L'essai d'un appelant simulé (scénario joué et verdict du juge) : seulement sur ce genre d'appel. */}
                    <FenetreDuRun workflowId={idAgent} runId={idRun} blocs={['simulation']} lue={analyseLue} />

                    <OngletsPage
                        defaut="transcription"
                        onglets={[
                            {
                                id: 'transcription',
                                titre: tp({ en: 'Transcript', fr: 'Transcription' }),
                                contenu: (
                                    <div data-onglet-conversation="transcription">
                                        <VueTranscription
                                            workflowId={idAgent}
                                            runId={idRun}
                                            recordingKey={workflowRun?.recording_url ?? null}
                                            lue={analyseLue}
                                            avant={
                                                <>
                                                    {!isTextChatRun && workflowRun?.recording_url && (
                                                        <div className="flex flex-wrap items-center gap-2">
                                                            <span className="text-sm text-muted-foreground">{tp({ en: 'Preview', fr: 'Aperçu' })} :</span>
                                                            <MediaPreviewButton
                                                                recordingUrl={workflowRun?.recording_url}
                                                                transcriptUrl={workflowRun?.transcript_url}
                                                                runId={idRun}
                                                                onOpenPreview={openPreview}
                                                            />
                                                        </div>
                                                    )}
                                                    {/* [.mark] builder lot 6 : créer un test depuis une réplique de cet appel */}
                                                    <BoutonCreerUnTest
                                                        workflowId={idAgent}
                                                        runId={idRun}
                                                        evenements={workflowRun?.logs?.realtime_feedback_events as never}
                                                        rangInitial={rangDemande}
                                                    />
                                                </>
                                            }
                                        />
                                    </div>
                                ),
                            },
                            {
                                id: 'journal',
                                titre: tp({ en: 'Event log', fr: 'Journal des événements' }),
                                contenu: (
                                    <div className="space-y-6" data-onglet-conversation="journal">
                                        <JournalDesEvenements evenements={workflowRun?.logs?.realtime_feedback_events} />
                                        <Collapsible>
                                            <CollapsibleTrigger className="cursor-pointer text-sm font-medium text-muted-foreground hover:font-semibold hover:text-foreground">
                                                {tp({ en: 'Detailed thread (messages, tools, hand-overs)', fr: 'Fil détaillé (messages, outils, passations)' })}
                                            </CollapsibleTrigger>
                                            <CollapsibleContent>
                                                <div className="mt-3 h-[60vh] min-h-0">
                                                    <ConversationRailFrame className="h-full">
                                                        <RealtimeFeedback mode="historical" logs={workflowRun?.logs ?? null} />
                                                    </ConversationRailFrame>
                                                </div>
                                            </CollapsibleContent>
                                        </Collapsible>
                                        <FenetreDuRun
                                            workflowId={idAgent}
                                            runId={idRun}
                                            blocs={['incidents', 'latence', 'chrono', 'reseau']}
                                            lue={analyseLue}
                                        />
                                    </div>
                                ),
                            },
                            {
                                id: 'agents',
                                titre: tp({ en: 'Agents and tools', fr: 'Agents et outils' }),
                                contenu: (
                                    <div className="space-y-6" data-onglet-conversation="agents">
                                        {/* [.mark] Lot 13 (agents-specialises): the agents of the call, its path and its hand-overs. */}
                                        <TraceDesAgents contexte={workflowRun?.gathered_context ?? null} />
                                        <FenetreDuRun
                                            workflowId={idAgent}
                                            runId={idRun}
                                            blocs={['parcours', 'modules', 'fiche']}
                                            lue={analyseLue}
                                        />
                                    </div>
                                ),
                            },
                            {
                                id: 'phrases',
                                titre: tp({ en: 'Code sentences', fr: 'Phrases du code' }),
                                contenu: (
                                    <div data-onglet-conversation="phrases">
                                        {/* [.mark] fiabilite-orchestration, lot 4 ter (F24) : les phrases dites par le code. */}
                                        <PhrasesDuCode contexte={(workflowRun?.gathered_context ?? null) as Record<string, unknown> | null} />
                                    </div>
                                ),
                            },
                            {
                                id: 'couts',
                                titre: tp({ en: 'Costs', fr: 'Coûts' }),
                                contenu: (
                                    <div className="space-y-6" data-onglet-conversation="couts">
                                        <RunMetricsSection
                                            costInfo={workflowRun?.cost_info ?? null}
                                            logs={workflowRun?.logs ?? null}
                                            gatheredContext={workflowRun?.gathered_context ?? null}
                                        />
                                        <FenetreDuRun workflowId={idAgent} runId={idRun} blocs={['fournisseurs']} lue={analyseLue} />
                                        {/* [.mark] The clerk's passes, failures and tokens (mode-prise-de-notes). */}
                                        <BilanGreffier fiche={workflowRun?.gathered_context ?? null} />
                                    </div>
                                ),
                            },
                            {
                                id: 'qualite',
                                titre: tp({ en: 'Quality control', fr: 'Contrôle qualité' }),
                                contenu: (
                                    <div className="space-y-6" data-onglet-conversation="qualite">
                                        <ContextDisplay
                                            title={tp({ en: 'Quality results', fr: 'Résultats du contrôle qualité' })}
                                            context={(workflowRun?.annotations ?? null) as Contexte}
                                        />
                                        {workflowRun?.gathered_context?.trace_url && (
                                            <Button asChild size="sm" variant="outline" className="gap-2">
                                                <a href={String(workflowRun.gathered_context.trace_url)} target="_blank" rel="noopener noreferrer">
                                                    <ExternalLink className="h-4 w-4" />
                                                    {tp({ en: 'View the trace', fr: 'Voir la trace' })}
                                                </a>
                                            </Button>
                                        )}
                                    </div>
                                ),
                            },
                            {
                                id: 'contexte',
                                titre: tp({ en: 'Context', fr: 'Contexte' }),
                                contenu: (
                                    <div className="grid gap-10 md:grid-cols-2" data-onglet-conversation="contexte">
                                        <ContextDisplay title={tp({ en: 'Initial context', fr: 'Contexte initial' })} context={workflowRun?.initial_context ?? null} />
                                        <ContextDisplay title={tp({ en: 'Gathered context', fr: 'Contexte recueilli' })} context={workflowRun?.gathered_context ?? null} />
                                    </div>
                                ),
                            },
                        ]}
                    />
                </div>
            </PageStudio>
        );
    }
    else {
        returnValue = (
            <PageStudio>
                <div className="flex flex-col items-center justify-center gap-3 py-16 text-center" data-testid="appel-sans-detail">
                    <Phone className="size-8 text-(--acc)" strokeWidth={1.75} />
                    <p className="flex items-center gap-1.5 text-base font-semibold">
                        {tp({ en: 'This call has no details yet', fr: "Cet appel n'a pas encore de détail" })}
                    </p>
                    <Button asChild variant="outline" size="sm">
                        <Link href={`/agents/${params.workflowId}`}>{tp({ en: 'Open the agent', fr: "Ouvrir l'agent" })}</Link>
                    </Button>
                </div>
            </PageStudio>
        );
    }

    return (
        <WorkflowLayout>
            {returnValue}
            {dialog}
        </WorkflowLayout>
    );
}
