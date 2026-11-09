import '@xyflow/react/dist/style.css';

import {
    Background,
    BackgroundVariant,
    MarkerType,
    MiniMap,
    type NodeChange,
    ReactFlow,
} from "@xyflow/react";
import { useRouter, useSearchParams } from 'next/navigation';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { notifier, useAgentCourant } from "@/components/mark/notifications";

import { createWorkflowDraftApiV1WorkflowWorkflowIdCreateDraftPost, getWorkflowApiV1WorkflowFetchWorkflowIdGet, getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet, listDocumentsApiV1KnowledgeBaseDocumentsGet, listRecordingsApiV1WorkflowRecordingsGet, listToolsApiV1ToolsGet,updateWorkflowApiV1WorkflowWorkflowIdPut } from '@/client';
import type { DocumentResponseSchema, RecordingResponseSchema, ToolResponse, WorkflowVersionResponse } from '@/client/types.gen';
// [.mark] builder-agent-vocal (lot 4): the « Builder AI » panel, its highlighting of the graph, the node menu.
import { appliquerLesOperations, grapheAAfficher, instantane, retirerLeSurlignage } from "@/components/builder/ecran/graphe";
import { MenuDuNoeud, type MenuOuvert } from "@/components/builder/ecran/MenuDuNoeud";
import { PanneauBuilder } from "@/components/builder/ecran/PanneauBuilder";
import { useBuilderEcran } from "@/components/builder/ecran/store";
import { useNodeSpecs } from "@/components/flow/renderer";
import { FlowEdge, FlowNode, NodeType } from "@/components/flow/types";
import { BandeauSelection, gestesDuGraphe } from "@/components/mark/graphe/gestes-graphe";
import { FilGroupe, GroupeSurCanevas } from "@/components/mark/graphe/GroupeSurCanevas";
import { BarreCanevas } from '@/components/mark/agent/BarreCanevas';
import { BarreOutilsGraphe } from "@/components/mark/graphe/BarreOutilsGraphe";
import { usePreferenceLocale, useStatistiquesDesEtapes } from "@/components/mark/graphe/hooks-graphe";
import { fermeUnCycle, liensEnBoucle } from "@/components/mark/graphe/sans-boucle";
import { latenceDeLEtape, partDesAppels } from "@/components/mark/graphe/statistiques-etapes";
import { useDecalagePanneau } from "@/components/mark/studio/panneau-droit";
import { ConfirmerSuppression } from "@/components/mark/studio/suppression-confirmee";
import { useOuvertureNoeud } from '@/components/mark/agent/ouverture-noeud';
import { libelleDuType } from "@/components/flow/nodes/GenericNode";
import { nomDeFonction } from "@/components/mark/graphe/VeriteDesActions";
import { ProposerLaPublicationDuGroupe } from '@/components/mark/groupe/PublierLeGroupe';
import { useLangue } from "@/components/mark/langue/langue";
import { Sheet, SheetContent } from '@/components/ui/sheet';
import { useOnboarding } from '@/context/OnboardingContext';
import { espaceRetenu } from '@/lib/espaceCourant';
import { ReglePhrase, WorkflowConfigurations } from '@/types/workflow-configurations';

import CustomEdge from "../../../components/flow/edges/CustomEdge";
import { GenericNode } from "../../../components/flow/nodes/GenericNode";
import { PhoneCallDialog } from './components/PhoneCallDialog';
import type { WorkflowRuntimeNodeTransition } from './components/workflow-tester/types';
import { type ModeEssai, WorkflowEditorHeader } from "./components/WorkflowEditorHeader";
import { WorkflowTesterPanel } from './components/WorkflowTesterPanel';
import { WorkflowProvider } from "./contexts/WorkflowContext";
import { useWorkflowState } from "./hooks/useWorkflowState";
import { useWorkflowStore } from "./stores/workflowStore";
import { layoutNodes } from './utils/layoutNodes';

const edgeTypes = {
    custom: CustomEdge,
};

const VERSIONS_PAGE_SIZE = 10;

interface RenderWorkflowProps {
    initialWorkflowName: string;
    workflowId: number;
    workflowUuid?: string;
    initialTotalRuns?: number | null;
    openTesterOnLoad?: boolean;
    initialFlow?: {
        nodes: FlowNode[];
        edges: FlowEdge[];
        viewport: {
            x: number;
            y: number;
            zoom: number;
        };
    };
    initialTemplateContextVariables?: Record<string, string>;
    initialWorkflowConfigurations?: WorkflowConfigurations;
    initialVersionNumber?: number | null;
    initialVersionStatus?: string | null;
    initialSelectedVersion?: WorkflowVersionResponse;
    user: { id: string; email?: string };
}

