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
 * The themes, in the order of a call: Agent, Services, Listening, Modules,
 * Turn taking, Voice, Call pacing, Phrases, Call data, Business.
 */
import { Bot, MapPin, NotebookPen, Timer, Cog, Blocks, Ear, MessageSquareQuote, Puzzle, ArrowLeftRight, Search, ShieldCheck, AudioLines } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { notifier, useAgentCourant } from "@/components/mark/notifications";

import { EmbedDialog } from "@/app/workflow/[workflowId]/components/EmbedDialog";
import { useWorkflowState } from "@/app/workflow/[workflowId]/hooks/useWorkflowState";
import {
    getModelConfigurationV2ApiV1OrganizationsModelConfigurationsV2Get,
    getModelConfigurationV2DefaultsApiV1OrganizationsModelConfigurationsV2DefaultsGet,
    lireLHeritageDesReglagesApiV1WorkflowWorkflowIdHeritageReglagesGet,
    lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet,
} from "@/client/sdk.gen";
import type {
    GroupeResponse,
    ModelConfigurationPricingResponse,
    OrganizationAiModelConfigurationResponse,
    WorkflowResponse,
} from "@/client/types.gen";
import type { ModelConfigurationDefaultsV2 } from "@/components/AIModelConfigurationV2Editor";
import type { FlowEdge, FlowNode } from "@/components/flow/types";
import { Input } from "@/components/ui/input";
import { useUnsavedChangesContext } from "@/context/UnsavedChangesContext";
import { useBrouillonLocal } from "@/components/mark/agent/brouillon-local";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { fetchModelConfigurationPricing } from "@/lib/modelConfigurationPricing";
import { resolveWorkflowConfigurations, type WorkflowConfigurations } from "@/types/workflow-configurations";

import { ContexteHeritage, type ReglageHerite } from "../ecran/heritage";
import { ContexteCartes } from "../ecran/Theme";
import { useThemesOuverts } from "../ecran/useThemesOuverts";
import { etapesSansPremiereReplique } from "../graphe/premiere-replique";
import { ContexteGroupe, type ValeurGroupe } from "../groupe/contexte-groupe";
import { useLangue } from "../langue/langue";
import { BoutonModeles } from "./modeles-de-reglages/ModaleModeles";
import {
    chercherReglages,
    dansUnEspaceClient,
    NIVEAU_DU_THEME,
    NIVEAUX_REGLAGES,
    propresParTheme,
} from "./niveaux-et-recherche";
import { INVENTAIRE_AGENT } from "./inventaire-agent";
import { JugeDesVraisAppels } from "./JugeDesVraisAppels";
import { PreparationAgent } from "./PreparationAgent";
import { RecetteDeLAgent } from "./RecetteDeLAgent";
import { ContexteErreursThemes } from "./theme-commun";
import { ID_THEME_AGENT, ThemeAgent, TITRE_AGENT } from "./ThemeAgent";
import { ID_THEME_BRIQUES, ThemeBriques, TITRE_BRIQUES } from "./ThemeBriques";
import { ID_THEME_DONNEES, ThemeDonnees, TITRE_DONNEES } from "./ThemeDonnees";
import { ID_THEME_ECOUTE, ThemeEcoute, TITRE_ECOUTE } from "./ThemeEcoute";
import { ID_THEME_ETABLISSEMENT, ThemeEtablissement, TITRE_ETABLISSEMENT } from "./ThemeEtablissement";
import { ID_THEME_INTERVENTIONS, ThemeInterventions, TITRE_INTERVENTIONS } from "./ThemeInterventions";
import { ID_THEME_MODULES, ThemeModules, TITRE_MODULES } from "./ThemeModules";
import { ID_THEME_PHRASES, ThemePhrases, TITRE_PHRASES } from "./ThemePhrases";
import { ID_THEME_SECURITE, ThemeSecurite, TITRE_SECURITE } from "./ThemeSecurite";
import { ID_THEME_RYTHME, ThemeRythme, TITRE_RYTHME } from "./ThemeRythme";
import { ID_THEME_TOUR, ThemeTourDeParole, TITRE_TOUR } from "./ThemeTourDeParole";
import { ID_THEME_VOIX, ThemeVoix, TITRE_VOIX } from "./ThemeVoix";

