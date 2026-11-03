"use client";

import { Loader2, Mic, Phone, RefreshCw, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import { createWorkflowRunApiV1WorkflowWorkflowIdRunsPost } from "@/client/sdk.gen";
import { AppelantSimule, TitreOngletAppelantSimule } from "@/components/mark/appelant-simule/AppelantSimule";
import { useLangue } from "@/components/mark/langue/langue";
import { ChoixEtablissementEssai } from "@/components/mark/etablissements/ChoixEtablissementEssai";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WORKFLOW_RUN_MODES } from "@/constants/workflowRunModes";
import { useOnboarding } from "@/context/OnboardingContext";
import { useAuth } from "@/lib/auth";
import { cn, getRandomId } from "@/lib/utils";

import { AiSimulatorPlaceholder } from "./workflow-tester/AiSimulatorPlaceholder";
import { EmbeddedVoiceTester } from "./workflow-tester/EmbeddedVoiceTester";
import { ManualTextChatPanel } from "./workflow-tester/ManualTextChatPanel";
import { ChatModeToggle, DisabledNotice, EmptyState } from "./workflow-tester/shared";
import type { WorkflowRuntimeNodeTransition } from "./workflow-tester/types";
import { extractSdkErrorMessage } from "./workflow-tester/utils";

// [.mark] One tab of the tester panel: icon above a label that may wrap (lot 0, direct-et-passe-muette).
const ONGLET = "-mb-px h-auto flex-none cursor-pointer rounded-none border-0 border-b-2 border-transparent bg-transparent px-2.5 py-2 text-sm text-muted-foreground shadow-none hover:text-foreground data-[state=active]:border-primary data-[state=active]:bg-transparent data-[state=active]:font-medium data-[state=active]:text-foreground data-[state=active]:shadow-none";

interface WorkflowTesterPanelProps {
    workflowId: number;
    initialContextVariables?: Record<string, string>;
    disabled: boolean;
    disabledReason: string | null;
    isVisible?: boolean;
    className?: string;
    onClose?: () => void;
    onRuntimeNodeTransition?: (transition: WorkflowRuntimeNodeTransition) => void;
    // [.mark] Lot 11 (C8): the fiche the agent chose; with one, the test window offers no establishment.
    ficheDeLagent?: string | null;
    // [.mark] U3 (« Try ▾ » of the agent bar): the tab to show. `cle` changes at each choice, so choosing the same mode twice still applies.
    modeDemande?: { mode: "audio" | "text" | "simulated"; cle: number } | null;
}