function RenderWorkflow({
    initialWorkflowName,
    workflowId,
    workflowUuid,
    initialTotalRuns,
    openTesterOnLoad = false,
    initialFlow,
    initialTemplateContextVariables,
    initialWorkflowConfigurations,
    initialVersionNumber,
    initialVersionStatus,
    initialSelectedVersion,
    user,
}: RenderWorkflowProps) {
    const router = useRouter();
    useAgentCourant(workflowId);
    const searchParams = useSearchParams();
    const { specs } = useNodeSpecs();
    const { hasCompletedAction } = useOnboarding();
    const [isPhoneCallDialogOpen, setIsPhoneCallDialogOpen] = useState(false);
    const [isTesterRailOpen, setIsTesterRailOpen] = useState(false);
    const [isTesterSheetOpen, setIsTesterSheetOpen] = useState(false);
    const [zoomPourCent, setZoomPourCent] = useState(80);
    const [isDesktopViewport, setIsDesktopViewport] = useState(false);
    const [versions, setVersions] = useState<WorkflowVersionResponse[]>([]);
    const [, setVersionsLoading] = useState(false);
    const [activeVersionId, setActiveVersionId] = useState<number | null>(initialSelectedVersion?.id ?? null);
    const hasAutoOpenedTester = useRef(false);
    // [.mark] builder-agent-vocal (lot 4): what the builder panel needs from this editor.
    const { t: tBuilder } = useLangue();
    const builderOuvert = useBuilderEcran((s) => s.ouvert);
    const builderAvant = useBuilderEcran((s) => s.avant);
    const builderOperations = useBuilderEcran((s) => s.operationsVives);
    const builderBascule = useBuilderEcran((s) => s.bascule);
    const [menuDuNoeud, setMenuDuNoeud] = useState<MenuOuvert | null>(null);
    // The panel and the tester rail share the right side: opening the builder leaves the room to it.
    useEffect(() => {
        if (builderOuvert) setIsTesterRailOpen(false);
    }, [builderOuvert]);
    // A new editor starts with a clean builder state; `?builder=1` (« Start with the Builder AI ») opens the panel.
    useEffect(() => {
        useBuilderEcran.getState().reinitialiser();
        if (searchParams.get('builder') === '1') useBuilderEcran.getState().ouvrir();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [workflowId]);
    // Version info that updates immediately from the GET/save/publish responses.
    const [currentVersionNumber, setCurrentVersionNumber] = useState<number | null>(initialVersionNumber ?? null);
    const [currentVersionStatus, setCurrentVersionStatus] = useState<string | null>(initialVersionStatus ?? null);
    const versionsFetched = useRef(false);
    const [documents, setDocuments] = useState<DocumentResponseSchema[] | undefined>(undefined);
    const [tools, setTools] = useState<ToolResponse[] | undefined>(undefined);
    const [recordings, setRecordings] = useState<RecordingResponseSchema[]>([]);
    const [activeRuntimeNodeId, setActiveRuntimeNodeId] = useState<string | null>(null);

    const {
        rfInstance,
        nodes,
        edges,
        workflowName,
        isDirty,
        workflowValidationErrors,
        templateContextVariables,
        setNodes,
        setEdges,
        setIsDirty,
        handleNodeSelect,
        saveWorkflow,
        workflowConfigurations,
        saveWorkflowConfigurations,
        onConnect,
        onEdgesChange,
        onNodesChange,
        onDelete,
        undo,
        redo,
        canUndo,
        canRedo,
    } = useWorkflowState({
        initialWorkflowName,
        workflowId,
        initialFlow,
        initialTemplateContextVariables,
        initialWorkflowConfigurations,
        user,
    });

    // Single generic component for every node type. Seed with core node types
    // so the initial render is stable before specs load, then merge in any
    // spec-defined or already-present node types so plugin integrations like
    // Tuner render without extra React registrations.
    const nodeTypes = useMemo(() => {
        const typeNames = new Set<string>([
            ...Object.values(NodeType),
            ...specs.map((spec) => spec.name),
            ...nodes.map((node) => node.type),
            ...(initialFlow?.nodes ?? []).map((node) => node.type),
        ]);
        return Object.fromEntries(
            Array.from(typeNames).map((typeName) => [typeName, GenericNode]),
        );
    }, [initialFlow?.nodes, nodes, specs]);

    // Derive hasDraft from the current version status
    const hasDraft = currentVersionStatus === "draft";

    // Fetch the first page of workflow versions, optionally forcing a refresh.
    // Pagination keeps the panel snappy when a workflow has accumulated a long
    // history — `workflow_json` is shipped per row, so loading hundreds at once
    // is expensive on the wire.
    const fetchVersions = useCallback(async (
        force = false,
        preserveActiveVersion = false,
    ) => {
        if (versionsFetched.current && !force) return;
        setVersionsLoading(true);
        try {
            const response = await getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({
                path: { workflow_id: workflowId },
                // Fetch one extra row so `hasMore` is exact. This also lets the
                // history panel reliably hide Compare on v1.
                query: { limit: VERSIONS_PAGE_SIZE + 1, offset: 0 },
            });
            if (response.error) {
                notifier.echec({ fr: "Historique illisible. Rechargez la page.", en: "Could not load version history. Reload the page." }, { erreur: response.error });
                return;
            }
            const data = response.data;
            if (data) {
                const page = data.slice(0, VERSIONS_PAGE_SIZE);
                setVersions(page);
                // Set active version to draft if exists, else published.
                // Both live on the newest page so the first fetch always sees them.
                const current = page.find((v) => v.status === "draft") ?? page.find((v) => v.status === "published");
                if (current) {
                    setActiveVersionId((existingActiveVersionId) => (
                        preserveActiveVersion && existingActiveVersionId !== null
                            ? existingActiveVersionId
                            : current.id
                    ));
                    setCurrentVersionNumber(current.version_number);
                    setCurrentVersionStatus(current.status);
                }
                versionsFetched.current = true;
            }
        } finally {
            setVersionsLoading(false);
        }
    }, [workflowId]);

    const navigateToVersion = useCallback((version: number | null) => {
        const query = new URLSearchParams(searchParams.toString());
        if (version === null) query.delete('version');
        else query.set('version', String(version));
        const suffix = query.toString();
        router.push(`/agents/${workflowId}${suffix ? `?${suffix}` : ''}`, { scroll: false });
    }, [router, searchParams, workflowId]);

    const handleSelectVersion = useCallback((version: WorkflowVersionResponse) => {
        const isCurrentVersion = version.status === 'draft'
            || (version.status === 'published' && !hasDraft);
        navigateToVersion(isCurrentVersion ? null : version.version_number);
    }, [hasDraft, navigateToVersion]);

    // Determine if we are viewing a historical (non-current) version.
    // The "current" version is the draft if one exists, otherwise the published version.
    // Anything else (archived, or published while a draft exists) is historical.
    const isViewingHistoricalVersion = useMemo(() => {
        // Explicit version links open a saved snapshot, including the latest release.
        if (initialSelectedVersion?.id === activeVersionId) return true;
        if (!activeVersionId || versions.length === 0) return false;
        const activeVersion = versions.find((v) => v.id === activeVersionId);
        if (!activeVersion) return false;
        if (activeVersion.status === "draft") return false;
        if (activeVersion.status === "published" && !hasDraft) return false;
        return true;
    }, [activeVersionId, versions, hasDraft, initialSelectedVersion]);

    useEffect(() => {
        if (!isViewingHistoricalVersion) {
            return;
        }
        setActiveRuntimeNodeId(null);
    }, [isViewingHistoricalVersion]);

    // Return to the draft version, creating one from published if needed
    const handleBackToDraft = useCallback(async () => {
        if (initialSelectedVersion) {
            navigateToVersion(null);
            return;
        }
        const existingDraft = versions.find((v) => v.status === "draft");
        if (existingDraft) {
            handleSelectVersion(existingDraft);
            return;
        }

        // No draft exists — ask the backend to create one from published
        const response = await createWorkflowDraftApiV1WorkflowWorkflowIdCreateDraftPost({
            path: { workflow_id: workflowId },
        });
        const draft = response.data;
        if (draft) {
            setCurrentVersionNumber(draft.version_number);
            setCurrentVersionStatus(draft.status);
            // Load draft nodes/edges via the Zustand store (same approach as handleSelectVersion)
            const flowNodes = (draft.workflow_json?.nodes ?? []) as FlowNode[];
            const flowEdges = (draft.workflow_json?.edges ?? []) as FlowEdge[];
            setNodes(flowNodes);
            setEdges(flowEdges);
            setActiveVersionId(draft.id);
            setIsDirty(false);
            // Refresh the version list so the new draft appears
            fetchVersions(true);
        }
    }, [versions, handleSelectVersion, workflowId, setNodes, setEdges, setIsDirty, fetchVersions, initialSelectedVersion, navigateToVersion]);

    // [.mark] Lot 12 (agents-specialises): the place of this agent in its group, for the node windows and
    // for the publication: publishing a main agent offers to publish the whole group (lot 10).
    const agentPrincipalId =
        typeof workflowConfigurations?.agent_principal_id === 'number' ? workflowConfigurations.agent_principal_id : null;
    const estPrincipal = Array.isArray(workflowConfigurations?.agents_specialises);
    // [.mark] modules-et-cerveaux (lot 5, M3): the steps' « Background work » box shows only when it is on.
    const travailActif = workflowConfigurations?.travail_actif === true;
    const [propositionGroupe, setPropositionGroupe] = useState(false);

    // After a successful publish, refresh the version list and update status
    const handlePublished = useCallback(() => {
        setCurrentVersionStatus("published");
        fetchVersions(true);
        if (estPrincipal) setPropositionGroupe(true);
    }, [fetchVersions, estPrincipal]);

    // K2 : la version que dit la barre (point vert publiée, creux brouillon) : celle qu'on regarde, sinon la courante.
    const versionAffichee = useMemo(() => {
        if (activeVersionId) {
            const v = versions.find((ver) => ver.id === activeVersionId)
                ?? (initialSelectedVersion?.id === activeVersionId ? initialSelectedVersion : undefined);
            if (v) return { numero: v.version_number ?? null, statut: v.status ?? null };
        }
        return { numero: currentVersionNumber, statut: currentVersionStatus };
    }, [activeVersionId, versions, currentVersionNumber, currentVersionStatus, initialSelectedVersion]);

    const testerDisabledReason = useMemo(() => {
        if (isViewingHistoricalVersion) {
            return "Return to the draft before starting a new test session.";
        }
        if (isDirty) {
            return "Save the latest draft before testing so the session uses the workflow you are looking at.";
        }
        if (workflowValidationErrors.length > 0) {
            return "Resolve the current validation errors before starting another test.";
        }
        return null;
    }, [isDirty, isViewingHistoricalVersion, workflowValidationErrors.length]);

    // [.mark] E36 : « Prompt général » ouvre la fenêtre du nœud global ; s'il n'existe pas, la barre le crée puis l'ouvre.
    const demanderOuverture = useOuvertureNoeud((s) => s.demander);
    const [ouvrirLeGlobalApresAjout, setOuvrirLeGlobalApresAjout] = useState(false);
    const noeudGlobal = nodes.find((n) => n.type === NodeType.GLOBAL_NODE);
    const handlePromptGeneral = useCallback(() => {
        if (noeudGlobal) {
            demanderOuverture(noeudGlobal.id);
            return;
        }
        setOuvrirLeGlobalApresAjout(true);
        handleNodeSelect(NodeType.GLOBAL_NODE);
    }, [noeudGlobal, demanderOuverture, handleNodeSelect]);
    useEffect(() => {
        if (ouvrirLeGlobalApresAjout && noeudGlobal) {
            setOuvrirLeGlobalApresAjout(false);
            demanderOuverture(noeudGlobal.id);
        }
    }, [ouvrirLeGlobalApresAjout, noeudGlobal, demanderOuverture]);
    // La bibliothèque est celle du Labo : le lien n'est proposé que depuis l'espace Labo.
    const [bibliothequeHref, setBibliothequeHref] = useState<string | undefined>(undefined);
    useEffect(() => {
        const espace = espaceRetenu();
        setBibliothequeHref(espace === 'labo' ? '/labo/bibliotheque' : undefined);
    }, []);

    // [.mark] U3 : « Try ▾ » choisit l'onglet du panneau d'essai ; `cle` change à chaque choix.
    const [modeEssai, setModeEssai] = useState<{ mode: ModeEssai; cle: number } | null>(null);
    const handleOpenTester = useCallback((mode?: ModeEssai) => {
        if (mode) setModeEssai((precedent) => ({ mode, cle: (precedent?.cle ?? 0) + 1 }));
        if (window.innerWidth >= 1280) {
            setIsTesterRailOpen(true);
            return;
        }
        setIsTesterSheetOpen(true);
    }, []);

    const shouldShowWebCallOnboarding = useMemo(() => {
        return (initialTotalRuns ?? 0) === 0 && !hasCompletedAction('web_call_started');
    }, [hasCompletedAction, initialTotalRuns]);

    // K2 : les onglets autres que le Parcours envoient ici leur « Essayer » (`?essai=audio|text|simulated|telephone`).
    const essaiDemande = searchParams.get('essai');
    const essaiJoue = useRef(false);
    useEffect(() => {
        if (essaiJoue.current || !essaiDemande) return;
        essaiJoue.current = true;
        if (essaiDemande === 'telephone') setIsPhoneCallDialogOpen(true);
        else if (essaiDemande === 'audio' || essaiDemande === 'text' || essaiDemande === 'simulated') handleOpenTester(essaiDemande);
    }, [essaiDemande, handleOpenTester]);

    // [.mark] Partie 3 (SA-L3a) : « Régler » dans « Prêt à publier » mène à l'étape exacte (`?etape=<identifiant>`) : elle est
    // sélectionnée et centrée dans le graphe, une seule fois.
    const etapeDemandee = searchParams.get('etape');
    const etapeMontree = useRef(false);
    useEffect(() => {
        if (etapeMontree.current || !etapeDemandee || !nodes.some((n) => n.id === etapeDemandee)) return;
        etapeMontree.current = true;
        setNodes(nodes.map((n) => ({ ...n, selected: n.id === etapeDemandee })));
        // Pas de nettoyage : la sélection change `nodes` et relancerait l'effet avant que le centrage ait eu lieu.
        setTimeout(() => rfInstance.current?.fitView({ nodes: [{ id: etapeDemandee }], padding: 0.6, duration: 300, maxZoom: 1 }), 120);
    }, [etapeDemandee, nodes, setNodes, rfInstance]);

    useEffect(() => {
        const syncViewport = () => {
            setIsDesktopViewport(window.innerWidth >= 1280);
        };

        syncViewport();
        window.addEventListener('resize', syncViewport);
        return () => window.removeEventListener('resize', syncViewport);
    }, []);

    useEffect(() => {
        if (hasAutoOpenedTester.current || !openTesterOnLoad || !shouldShowWebCallOnboarding || testerDisabledReason) {
            return;
        }

        handleOpenTester();
        hasAutoOpenedTester.current = true;
    }, [handleOpenTester, openTesterOnLoad, shouldShowWebCallOnboarding, testerDisabledReason]);

    // Fetch documents, tools, and recordings once for the entire workflow
    useEffect(() => {
        const fetchData = async () => {
            try {
                // Fetch documents
                const documentsResponse = await listDocumentsApiV1KnowledgeBaseDocumentsGet({
                    query: { limit: 100 },
                });
                if (documentsResponse.data) {
                    setDocuments(documentsResponse.data.documents);
                }

                // Fetch tools
                const toolsResponse = await listToolsApiV1ToolsGet({});
                if (toolsResponse.data) {
                    setTools(toolsResponse.data);
                }

                // Fetch org-level recordings
                try {
                    const recordingsResponse = await listRecordingsApiV1WorkflowRecordingsGet({
                        query: {},
                    });
                    if (recordingsResponse.data) {
                        setRecordings(recordingsResponse.data.recordings);
                    }
                } catch {
                    // Recordings API may not be available yet; silently ignore
                }
            } catch (error) {
                console.error('Failed to fetch documents and tools:', error);
            }
        };

        fetchData();
    }, [workflowId]);

    // Memoize defaultEdgeOptions to prevent unnecessary re-renders
    const defaultEdgeOptions = useMemo(() => ({
        type: "custom",
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--liaison-fleche)", width: 14, height: 14 },
    }), []);

    const displayNodes = useMemo(
        () =>
            nodes.map((node) =>
                node.id === activeRuntimeNodeId
                    ? {
                          ...node,
                          data: {
                              ...node.data,
                              runtime_active: true,
                          },
                      }
                    : node,
            ),
        [activeRuntimeNodeId, nodes],
    );

    // [.mark] builder-agent-vocal (lot 4) -----------------------------------------------------------------------------
    const lireLeGrapheDuBuilder = useCallback(() => {
        const etat = useWorkflowStore.getState();
        return instantane(etat.nodes, etat.edges);
    }, []);

    // Reads the agent's draft again (the builder saved it on the server) and puts it on the canvas.
    const rechargerLeBrouillon = useCallback(async () => {
        const reponse = await getWorkflowApiV1WorkflowFetchWorkflowIdGet({ path: { workflow_id: workflowId } });
        const definition = reponse.data?.workflow_definition;
        if (reponse.error || !definition) return false;
        setNodes((definition.nodes ?? []) as FlowNode[]);
        setEdges((definition.edges ?? []) as FlowEdge[]);
        setIsDirty(false);
        setCurrentVersionNumber(reponse.data?.version_number ?? null);
        setCurrentVersionStatus(reponse.data?.version_status ?? null);
        void fetchVersions(true);
        setTimeout(() => rfInstance.current?.fitView({ padding: 0.2, duration: 300, maxZoom: 0.8 }), 100);
        return true;
    }, [workflowId, setNodes, setEdges, setIsDirty, fetchVersions, rfInstance]);

    // « Refuse »: the graph from before becomes the draft again (a normal save, then read back).
    const restaurerLeGraphe = useCallback(async (graphe: { nodes: FlowNode[]; edges: FlowEdge[] }) => {
        const reponse = await updateWorkflowApiV1WorkflowWorkflowIdPut({
            path: { workflow_id: workflowId },
            body: {
                name: workflowName,
                workflow_definition: { ...graphe, viewport: rfInstance.current?.getViewport() ?? { x: 0, y: 0, zoom: 0.75 } },
            },
        });
        if (reponse.error) return false;
        return rechargerLeBrouillon();
    }, [workflowId, workflowName, rfInstance, rechargerLeBrouillon]);

    const contexteDuBuilder = useMemo(
        () => ({
            workflowId,
            lireLeGraphe: lireLeGrapheDuBuilder,
            recharger: rechargerLeBrouillon,
            restaurer: restaurerLeGraphe,
            appelerLAgent: () => setIsPhoneCallDialogOpen(true),
            essayerAuClavier: () => handleOpenTester("text"),
        }),
        [workflowId, lireLeGrapheDuBuilder, rechargerLeBrouillon, restaurerLeGraphe, handleOpenTester],
    );

    // What the canvas shows while the builder has changes to review: Sim-style highlighting, or the graph from before.
    const affichageDuBuilder = useMemo(() => {
        if (!builderAvant) return null;
        const apres = builderOperations.length ? appliquerLesOperations(builderAvant, builderOperations) : { nodes, edges };
        return grapheAAfficher(builderAvant, apres, builderBascule, {
            champs: (n) => `${n} ${tBuilder({ en: "field(s)", fr: "champ(s)" })}`,
        });
    }, [builderAvant, builderOperations, builderBascule, nodes, edges, tBuilder]);
    // React Flow reports « replace » changes built from the nodes it DISPLAYS (the highlighted copies): none of that may
    // reach the editor's own nodes, which are saved. A ghost (a node the builder removed, kept on screen) is not stored.
    const onNodesChangeDuBuilder = useCallback(
        (changes: NodeChange<FlowNode>[]) => {
            const connus = new Set(useWorkflowStore.getState().nodes.map((n) => n.id));
            const propres = (changes as { type: string; id?: string; item?: FlowNode }[]).flatMap((c) => {
                if (c.type !== 'replace') return [c];
                return c.id && c.item && connus.has(c.id) ? [{ ...c, item: retirerLeSurlignage(c.item) }] : [];
            });
            onNodesChange(propres as unknown as NodeChange<FlowNode>[]);
        },
        [onNodesChange],
    );
    // [.mark] T4 : annuler la sélection (Échap) ; lu dans le magasin au moment du geste, jamais pendant un rendu.
    const annulerLaSelection = useCallback(() => {
        const courants = useWorkflowStore.getState().nodes;
        if (courants.some((n) => n.selected)) useWorkflowStore.getState().setNodes(courants.map((n) => (n.selected ? { ...n, selected: false } : n)));
    }, []);
    const panneauOuvert = builderOuvert || isTesterRailOpen;
    // [.mark] K2b : les panneaux de droite flottent sur tout le cadre du studio, barre d'agent comprise (maquette `superpose`) :
    // ils s'y posent par un portail ; sans cadre (test, autre page), ils restent dans la zone du canevas.
    const [cadreStudio, setCadreStudio] = useState<HTMLElement | null>(null);
    useEffect(() => {
        setCadreStudio(document.getElementById('cadre-studio'));
    }, []);
    const noeudsDeBase = affichageDuBuilder ? affichageDuBuilder.nodes : displayNodes;
    const liaisonsAffichees = affichageDuBuilder ? affichageDuBuilder.edges : edges;

    // [.mark] Partie 3, sous-lot 20 : l'éditeur du graphe façon ElevenLabs (annuler, aimant, carte, recherche, statistiques, boucles).
    const [aimant, basculerAimant] = usePreferenceLocale("mark.graphe.aimant", false);
    const [carte, basculerCarte] = usePreferenceLocale("mark.graphe.carte", true);
    // Clôture, lot C : « Empêcher les boucles » est un réglage de l'agent (`empecher_boucles`), plus une préférence du navigateur.
    const boucles = workflowConfigurations?.empecher_boucles === true;
    const basculerBoucles = useCallback(async () => {
        if (!workflowConfigurations) return;
        try {
            await saveWorkflowConfigurations({ ...workflowConfigurations, empecher_boucles: !boucles }, workflowName);
            notifier.succes(
                !boucles
                    ? { fr: 'Boucles interdites entre les étapes.', en: 'Loops between steps are now forbidden.' }
                    : { fr: 'Boucles de nouveau permises entre les étapes.', en: 'Loops between steps are allowed again.' },
            );
        } catch (erreur) {
            notifier.echec(
                { fr: "Réglage non enregistré. Si la version en ligne est protégée, passez par une branche.", en: 'Setting not saved. If the live version is protected, use a branch.' },
                { erreur },
            );
        }
    }, [workflowConfigurations, saveWorkflowConfigurations, boucles, workflowName]);
    const [statsAllumees, setStatsAllumees] = useState(false);
    const statistiques = useStatistiquesDesEtapes(workflowId, statsAllumees);
    // Les statistiques se posent à l'affichage seulement (jamais dans les étapes enregistrées).
    const noeudsAffiches = useMemo(
        () =>
            statistiques
                ? noeudsDeBase.map((n) => {
                      const nom = String((n.data as { name?: string }).name ?? "");
                      const part = partDesAppels(statistiques, nom);
                      const latence = latenceDeLEtape(statistiques, nom);
                      return part === null ? n : { ...n, data: { ...n.data, stats_part: part, ...(latence ? { stats_latence: latence } : {}) } };
                  })
                : noeudsDeBase,
        [noeudsDeBase, statistiques],
    );
    const nombreEnBoucle = useMemo(() => (boucles ? liensEnBoucle(edges).length : 0), [boucles, edges]);
    const onConnectGardee = useCallback(
        (connexion: Parameters<typeof onConnect>[0]) => {
            const { source, target } = connexion;
            if (boucles && source && target && fermeUnCycle(useWorkflowStore.getState().edges, source, target)) {
                notifier.avertissement({
                    fr: "Cette liaison fermerait une boucle. Éteignez « Empêcher les boucles » pour la poser.",
                    en: "This link would close a loop. Turn off \"Forbid loops\" to add it.",
                });
                return;
            }
            onConnect(connexion);
        },
        [boucles, onConnect],
    );
    const reorganiser = useCallback(() => {
        const rangees = layoutNodes(nodes, edges, 'TB', rfInstance);
        // Comme un glissement terminé : le geste entre dans l'historique, « Annuler » remet les places d'avant.
        useWorkflowStore.getState().setNodes(
            rangees,
            rangees.map((n) => ({ type: 'position', id: n.id, position: n.position, dragging: false }) as NodeChange<FlowNode>),
        );
        setTimeout(() => rfInstance.current?.fitView({ padding: 0.2, duration: 250, maxZoom: 0.8 }), 60);
    }, [nodes, edges, rfInstance]);
    const montrerUneEtape = useCallback(
        (id: string) => {
            useWorkflowStore.getState().setNodes(useWorkflowStore.getState().nodes.map((n) => ({ ...n, selected: n.id === id })));
            setTimeout(() => rfInstance.current?.fitView({ nodes: [{ id }], padding: 0.6, duration: 300, maxZoom: 1 }), 60);
        },
        [rfInstance],
    );
    const { langue } = useLangue();
    const etapesCherchables = useMemo(
        () =>
            nodes.map((n) => {
                const spec = specs.find((s) => s.name === n.type);
                return { id: n.id, nom: String((n.data as { name?: string }).name ?? n.id), type: spec ? libelleDuType(spec, langue) : n.type };
            }),
        [nodes, specs, langue],
    );
    // Supprimer au clavier demande aussi confirmation (la barre au survol a la sienne).
    const [suppressionDemandee, setSuppressionDemandee] = useState<{ nombre: number; nom: string; reponse: (ok: boolean) => void } | null>(null);
    const avantSuppression = useCallback(
        ({ nodes: aSupprimer }: { nodes: FlowNode[]; edges: FlowEdge[] }) =>
            aSupprimer.length === 0
                ? Promise.resolve(true)
                : new Promise<boolean>((reponse) =>
                      setSuppressionDemandee({
                          nombre: aSupprimer.length,
                          nom: String((aSupprimer[0].data as { name?: string }).name ?? aSupprimer[0].id),
                          reponse,
                      }),
                  ),
        [],
    );
    const decalagePanneau = useDecalagePanneau();
    // Le panneau de droite s'ouvre ou s'élargit : la zone du graphe rétrécit ; le graphe glisse (sans toucher au zoom) pour garder
    // l'étape choisie entièrement visible (maquette `canevas.tsx`).
    useEffect(() => {
        const minuteur = setTimeout(() => {
            const instance = rfInstance.current;
            const choisie = useWorkflowStore.getState().nodes.find((n) => n.selected);
            if (!instance || !choisie) return;
            const mesuree = instance.getInternalNode(choisie.id);
            const largeur = mesuree?.measured?.width ?? 250;
            const hauteur = mesuree?.measured?.height ?? 100;
            instance.setCenter(choisie.position.x + largeur / 2, choisie.position.y + hauteur / 2, { zoom: instance.getZoom(), duration: 250 });
        }, 120);
        return () => clearTimeout(minuteur);
    }, [decalagePanneau, rfInstance]);

    // The nodes appear one by one: keep the whole graph in view while the operations arrive.
    useEffect(() => {
        if (builderOperations.length === 0) return;
        const minuteur = setTimeout(() => rfInstance.current?.fitView({ padding: 0.2, duration: 250, maxZoom: 0.8 }), 60);
        return () => clearTimeout(minuteur);
    }, [builderOperations.length, rfInstance]);

    const handleRuntimeNodeTransition = useCallback(
        (transition: WorkflowRuntimeNodeTransition) => {
            const nodeId = transition.nodeId;
            const instance = rfInstance.current;
            if (!nodeId || !instance) {
                return;
            }

            setActiveRuntimeNodeId(nodeId);

            if (!instance.viewportInitialized) {
                return;
            }

            void instance.fitView({
                nodes: [{ id: nodeId }],
                duration: 350,
                padding: 0.45,
                maxZoom: 0.9,
            });
        },
        [rfInstance],
    );

    // Guard saveWorkflow so it's a no-op when viewing a historical version.
    // This is the single safety net that covers every save path: header button,
    // Cmd+S, node edit dialogs, stale doc/tool cleanup, etc.
    // Uses the save response to immediately update version label and hasDraft.
    const guardedSaveWorkflow = useCallback(async (updateWorkflowDefinition?: boolean) => {
        if (isViewingHistoricalVersion) return;
        const result = await saveWorkflow(updateWorkflowDefinition);
        if (result) {
            // If the versions list has been fetched (user interacted with versioning
            // or published), refresh it so that activeVersionId points to the correct
            // version.  This is critical when a save creates a new draft from a
            // published version: without refreshing, activeVersionId would still
            // point to the old published version, causing isViewingHistoricalVersion
            // to incorrectly return true and lock the editor into read-only mode.
            if (versionsFetched.current) {
                await fetchVersions(true);
            } else {
                if (result.versionNumber != null) setCurrentVersionNumber(result.versionNumber);
                if (result.versionStatus) setCurrentVersionStatus(result.versionStatus);
            }
        }
    }, [saveWorkflow, isViewingHistoricalVersion, fetchVersions]);

    const renameWorkflow = useCallback(async (newName: string) => {
        // The header doesn't render the pencil until the page has mounted with
        // initial data, so workflowConfigurations is non-null by the time this
        // runs. Throw rather than silently sending fallback workflow configurations,
        // which would overwrite the saved server-side config.
        if (!workflowConfigurations) {
            throw new Error("Workflow configurations not loaded");
        }
        await saveWorkflowConfigurations(workflowConfigurations, newName);
    }, [saveWorkflowConfigurations, workflowConfigurations]);

    const updateTool = useCallback(
        (toolUuid: string, updater: (tool: ToolResponse) => ToolResponse) => {
            setTools((prev) =>
                prev?.map((tool) =>
                    tool.tool_uuid === toolUuid ? updater(tool) : tool,
                ),
            );
        },
        [],
    );

    // Memoize the context value to prevent unnecessary re-renders
    // [.mark] Lot E d'agent-leger-greffier: the record fields a step can label.
    const champsFiche = useMemo(
        () =>
            ((workflowConfigurations?.fiche_champs ?? []) as Array<{ nom?: string }>)
                .map((c) => c?.nom)
                .filter((n): n is string => typeof n === "string" && n !== ""),
        [workflowConfigurations?.fiche_champs],
    );
    // [.mark] Lot 11 de correctifs-apres-banc-commun (F-2): the tools that write a record field (booking) or undo it
    // (cancelling), as function names: a step that carries one has « Truth of actions » on by default.
    const outilsQuiEcrivent = useMemo(
        () =>
            ((workflowConfigurations?.fiche_champs ?? []) as Array<{ rempli_par_outil?: string | null; annule_par_outil?: string | null }>)
                .flatMap((c) => [c?.rempli_par_outil, c?.annule_par_outil])
                .filter((n): n is string => typeof n === "string" && n.trim() !== "")
                .map(nomDeFonction),
        [workflowConfigurations?.fiche_champs],
    );
    const ajouterOutil = useCallback((tool: ToolResponse) => {
        setTools((prev) => (prev?.some((t) => t.tool_uuid === tool.tool_uuid) ? prev : [...(prev ?? []), tool]));
    }, []);
    // [.mark] correctifs-apres-banc-v4, lot 5: the steps' section « Fixed sentences at this step ».
    const phrasesDeLEtape = useMemo(
        () => ({
            configuration: workflowConfigurations,
            etapes: nodes
                .map((n) => ({ id: n.id, nom: (n.data as { name?: unknown } | undefined)?.name }))
                .filter((e): e is { id: string; nom: string } => typeof e.nom === 'string' && e.nom.trim() !== ''),
            outilsUuids: [
                ...new Set(
                    nodes.flatMap((n) => {
                        const uuids = (n.data as { tool_uuids?: unknown } | undefined)?.tool_uuids;
                        return Array.isArray(uuids) ? uuids.filter((u): u is string => typeof u === 'string') : [];
                    }),
                ),
            ],
            peutGroupe: estPrincipal,
            enregistrer: async (regles: ReglePhrase[]) => {
                if (!workflowConfigurations) throw new Error('Workflow configurations not loaded');
                await saveWorkflowConfigurations({ ...workflowConfigurations, phrases_regles: regles }, workflowName);
            },
        }),
        [workflowConfigurations, nodes, estPrincipal, saveWorkflowConfigurations, workflowName],
    );
    const workflowContextValue = useMemo(() => ({
        saveWorkflow: guardedSaveWorkflow,
        documents,
        tools,
        updateTool,
        recordings,
        readOnly: isViewingHistoricalVersion,
        champsFiche,
        outilsQuiEcrivent,
        workflowId,
        agentPrincipalId,
        estPrincipal,
        travailActif,
        ajouterOutil,
        phrasesDeLEtape,
    }), [
        outilsQuiEcrivent,
        guardedSaveWorkflow,
        documents,
        tools,
        updateTool,
        recordings,
        champsFiche,
        isViewingHistoricalVersion,
        workflowId,
        agentPrincipalId,
        estPrincipal,
        travailActif,
        ajouterOutil,
        phrasesDeLEtape,
    ]);

    const panneauFlottant = (
        <div style={{ right: 8 + decalagePanneau }} className="absolute bottom-2 top-2 z-30 flex overflow-hidden rounded-xl border bg-card shadow-2xl">
            {builderOuvert && <PanneauBuilder contexte={contexteDuBuilder} noeuds={nodes} />}
            {isTesterRailOpen && (
                <aside className="hidden h-full w-[420px] shrink-0 xl:block">
                    <WorkflowTesterPanel
                        workflowId={workflowId}
                        initialContextVariables={templateContextVariables}
                        ficheDeLagent={workflowConfigurations?.etablissement_id ?? null}
                        disabled={testerDisabledReason !== null}
                        disabledReason={testerDisabledReason}
                        isVisible={isDesktopViewport}
                        onClose={() => setIsTesterRailOpen(false)}
                        onRuntimeNodeTransition={handleRuntimeNodeTransition}
                        modeDemande={modeEssai}
                    />
                </aside>
            )}
        </div>
    );
    const panneauPose = cadreStudio ? createPortal(panneauFlottant, cadreStudio) : panneauFlottant;

    return (
        <WorkflowProvider value={workflowContextValue}>
            <ProposerLaPublicationDuGroupe
                principalId={workflowId}
                ouvert={propositionGroupe}
                onOuvertChange={setPropositionGroupe}
            />
            <div className="flex h-full min-w-fit flex-col">
                {/* New Workflow Editor Header */}
                <WorkflowEditorHeader
                    workflowName={workflowName}
                    isDirty={isDirty}
                    workflowValidationErrors={workflowValidationErrors}
                    rfInstance={rfInstance}
                    workflowId={workflowId}
                    workflowUuid={workflowUuid}
                    saveWorkflow={guardedSaveWorkflow}
                    user={user}
                    onPhoneCallClick={() => setIsPhoneCallDialogOpen(true)}
                    onTestAgentClick={handleOpenTester}
                    versionNumber={versionAffichee.numero}
                    versionStatus={versionAffichee.statut}
                    isViewingHistoricalVersion={isViewingHistoricalVersion}
                    onBackToDraft={handleBackToDraft}
                    hasDraft={hasDraft}
                    onPublished={handlePublished}
                    renameWorkflow={renameWorkflow}
                    builder={{
                        ouvert: builderOuvert,
                        onToggle: () => useBuilderEcran.getState().basculerLePanneau(),
                        raisonDeBlocage: builderAvant
                            ? tBuilder({ en: "Review the builder's changes first.", fr: "Relisez d'abord les changements du builder." })
                            : null,
                    }}
                />

                {/* Workflow Canvas */}
                <div className="flex-1 min-h-0">
                    <div className="relative flex h-full min-w-0">
                        <div className={`min-w-0 flex-1 bg-(--canevas) ${panneauOuvert ? "lg:pr-[436px]" : ""}`}>
                        {/* [.mark] V1b : au clavier, Entrée sur un nœud (il prend le focus par Tab) ouvre sa fenêtre, comme le double-clic. */}
                        <div
                            className="relative h-full"
                            onKeyDown={(evenement) => {
                                const cible = evenement.target as HTMLElement;
                                if (evenement.key !== 'Enter' || !cible.classList?.contains('react-flow__node')) return;
                                const id = cible.getAttribute('data-id');
                                if (!id) return;
                                evenement.preventDefault();
                                demanderOuverture(id);
                            }}
                        >
                            <ReactFlow
                                key={activeVersionId ?? 'current'}
                                nodes={noeudsAffiches}
                                edges={liaisonsAffichees}
                                onNodeContextMenu={(evenement, noeud) => {
                                    evenement.preventDefault();
                                    setMenuDuNoeud({
                                        x: evenement.clientX,
                                        y: evenement.clientY,
                                        id: noeud.id,
                                        nom: String((noeud.data as { name?: string }).name ?? noeud.id),
                                    });
                                }}
                                onNodesChange={onNodesChangeDuBuilder}
                                onEdgesChange={onEdgesChange}
                                onDelete={onDelete}
                                nodeTypes={nodeTypes}
                                edgeTypes={edgeTypes}
                                onConnect={isViewingHistoricalVersion ? undefined : onConnectGardee}
                                onBeforeDelete={avantSuppression}
                                snapToGrid={aimant}
                                snapGrid={[20, 20]}
                                minZoom={0.2}
                                onMove={(_, vue) => setZoomPourCent(Math.round(vue.zoom * 100))}
                                onInit={(instance) => {
                                    rfInstance.current = instance;
                                    // Center the workflow on load
                                    setTimeout(() => {
                                        instance.fitView({ padding: 0.2, duration: 200, maxZoom: 0.8 });
                                    }, 0);
                                }}
                                defaultEdgeOptions={defaultEdgeOptions}
                                defaultViewport={initialFlow?.viewport}
                                nodesDraggable={!isViewingHistoricalVersion}
                                nodesConnectable={!isViewingHistoricalVersion}
                                edgesReconnectable={!isViewingHistoricalVersion}
                                zoomOnDoubleClick={false}
                                {...gestesDuGraphe(isViewingHistoricalVersion)}
                                deleteKeyCode={isViewingHistoricalVersion ? null : "Backspace"}
                            >
                                {carte && (
                                    <MiniMap
                                        pannable
                                        zoomable
                                        ariaLabel={tBuilder({ en: "Mini map", fr: "Carte miniature" })}
                                        className="rounded-lg! border! bg-card! shadow-sm!"
                                        maskColor="var(--canevas-point)"
                                        nodeColor="var(--liaison)"
                                        nodeStrokeColor="var(--liaison-survol)"
                                    />
                                )}
                                <GroupeSurCanevas agentId={workflowId} />
                                <Background
                                    variant={BackgroundVariant.Dots}
                                    gap={20}
                                    size={2}
                                    color="var(--canevas-point)"
                                />

                            </ReactFlow>

                            <FilGroupe agentId={workflowId} />
                            <BarreOutilsGraphe
                                lectureSeule={isViewingHistoricalVersion}
                                peutAnnuler={canUndo}
                                peutRetablir={canRedo}
                                onAnnuler={undo}
                                onRetablir={redo}
                                onReorganiser={reorganiser}
                                aimant={aimant}
                                onAimant={basculerAimant}
                                carte={carte}
                                onCarte={basculerCarte}
                                stats={statsAllumees}
                                onStats={() => setStatsAllumees((v) => !v)}
                                appelsLus={statistiques ? statistiques.appels : null}
                                boucles={boucles}
                                onBoucles={basculerBoucles}
                                enBoucle={nombreEnBoucle}
                                etapes={etapesCherchables}
                                onChoisirEtape={montrerUneEtape}
                            />
                            <BandeauSelection nombre={noeudsAffiches.filter((n) => n.selected).length} onAnnuler={annulerLaSelection} />
                            {/* [.mark] E36 : la barre flottante du canevas (prompt général, nœud, bibliothèque, zoom, ajuster, ranger) */}
                            <BarreCanevas
                                lectureSeule={isViewingHistoricalVersion}
                                zoom={zoomPourCent}
                                changementDuBuilder={Boolean(builderAvant)}
                                noeuds={nodes}
                                onPromptGeneral={handlePromptGeneral}
                                onAjouter={handleNodeSelect}
                                onZoomAvant={() => rfInstance.current?.zoomIn()}
                                onZoomArriere={() => rfInstance.current?.zoomOut()}
                                onAjuster={() => rfInstance.current?.fitView()}
                                onRanger={() => {
                                    setNodes(layoutNodes(nodes, edges, 'TB', rfInstance));
                                    setIsDirty(true);
                                }}
                                bibliothequeHref={bibliothequeHref}
                            />
                        </div>
                        </div>

                        {/* K2 : les panneaux de droite flottent au-dessus du canevas, comme la maquette (« superpose »). */}
                        {panneauOuvert && panneauPose}
                    </div>

                    <Sheet open={isTesterSheetOpen} onOpenChange={setIsTesterSheetOpen}>
                        <SheetContent side="right" className="w-full max-w-none p-0 sm:max-w-xl xl:hidden">
                            <WorkflowTesterPanel
                                workflowId={workflowId}
                                initialContextVariables={templateContextVariables}
                                ficheDeLagent={workflowConfigurations?.etablissement_id ?? null}
                                disabled={testerDisabledReason !== null}
                                disabledReason={testerDisabledReason}
                                isVisible={isTesterSheetOpen}
                                onRuntimeNodeTransition={handleRuntimeNodeTransition}
                                modeDemande={modeEssai}
                            />
                        </SheetContent>
                    </Sheet>
                </div>

                <MenuDuNoeud menu={menuDuNoeud} onFermer={() => setMenuDuNoeud(null)} />

                <ConfirmerSuppression
                    ouvert={suppressionDemandee !== null}
                    titre={
                        suppressionDemandee && suppressionDemandee.nombre > 1
                            ? tBuilder({ en: `Delete ${suppressionDemandee.nombre} steps?`, fr: `Supprimer ${suppressionDemandee.nombre} étapes ?` })
                            : tBuilder({ en: `Delete "${suppressionDemandee?.nom ?? ''}"?`, fr: `Supprimer « ${suppressionDemandee?.nom ?? ''} » ?` })
                    }
                    description={tBuilder({
                        en: 'The steps and their transitions leave the draft. "Undo" in the toolbar puts them back.',
                        fr: "Les étapes et leurs transitions sortent du brouillon. « Annuler » dans la barre d'outils les remet.",
                    })}
                    onFermer={() => {
                        suppressionDemandee?.reponse(false);
                        setSuppressionDemandee(null);
                    }}
                    onConfirmer={() => {
                        suppressionDemandee?.reponse(true);
                        setSuppressionDemandee(null);
                    }}
                />

                <PhoneCallDialog
                    open={isPhoneCallDialogOpen}
                    onOpenChange={setIsPhoneCallDialogOpen}
                    workflowId={workflowId}
                    user={user}
                />
            </div>
        </WorkflowProvider>
    );
}

// Memoize the component to prevent unnecessary re-renders when parent re-renders
export default React.memo(RenderWorkflow, (prevProps, nextProps) => {
    // Only re-render if these specific props change
    return (
        prevProps.workflowId === nextProps.workflowId &&
        prevProps.initialWorkflowName === nextProps.initialWorkflowName &&
        prevProps.user.id === nextProps.user.id
        // Note: We intentionally don't compare initialFlow, initialTemplateContextVariables,
        // or initialWorkflowConfigurations because they're only used for initialization
    );
});