/** The themes, in the order of a call (convention § 2). */
export const THEMES_AGENT = [
    { id: ID_THEME_AGENT, titre: TITRE_AGENT, icone: Bot },
    { id: ID_THEME_BRIQUES, titre: TITRE_BRIQUES, icone: Blocks },
    { id: ID_THEME_ECOUTE, titre: TITRE_ECOUTE, icone: Ear },
    // cloture-code, F8 (M4): the modules, moved out of « Listening » and « Call data ».
    { id: ID_THEME_MODULES, titre: TITRE_MODULES, icone: Puzzle },
    { id: ID_THEME_TOUR, titre: TITRE_TOUR, icone: ArrowLeftRight },
    { id: ID_THEME_VOIX, titre: TITRE_VOIX, icone: AudioLines },
    { id: ID_THEME_RYTHME, titre: TITRE_RYTHME, icone: Timer },
    { id: ID_THEME_PHRASES, titre: TITRE_PHRASES, icone: MessageSquareQuote },
    { id: ID_THEME_DONNEES, titre: TITRE_DONNEES, icone: NotebookPen },
    // builder-agent-vocal, lot 8: what our code does in the conversation, switch by switch.
    { id: ID_THEME_SECURITE, titre: TITRE_SECURITE, icone: ShieldCheck },
    { id: ID_THEME_INTERVENTIONS, titre: TITRE_INTERVENTIONS, icone: Cog },
    { id: ID_THEME_ETABLISSEMENT, titre: TITRE_ETABLISSEMENT, icone: MapPin },
] as const;

interface ProprietesPage {
    workflow: WorkflowResponse;
    user: { id: string; email?: string };
}