export function WorkflowTesterPanel({
    workflowId,
    initialContextVariables,
    disabled,
    disabledReason,
    isVisible = true,
    className,
    onClose,
    onRuntimeNodeTransition,
    ficheDeLagent = null,
    modeDemande = null,
}: WorkflowTesterPanelProps) {
    const auth = useAuth();
    const { t } = useLangue();
    const { markActionCompleted } = useOnboarding();
    const { isAuthenticated, loading: authLoading, getAccessToken } = auth;
    const [accessToken, setAccessToken] = useState<string | null>(null);
    // [.mark] Third tab: the simulated caller (langwatch-et-fenetre-du-run, lot 3, L11).
    const [activeMode, setActiveMode] = useState<"audio" | "text" | "simulated">("audio");
    const [chatMode, setChatMode] = useState<"manual" | "simulated">("manual");
    const [chatSessionKey, setChatSessionKey] = useState(0);
    const [chatActive, setChatActive] = useState(false);
    const [voiceRunId, setVoiceRunId] = useState<number | null>(null);
    const [creatingVoiceRun, setCreatingVoiceRun] = useState(false);
    const [tokenReady, setTokenReady] = useState(false);
    // [.mark] The establishment the test plays (l-agent-travaille, E3). Empty: the agent's first.
    const [etablissementChoisi, setEtablissementEssai] = useState("");
    // With a fiche of its own the agent plays that one (the choice is not offered, so none is sent).
    const etablissementEssai = ficheDeLagent ? "" : etablissementChoisi;
    const contexteEssai = etablissementEssai
        ? { ...(initialContextVariables ?? {}), etablissement_id: etablissementEssai }
        : initialContextVariables;

    useEffect(() => {
        let ignore = false;

        const hydrateAccessToken = async () => {
            if (!isAuthenticated || authLoading) return;
            try {
                const token = await getAccessToken();
                if (!ignore) {
                    setAccessToken(token);
                }
            } catch (error) {
                if (!ignore) {
                    notifier.echec({ fr: "Test non démarré. Vérifiez le micro et réessayez.", en: "Test not started. Check the microphone and try again." }, { erreur: error });
                }
            } finally {
                if (!ignore) {
                    setTokenReady(true);
                }
            }
        };

        if (authLoading) {
            return;
        }

        if (!isAuthenticated) {
            setTokenReady(true);
            return;
        }

        hydrateAccessToken();

        return () => {
            ignore = true;
        };
    }, [authLoading, getAccessToken, isAuthenticated]);

    const createVoiceRun = useCallback(async () => {
        if (!accessToken || disabled) return;
        setCreatingVoiceRun(true);
        try {
            const response = await createWorkflowRunApiV1WorkflowWorkflowIdRunsPost({
                path: { workflow_id: workflowId },
                body: {
                    mode: WORKFLOW_RUN_MODES.SMALL_WEBRTC,
                    name: `WR-${getRandomId()}`,
                    ...(etablissementEssai ? { etablissement_id: etablissementEssai } : {}),
                },
            });

            if (response.error || !response.data?.id) {
                throw new Error(extractSdkErrorMessage(response.error, "Failed to create browser test run"));
            }

            markActionCompleted("web_call_started");
            setVoiceRunId(response.data.id);
            setActiveMode("audio");
        } catch (error) {
            notifier.echec({ fr: "Test interrompu. Relancez-le.", en: "Test interrupted. Start it again." }, { erreur: error });
        } finally {
            setCreatingVoiceRun(false);
        }
    }, [accessToken, disabled, etablissementEssai, markActionCompleted, workflowId]);

    const authUnavailableReason = tokenReady && !accessToken
        ? "Authentication is required before testing can start."
        : null;
    const effectiveDisabledReason = disabledReason ?? authUnavailableReason;
    const testerBlocked = disabled || authUnavailableReason !== null;

    const handleModeChange = (value: string) => {
        const mode = value as "audio" | "text" | "simulated";
        setActiveMode(mode);
        if (mode !== "audio") {
            // Leaving this tab unmounts EmbeddedVoiceTester, whose cleanup closes
            // the socket and peer connection — the call is over at that point and
            // the backend completes the run. A run may only be called once, so
            // release the id here; coming back mints a fresh one rather than
            // re-offering a finished run.
            setVoiceRunId(null);
        }
    };

    useEffect(() => {
        if (modeDemande) handleModeChange(modeDemande.mode);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [modeDemande?.cle]);

    return (
        <div className={cn("flex h-full min-h-0 flex-col bg-background", className)}>
            <Tabs
                value={activeMode}
                onValueChange={handleModeChange}
                className="min-h-0 flex-1 gap-0"
            >
                <div className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
                    <p className="flex-1 text-sm font-medium">{t({ en: "Try the agent", fr: "Essayer l'agent" })}</p>
                    {onClose ? (
                        <Button variant="ghost" size="icon" className="size-8" onClick={onClose} aria-label={t({ en: "Close the test panel", fr: "Fermer le panneau d'essai" })}>
                            <X className="size-4" />
                        </Button>
                    ) : null}
                </div>
                <ChoixEtablissementEssai
                    valeur={etablissementEssai}
                    ficheDeLagent={ficheDeLagent}
                    onChange={setEtablissementEssai}
                    desactive={voiceRunId !== null || chatActive}
                />
                <TabsList className="h-auto w-full justify-start gap-1 rounded-none border-b bg-transparent px-4 py-0">
                    <TabsTrigger value="audio" className={ONGLET}>
                        {t({ en: "Browser", fr: "Navigateur" })}
                    </TabsTrigger>
                    <TabsTrigger value="text" className={ONGLET}>
                        {t({ en: "Keyboard", fr: "Clavier" })}
                    </TabsTrigger>
                    <TabsTrigger value="simulated" className={ONGLET}>
                        <TitreOngletAppelantSimule />
                    </TabsTrigger>
                </TabsList>

                <TabsContent value="audio" className="min-h-0 flex-1 px-4 py-4">
                    <div className="flex h-full min-h-0 flex-col gap-3">
                        {!tokenReady ? (
                            <div className="space-y-4">
                                <Skeleton className="h-14 rounded-xl" />
                                <Skeleton className="h-80 rounded-xl" />
                            </div>
                        ) : !accessToken ? (
                            <DisabledNotice
                                reason={authUnavailableReason ?? "Authentication is required before browser tests can start."}
                            />
                        ) : voiceRunId ? (
                            <EmbeddedVoiceTester
                                workflowId={workflowId}
                                workflowRunId={voiceRunId}
                                initialContextVariables={contexteEssai}
                                accessToken={accessToken}
                                onReset={() => setVoiceRunId(null)}
                                onNodeTransition={onRuntimeNodeTransition}
                            />
                        ) : (
                            <>
                                {effectiveDisabledReason ? <DisabledNotice reason={effectiveDisabledReason} /> : null}
                                <EmptyState
                                    icon={<Mic className="h-7 w-7" />}
                                    title={t({ en: "Call in the browser", fr: "Appel dans le navigateur" })}
                                    action={
                                        <Button
                                            onClick={createVoiceRun}
                                            disabled={creatingVoiceRun || testerBlocked}
                                        >
                                            {creatingVoiceRun ? (
                                                <>
                                                    <Loader2 className="h-4 w-4 animate-spin" />
                                                    {t({ en: "Starting…", fr: "Démarrage…" })}
                                                </>
                                            ) : (
                                                <>
                                                    {t({ en: "Start the call", fr: "Lancer l'appel" })}
                                                </>
                                            )}
                                        </Button>
                                    }
                                />
                            </>
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="text" className="min-h-0 flex-1 px-4 py-3">
                    <div className="flex h-full min-h-0 flex-col gap-3">
                        <div className="flex items-center justify-between gap-2">
                            <ChatModeToggle value={chatMode} onChange={setChatMode} />
                            {chatMode === "manual" && chatActive ? (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => setChatSessionKey((value) => value + 1)}
                                    disabled={testerBlocked}
                                    className="h-7 px-2 text-xs text-muted-foreground hover:text-foreground"
                                >
                                    <RefreshCw className="h-3.5 w-3.5" />
                                    Reset
                                </Button>
                            ) : null}
                        </div>

                        {chatMode === "manual" ? (
                            <ManualTextChatPanel
                                key={chatSessionKey}
                                workflowId={workflowId}
                                ready={tokenReady && !!accessToken}
                                initialContextVariables={contexteEssai}
                                disabled={testerBlocked}
                                disabledReason={effectiveDisabledReason}
                                onActiveChange={setChatActive}
                                onNodeTransition={onRuntimeNodeTransition}
                            />
                        ) : (
                            <AiSimulatorPlaceholder disabledReason={effectiveDisabledReason} />
                        )}
                    </div>
                </TabsContent>

                <TabsContent value="simulated" className="min-h-0 flex-1 px-4 py-3">
                    {testerBlocked && effectiveDisabledReason ? (
                        <DisabledNotice reason={effectiveDisabledReason} />
                    ) : (
                        <AppelantSimule workflowId={workflowId} />
                    )}
                </TabsContent>
            </Tabs>

        </div>
    );
}
