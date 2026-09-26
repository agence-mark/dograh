"use client";

/**
 * [.mark] The agent settings page in 8 themes (chantier
 * reorganisation-ecran-reglages, decision D2, convention § 2).
 *
 * Called from Dograh's `settings/page.tsx` in place of its cards (the one
 * change to their file). It receives what their page component received, and
 * does what their page did before drawing: the workflow state (the same hook),
 * the organization's model configuration, the website widget dialog. Their
 * card components stay in their file, unused: every setting they drew is
 * rebuilt in a theme (option B of D6), and `inventaire-agent.test.ts` fails if
 * one is drawn nowhere.
 *
 * The themes, in the order of a call: Agent, Services, Listening, Turn taking,
 * Voice, Call pacing, Call data, Business.
 */
import { ArrowLeft, Bot, Building2, ClipboardList, Clock, Cpu, Ear, Repeat, Volume2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { EmbedDialog } from "@/app/workflow/[workflowId]/components/EmbedDialog";
import { useWorkflowState } from "@/app/workflow/[workflowId]/hooks/useWorkflowState";
import {
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get,
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet,
} from "@/client/sdk.gen";
import type {
    ModelConfigurationPricingResponse,
    OrganizationAiModelConfigurationResponse,
    WorkflowResponse,
} from "@/client/types.gen";
import type { ModelConfigurationDefaultsV2 } from "@/components/AIModelConfigurationV2Editor";
import type { FlowEdge, FlowNode } from "@/components/flow/types";
import { Button } from "@/components/ui/button";
import { useUnsavedChangesContext } from "@/context/UnsavedChangesContext";
import { detailFromError } from "@/lib/apiError";
import { fetchModelConfigurationPricing } from "@/lib/modelConfigurationPricing";
import { resolveWorkflowConfigurations, type WorkflowConfigurations } from "@/types/workflow-configurations";

import { NavigationThemes } from "../ecran/NavigationThemes";
import { useThemesOuverts } from "../ecran/useThemesOuverts";
import { useLangue } from "../langue/langue";
import { ContexteErreursThemes } from "./theme-commun";
import { ID_THEME_AGENT, ThemeAgent, TITRE_AGENT } from "./ThemeAgent";
import { ID_THEME_BRIQUES, ThemeBriques, TITRE_BRIQUES } from "./ThemeBriques";
import { ID_THEME_DONNEES, ThemeDonnees, TITRE_DONNEES } from "./ThemeDonnees";
import { ID_THEME_ECOUTE, ThemeEcoute, TITRE_ECOUTE } from "./ThemeEcoute";
import { ID_THEME_ETABLISSEMENT, ThemeEtablissement, TITRE_ETABLISSEMENT } from "./ThemeEtablissement";
import { ID_THEME_RYTHME, ThemeRythme, TITRE_RYTHME } from "./ThemeRythme";
import { ID_THEME_TOUR, ThemeTourDeParole, TITRE_TOUR } from "./ThemeTourDeParole";
import { ID_THEME_VOIX, ThemeVoix, TITRE_VOIX } from "./ThemeVoix";

/** The themes, in the order of a call (convention § 2). */
export const THEMES_AGENT = [
    { id: ID_THEME_AGENT, titre: TITRE_AGENT, icone: Bot },
    { id: ID_THEME_BRIQUES, titre: TITRE_BRIQUES, icone: Cpu },
    { id: ID_THEME_ECOUTE, titre: TITRE_ECOUTE, icone: Ear },
    { id: ID_THEME_TOUR, titre: TITRE_TOUR, icone: Repeat },
    { id: ID_THEME_VOIX, titre: TITRE_VOIX, icone: Volume2 },
    { id: ID_THEME_RYTHME, titre: TITRE_RYTHME, icone: Clock },
    { id: ID_THEME_DONNEES, titre: TITRE_DONNEES, icone: ClipboardList },
    { id: ID_THEME_ETABLISSEMENT, titre: TITRE_ETABLISSEMENT, icone: Building2 },
] as const;

interface ProprietesPage {
    workflow: WorkflowResponse;
    user: { id: string; email?: string };
}

/** Mounted inside Dograh's `UnsavedChangesProvider`, which their page already renders. */
export const PageReglagesAgent = ({ workflow, user }: ProprietesPage) => {
    const router = useRouter();
    const { t } = useLangue();
    const { dirtySections, confirmNavigate } = useUnsavedChangesContext();
    const themes = useThemesOuverts();
    const [themesEnErreur, setThemesEnErreur] = useState<Set<string>>(() => new Set());
    const signalerErreur = useCallback((id: string, enErreur: boolean) => {
        setThemesEnErreur((avant) => {
            if (avant.has(id) === enErreur) return avant;
            const apres = new Set(avant);
            if (enErreur) apres.add(id);
            else apres.delete(id);
            return apres;
        });
    }, []);

    const [moduleSiteOuvert, setModuleSiteOuvert] = useState(false);
    const [modelConfigurationDefaults, setModelConfigurationDefaults] = useState<ModelConfigurationDefaultsV2 | null>(null);
    const [organizationModelConfiguration, setOrganizationModelConfiguration] = useState<OrganizationAiModelConfigurationResponse | null>(null);
    const [modelConfigurationPricing, setModelConfigurationPricing] = useState<ModelConfigurationPricingResponse | null>(null);
    const [modelConfigurationLoading, setModelConfigurationLoading] = useState(true);
    const [modelConfigurationError, setModelConfigurationError] = useState<string | null>(null);
    const hasFetchedModelConfiguration = useRef(false);

    const workflowId = workflow.id;

    // What Dograh's page handed its state hook, unchanged.
    const initialFlow = useMemo(
        () => ({
            nodes: workflow.workflow_definition.nodes as FlowNode[],
            edges: workflow.workflow_definition.edges as FlowEdge[],
            viewport: { x: 0, y: 0, zoom: 0 },
        }),
        [workflow],
    );
    const initialTemplateContextVariables = useMemo(
        () => (workflow.template_context_variables as Record<string, string>) || {},
        [workflow],
    );
    const initialWorkflowConfigurations = useMemo(
        () => (workflow.workflow_configurations ? (workflow.workflow_configurations as WorkflowConfigurations) : undefined),
        [workflow],
    );

    const {
        workflowName,
        workflowConfigurations,
        defaultCallDispositions,
        defaultAnswerClassifierPrompt,
        textChatInactivityTimeoutConstraints,
        widgetTextDefaults,
        templateContextVariables,
        dictionary,
        saveWorkflowConfigurations,
        saveTemplateContextVariables,
        saveDictionary,
    } = useWorkflowState({
        initialWorkflowName: workflow.name,
        workflowId,
        initialFlow,
        initialTemplateContextVariables,
        initialWorkflowConfigurations,
        user,
    });
    const resolue = workflowConfigurations ? resolveWorkflowConfigurations(workflowConfigurations) : null;
    const nom = workflowName || workflow.name;

    useEffect(() => {
        if (hasFetchedModelConfiguration.current) return;
        hasFetchedModelConfiguration.current = true;
        const loadModelConfiguration = async () => {
            setModelConfigurationLoading(true);
            setModelConfigurationError(null);
            const [defaultsResult, configurationResult, pricingResult] = await Promise.all([
                getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet(),
                getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get(),
                fetchModelConfigurationPricing(),
            ]);
            if (defaultsResult.error) {
                setModelConfigurationError(detailFromError(defaultsResult.error, "Failed to load model configuration defaults"));
                setModelConfigurationLoading(false);
                return;
            }
            if (configurationResult.error) {
                setModelConfigurationError(detailFromError(configurationResult.error, "Failed to load model configuration"));
                setModelConfigurationLoading(false);
                return;
            }
            setModelConfigurationDefaults(defaultsResult.data as ModelConfigurationDefaultsV2);
            setOrganizationModelConfiguration(configurationResult.data || null);
            setModelConfigurationPricing(pricingResult);
            setModelConfigurationLoading(false);
        };
        loadModelConfiguration();
    }, []);

    const commun = (id: string) =>
        resolue
            ? {
                  resolue,
                  workflowName: nom,
                  onSave: saveWorkflowConfigurations,
                  ouvert: themes.estOuvert(id),
                  onBasculer: () => themes.basculer(id),
                  ouvrir: () => themes.ouvrir(id),
              }
            : null;

    return (
        <div className="min-h-screen">
            <header className="sticky top-0 z-10 flex items-center gap-3 border-b bg-background/95 px-6 py-3 backdrop-blur supports-[backdrop-filter]:bg-background/60">
                <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t({ en: "Back to the agent", fr: "Retour à l'agent" })}
                    onClick={() => confirmNavigate(() => router.push(`/workflow/${workflowId}`))}
                >
                    <ArrowLeft className="h-4 w-4" />
                </Button>
                <div>
                    <p className="text-xs text-muted-foreground">{t({ en: "Workflow Settings", fr: "Réglages de l'agent" })}</p>
                    <h1 className="text-sm font-semibold">{nom}</h1>
                </div>
            </header>

            <ContexteErreursThemes.Provider value={signalerErreur}>
                <div className="mx-auto flex max-w-5xl gap-8 px-6 py-8">
                    <div className="min-w-0 flex-1 space-y-4">
                        {resolue && (
                            <>
                                <ThemeAgent
                                    {...commun(ID_THEME_AGENT)!}
                                    workflowId={workflowId}
                                    workflowUuid={workflow.workflow_uuid}
                                    variablesEnregistrees={templateContextVariables}
                                    enregistrerVariables={saveTemplateContextVariables}
                                    ouvrirModuleSite={() => setModuleSiteOuvert(true)}
                                />
                                <ThemeBriques
                                    {...commun(ID_THEME_BRIQUES)!}
                                    workflowName={workflowName}
                                    modeles={{
                                        defaults: modelConfigurationDefaults,
                                        organisation: organizationModelConfiguration,
                                        tarifs: modelConfigurationPricing,
                                        chargement: modelConfigurationLoading,
                                        erreur: modelConfigurationError,
                                    }}
                                />
                                <ThemeEcoute {...commun(ID_THEME_ECOUTE)!} dictionnaire={dictionary} enregistrerDictionnaire={saveDictionary} />
                                <ThemeTourDeParole {...commun(ID_THEME_TOUR)!} />
                                <ThemeVoix {...commun(ID_THEME_VOIX)!} workflowId={workflowId} />
                                <ThemeRythme {...commun(ID_THEME_RYTHME)!} />
                                <ThemeDonnees {...commun(ID_THEME_DONNEES)!} issuesParDefaut={defaultCallDispositions} />
                                <ThemeEtablissement
                                    {...commun(ID_THEME_ETABLISSEMENT)!}
                                    consignesParDefaut={defaultAnswerClassifierPrompt}
                                />
                            </>
                        )}
                    </div>

                    <NavigationThemes
                        actif={null}
                        onChoisir={themes.choisir}
                        entrees={THEMES_AGENT.map((theme) => ({
                            ...theme,
                            modifie: dirtySections.has(theme.id),
                            enErreur: themesEnErreur.has(theme.id),
                        }))}
                    />
                </div>
            </ContexteErreursThemes.Provider>

            {resolue && (
                <EmbedDialog
                    open={moduleSiteOuvert}
                    onOpenChange={setModuleSiteOuvert}
                    workflowId={workflowId}
                    workflowName={nom}
                    workflowConfigurations={resolue}
                    textChatInactivityTimeoutConstraints={textChatInactivityTimeoutConstraints}
                    widgetTextDefaults={widgetTextDefaults}
                    onSaveWorkflowConfigurations={saveWorkflowConfigurations}
                />
            )}
        </div>
    );
};