/** Mounted inside Dograh's `UnsavedChangesProvider`, which their page already renders. */
export const PageReglagesAgent = ({ workflow, user }: ProprietesPage) => {
    const { t } = useLangue();
    const { dirtySections } = useUnsavedChangesContext();
    // K6 : une saisie non enregistrée n'est jamais relue par-dessus quand l'agent est modifié ailleurs.
    useBrouillonLocal(dirtySections.size > 0);
    const themes = useThemesOuverts();
    // [.mark] lot 5: a link from a sentence rule opens the theme that sets what it reads (`?theme=briques`).
    useEffect(() => {
        const theme = new URLSearchParams(window.location.search).get("theme");
        if (theme && THEMES_AGENT.some((x) => x.id === theme)) themes.choisir(theme);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);
    const [, setThemesEnErreur] = useState<Set<string>>(() => new Set());
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
    useAgentCourant(workflowId);

    // What Dograh's page handed its state hook, unchanged.
    const initialFlow = useMemo(
        () => ({
            nodes: workflow.workflow_definition.nodes as FlowNode[],
            edges: workflow.workflow_definition.edges as FlowEdge[],
            viewport: { x: 0, y: 0, zoom: 0 },
        }),
        [workflow],
    );
    // [.mark] Plan porte-parlee (D3): read from the graph the page was opened with.
    const etapesSansPremiere = useMemo(
        () => etapesSansPremiereReplique(workflow.workflow_definition as Parameters<typeof etapesSansPremiereReplique>[0]),
        [workflow],
    );
    // [.mark] fiabilite-orchestration, lot 4 bis: the step names a sentence rule can target.
    // [.mark] correctifs-apres-banc-v4, lot 5: a rule targets a step by its node identifier (the name is only shown).
    const etapesDuGraphe = useMemo(
        () =>
            (workflow.workflow_definition.nodes as Array<{ id?: unknown; data?: { name?: unknown } }>)
                .map((noeud) => ({ id: noeud.id, nom: noeud.data?.name }))
                .filter((e): e is { id: string; nom: string } => typeof e.id === "string" && typeof e.nom === "string" && e.nom.trim() !== ""),
        [workflow],
    );
    // The tools the agent's steps carry (the « For the tool » box of a sentence rule).
    const outilsUuids = useMemo(
        () =>
            [
                ...new Set(
                    (workflow.workflow_definition.nodes as Array<{ data?: { tool_uuids?: unknown } }>).flatMap((noeud) =>
                        Array.isArray(noeud.data?.tool_uuids) ? (noeud.data.tool_uuids as unknown[]).filter((u): u is string => typeof u === "string") : [],
                    ),
                ),
            ],
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

    // [.mark] Lots 10 and 12 (A10): the group of this agent, read once, for the lists and the links of the
    // group's settings. A lone agent never asks. A failure leaves the page as for a lone agent's lists.
    const dansUnGroupe = resolue
        ? Array.isArray(resolue.agents_specialises) || typeof resolue.agent_principal_id === "number"
        : false;
    const [groupeLu, setGroupeLu] = useState<GroupeResponse | null>(null);
    useEffect(() => {
        if (!dansUnGroupe) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await lireUnGroupeApiV1WorkflowWorkflowIdGroupeGet({ path: { workflow_id: workflowId } });
                if (!annule && reponse.data) setGroupeLu(reponse.data);
            } catch {
                // The lists stay empty: the settings themselves do not depend on it.
            }
        })();
        return () => {
            annule = true;
        };
    }, [dansUnGroupe, workflowId]);
    const valeurGroupe = useMemo<ValeurGroupe>(
        () => ({
            specialiseDe: typeof resolue?.agent_principal_id === "number" ? resolue.agent_principal_id : null,
            principalNom: groupeLu?.principal?.name ?? null,
            cerveauPropre: resolue?.cerveau_propre === true,
            membres: (groupeLu?.specialises ?? []).map((m) => ({ id: m.id, name: m.name, cerveau_propre: m.cerveau_propre })),
        }),
        [resolue?.agent_principal_id, resolue?.cerveau_propre, groupeLu],
    );

    // [.mark] U4 (F3): where each setting's value comes from, read once per save; « back to the inherited value » saves
    // the inherited value at once (a deliberate gesture), then the themes are drawn again from what the server stored.
    const [heritage, setHeritage] = useState<Record<string, ReglageHerite>>({});
    const [versionEcran, setVersionEcran] = useState(0);
    const lireHeritage = useCallback(async () => {
        try {
            const reponse = await lireLHeritageDesReglagesApiV1WorkflowWorkflowIdHeritageReglagesGet({ path: { workflow_id: workflowId } });
            if (reponse.data) setHeritage(reponse.data.reglages as Record<string, ReglageHerite>);
        } catch {
            // Without it the settings show no origin: never a false one.
        }
    }, [workflowId]);
    useEffect(() => {
        void lireHeritage();
    }, [lireHeritage, workflowConfigurations]);
    const revenirALaValeurHeritee = useCallback(
        async (cle: string) => {
            if (!resolue) return;
            if (dirtySections.size > 0) {
                notifier.echec({ fr: "Enregistrez ou annulez d'abord les changements en cours.", en: "Save or cancel the pending changes first." });
                return;
            }
            const heritee = heritage[cle]?.valeur_heritee ?? null;
            try {
                await saveWorkflowConfigurations({ ...resolue, [cle]: heritee } as WorkflowConfigurations, nom);
                setVersionEcran((v) => v + 1);
                notifier.succes({ fr: "Valeur héritée rétablie.", en: "Inherited value restored." }, { publier: true });
            } catch (erreur) {
                notifier.echec({ fr: "Non enregistré. Réessayez.", en: "Not saved. Try again." }, { erreur: erreur });
            }
        },
        [resolue, dirtySections, heritage, saveWorkflowConfigurations, nom, t],
    );
    const valeurHeritage = useMemo(
        () => ({ reglages: heritage, revenir: revenirALaValeurHeritee }),
        [heritage, revenirALaValeurHeritee],
    );

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
                setModelConfigurationError(echecAffiche(defaultsResult.error));
                setModelConfigurationLoading(false);
                return;
            }
            if (configurationResult.error) {
                setModelConfigurationError(echecAffiche(configurationResult.error));
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

    // [.mark] U4 (E42, E44): the themes are cards; a card opens its window. « Cancel » forgets the draft of the theme
    // (the theme is drawn again from what the server stored) and closes the window.
    const [clesThemes, setClesThemes] = useState<Record<string, number>>({});
    const annulerTheme = useCallback(
        (id: string) => {
            themes.fermer(id);
            setClesThemes((avant) => ({ ...avant, [id]: (avant[id] ?? 0) + 1 }));
        },
        [themes],
    );
    // The Engine level is the team's: a client's space does not show it. Unknown space: shown.
    const [espaceClient, setEspaceClient] = useState(false);
    useEffect(() => {
        setEspaceClient(dansUnEspaceClient(window.location.pathname));
    }, []);
    const niveauxVisibles = NIVEAUX_REGLAGES.filter((n) => !(n.laboSeulement && espaceClient));
    const themesVisibles = useMemo(() => new Set(niveauxVisibles.flatMap((n) => n.themes)), [niveauxVisibles]);
    const valeurCartes = useMemo(
        () => ({
            annuler: annulerTheme,
            niveaux: NIVEAU_DU_THEME,
            propres: propresParTheme((cle) => heritage[cle]?.propre === true),
        }),
        [annulerTheme, heritage],
    );
    const [recherche, setRecherche] = useState("");
    const resultats = useMemo(() => chercherReglages(recherche, themesVisibles), [recherche, themesVisibles]);

    const commun = (id: string) =>
        resolue
            ? {
                  resolue,
                  workflowName: nom,
                  onSave: saveWorkflowConfigurations,
                  ouvert: themes.estOuvert(id),
                  onBasculer: () => themes.basculer(id),
                  ouvrir: () => themes.ouvrir(id),
                  versTheme: themes.choisir,
              }
            : null;

    // Each theme, drawn by its identifier; a theme the level hides is not drawn at all.
    const dessiner = (id: string) => {
        const propres = commun(id);
        if (!propres) return null;
        const cle = `${id}-${clesThemes[id] ?? 0}`;
        switch (id) {
            case ID_THEME_AGENT:
                return (
                    <ThemeAgent
                        key={cle}
                        {...propres}
                        workflowId={workflowId}
                        workflowUuid={workflow.workflow_uuid}
                        variablesEnregistrees={templateContextVariables}
                        enregistrerVariables={saveTemplateContextVariables}
                        ouvrirModuleSite={() => setModuleSiteOuvert(true)}
                    />
                );
            case ID_THEME_BRIQUES:
                return (
                    <ThemeBriques
                        key={cle}
                        {...propres}
                        workflowName={workflowName}
                        modeles={{
                            defaults: modelConfigurationDefaults,
                            organisation: organizationModelConfiguration,
                            tarifs: modelConfigurationPricing,
                            chargement: modelConfigurationLoading,
                            erreur: modelConfigurationError,
                        }}
                    />
                );
            case ID_THEME_ECOUTE:
                return <ThemeEcoute key={cle} {...propres} dictionnaire={dictionary} enregistrerDictionnaire={saveDictionary} />;
            case ID_THEME_MODULES:
                return <ThemeModules key={cle} {...propres} workflowId={workflowId} />;
            case ID_THEME_TOUR:
                return <ThemeTourDeParole key={cle} {...propres} />;
            case ID_THEME_VOIX:
                return <ThemeVoix key={cle} {...propres} workflowId={workflowId} />;
            case ID_THEME_RYTHME:
                return <ThemeRythme key={cle} {...propres} />;
            case ID_THEME_PHRASES:
                return <ThemePhrases key={cle} {...propres} etapes={etapesDuGraphe} outilsUuids={outilsUuids} workflowId={workflowId} />;
            case ID_THEME_DONNEES:
                return (
                    <ThemeDonnees
                        key={cle}
                        {...propres}
                        issuesParDefaut={defaultCallDispositions}
                        etapesSansPremiereReplique={etapesSansPremiere}
                        workflowId={workflowId}
                    />
                );
            case ID_THEME_SECURITE:
                return <ThemeSecurite key={cle} {...propres} />;
            case ID_THEME_INTERVENTIONS:
                return <ThemeInterventions key={cle} {...propres} />;
            case ID_THEME_ETABLISSEMENT:
                return (
                    <ThemeEtablissement key={cle} {...propres} consignesParDefaut={defaultAnswerClassifierPrompt} workflowId={workflowId} />
                );
            default:
                return null;
        }
    };

    return (
        <div className="min-h-screen">
            <ContexteHeritage.Provider value={valeurHeritage}>
            <ContexteGroupe.Provider value={valeurGroupe}>
            <ContexteErreursThemes.Provider value={signalerErreur}>
            <ContexteCartes.Provider value={valeurCartes}>
                <div className="mx-auto max-w-6xl space-y-6 px-6 py-6" key={versionEcran}>
                    {/* [.mark] K3 (maquette `ReglagesAgent`) : « Modèle : <nom> ⌄ » à gauche, la recherche à droite. */}
                    <div className="flex items-center gap-4">
                        <BoutonModeles workflowId={workflowId} modifie={dirtySections.size > 0} />
                        <div className="relative ml-auto w-72">
                            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                            <Input
                                type="search"
                                value={recherche}
                                onChange={(e) => setRecherche(e.target.value)}
                                aria-label={t({ en: "Search all settings", fr: "Chercher dans tous les réglages" })}
                                placeholder={t({
                                    en: `Search among the ${Object.keys(INVENTAIRE_AGENT).length} settings`,
                                    fr: `Chercher parmi les ${Object.keys(INVENTAIRE_AGENT).length} réglages`,
                                })}
                                className="h-8 border-transparent bg-muted/50 pl-8 shadow-none focus-visible:bg-background"
                            />
                        </div>
                    </div>

                    {resultats.length > 0 && (
                        <ul className="divide-y" data-recherche="resultats">
                            {resultats.map((r) => {
                                const theme = THEMES_AGENT.find((x) => x.id === r.theme);
                                return (
                                    <li key={r.cle}>
                                        <button
                                            type="button"
                                            data-resultat={r.cle}
                                            onClick={() => {
                                                themes.afficher(r.theme, r.cle);
                                                setRecherche("");
                                            }}
                                            className="flex w-full cursor-pointer items-baseline gap-3 py-2 text-left text-sm hover:font-semibold"
                                        >
                                            <span className="min-w-0 flex-1 truncate">{r.libelle ? t(r.libelle) : r.cle}</span>
                                            <code className="text-[11px] text-muted-foreground">{r.cle}</code>
                                            {theme && <span className="text-xs text-muted-foreground">{t(theme.titre)}</span>}
                                        </button>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                    {recherche.trim().length >= 2 && resultats.length === 0 && (
                        <p className="text-sm text-muted-foreground" data-recherche="aucun">
                            {t({ en: `No setting for « ${recherche.trim()} ».`, fr: `Aucun réglage pour « ${recherche.trim()} ».` })}
                        </p>
                    )}

                    <RecetteDeLAgent workflowId={workflowId} />
                    <PreparationAgent workflowId={workflowId} versTheme={themes.choisir} />

                    {resolue && (
                        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                            {niveauxVisibles.map((niveau) => (
                                <section key={niveau.id} data-niveau={niveau.id} className="contents">
                                    <h2 className="sr-only">{t(niveau.titre)}</h2>
                                    {niveau.themes.map((id) => dessiner(id))}
                                </section>
                            ))}
                        </div>
                    )}

                    <JugeDesVraisAppels workflowId={workflowId} />
                </div>
            </ContexteCartes.Provider>
            </ContexteErreursThemes.Provider>
            </ContexteGroupe.Provider>
            </ContexteHeritage.Provider>

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
