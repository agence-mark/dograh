"use client";

/**
 * [.mark] Theme « Agent »: name, identifier, template variables, website
 * widget, recordings and report (convention § 2).
 *
 * Rebuilt from Dograh's cards (option B of D6, their file untouched): the name
 * (« General »), « Agent UUID », « Template Variables » (now in a dialog edited
 * directly, closed with « Done », convention E4), « Add to Website »,
 * « Recordings » and « Report ». Same controls, same texts, same saves: the name
 * goes with the configuration save, the variables with their own function.
 *
 * Chantier correctifs-modules, lot 4 bis: « Generate the flow map », a setting
 * added after the reorganisation, saved with the configuration like the name.
 */
import { format } from "date-fns";
import { Bot, CalendarIcon, Clipboard, Download, ExternalLink, Trash2Icon } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { downloadWorkflowReportApiV1WorkflowWorkflowIdReportGet } from "@/client/sdk.gen";
import { Button } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import { copyTextToClipboard } from "@/lib/clipboard";
import logger from "@/lib/logger";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useGroupe, ZoneCommune } from "../groupe/contexte-groupe";
import {
    AIDE_SCHEMA_TOUJOURS_ACTIF,
    estPrincipal,
    estSpecialise,
    groupeForceLeSchema,
    extraireGroupe,
    IntertitreAgentsSpecialises,
    TITRE_AGENTS_SPECIALISES,
} from "../groupe/reglages-groupe";
import { type Texte, useLangue } from "../langue/langue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, type ProprietesThemeAgent, useEtatTheme } from "./theme-commun";

// Chantier schema-parcours-unique (C1): one box writes the map and drives the end of each step.
export const AIDES_SCHEMA_DU_PARCOURS: Texte[] = [
    {
        en: "At every save, writes at the end of the global prompt each step with its role (the line under « # Ta mission ici » of its prompt). Clerk mode with transitions in the reply: during the call, each step ends with one block (where the agent is, how to move on, each way out with its condition and arrival sentence) and the note-taking block is dropped. Other modes: « Tu es ici » with the step's name at the end of each step's prompt.",
        fr: "À chaque enregistrement, écrit à la fin du prompt global chaque étape avec son rôle (la ligne sous « # Ta mission ici » de son prompt). En greffier avec les portes dans la réponse : pendant l'appel, chaque étape finit par un seul bloc (où en est l'agent, comment passer à la suite, chaque sortie avec sa condition et sa phrase d'arrivée) et le bloc de prise de notes disparaît. Dans les autres modes : « Tu es ici » avec le nom de l'étape à la fin du prompt de chaque étape.",
    },
    {
        en: "Off by default. The blocks are replaced at each save, never stacked, and never touch the text you wrote. Turned off, the blocks written earlier are removed at the next save.",
        fr: "Éteint par défaut. Les blocs sont remplacés à chaque enregistrement, jamais empilés, et ne touchent jamais le texte que vous avez écrit. Éteint, les blocs écrits auparavant sont retirés au prochain enregistrement.",
    },
];

// Chantier repliques-coupees, D10; Agent theme since schema-parcours-unique (C2, C6).
type ReflexionDeRelance = "none" | "minimal" | "low" | "medium" | "high";
const NIVEAUX_DE_RELANCE: ReflexionDeRelance[] = ["none", "minimal", "low", "medium", "high"];
// A Select item cannot carry an empty value: this one stands for « no retry setting ».
const RELANCE_DE_L_AGENT = "reglage_de_l_agent";

export const AIDES_REFLEXION_DE_RELANCE: Texte[] = [
    {
        en: "When a reply stops in the middle of a sentence, it is never spoken and the model answers once more. That single retry is sent with this reasoning effort (e.g. « low » when the agent runs with « none »).",
        fr: "Quand une réplique s'arrête au milieu d'une phrase, elle n'est jamais dite et le modèle répond une fois de plus. Cette seule relance part avec ce niveau de réflexion (par exemple « low » quand l'agent tourne en « none »).",
    },
    {
        en: "Acts only in Clerk mode with transitions in the reply (Call data theme), and never with Mistral: OpenAI-compatible providers only (Scaleway…).",
        fr: "N'agit qu'en greffier avec les portes dans la réponse (thème Données de l'appel), et jamais avec Mistral : fournisseurs compatibles OpenAI seulement (Scaleway…).",
    },
];

export const ID_THEME_AGENT = "agent";
export const TITRE_AGENT = { en: "Agent", fr: "Agent" };

const EnSavoirPlus = ({ href }: { href: string }) => {
    const { t } = useLangue();
    return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 underline">
            {t({ en: "Learn more", fr: "En savoir plus" })} <ExternalLink className="h-3 w-3" />
        </a>
    );
};

/** Dograh's « Report » card, rebuilt: the CSV of completed runs, by date range. */
const Rapport = ({ workflowId }: { workflowId: number }) => {
    const { t } = useLangue();
    const [startDate, setStartDate] = useState<Date | undefined>(undefined);
    const [startTime, setStartTime] = useState("00:00");
    const [endDate, setEndDate] = useState<Date | undefined>(undefined);
    const [endTime, setEndTime] = useState("23:59");
    const [isPopoverOpen, setIsPopoverOpen] = useState(false);
    const [isDownloading, setIsDownloading] = useState(false);

    const buildDateTime = (date: Date | undefined, time: string): string | undefined => {
        if (!date) return undefined;
        const [hours, minutes] = time.split(":").map(Number);
        const combined = new Date(date);
        combined.setHours(hours, minutes, 0, 0);
        return combined.toISOString();
    };

    const handleDownload = async () => {
        setIsDownloading(true);
        setIsPopoverOpen(false);
        try {
            const response = await downloadWorkflowReportApiV1WorkflowWorkflowIdReportGet({
                path: { workflow_id: workflowId },
                query: {
                    start_date: buildDateTime(startDate, startTime),
                    end_date: buildDateTime(endDate, endTime),
                },
                parseAs: "blob",
            });
            if (response.data) {
                const blob = response.data as Blob;
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `workflow_${workflowId}_report.csv`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                window.URL.revokeObjectURL(url);
            } else {
                toast.error(t({ en: "Failed to download report", fr: "Téléchargement du rapport impossible" }));
            }
        } catch (err) {
            logger.error(`Failed to download workflow report: ${err}`);
            toast.error(t({ en: "Failed to download report", fr: "Téléchargement du rapport impossible" }));
        } finally {
            setIsDownloading(false);
        }
    };

    const handleClear = () => {
        setStartDate(undefined);
        setStartTime("00:00");
        setEndDate(undefined);
        setEndTime("23:59");
    };

    return (
        <Popover open={isPopoverOpen} onOpenChange={setIsPopoverOpen}>
            <PopoverTrigger asChild>
                <Button variant="outline" disabled={isDownloading}>
                    <Download className="mr-2 h-4 w-4" />
                    {t({ en: "Download Report", fr: "Télécharger le rapport" })}
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-auto p-4" align="start">
                <div className="space-y-4">
                    <div className="text-sm font-medium">{t({ en: "Filter by date range", fr: "Filtrer par période" })}</div>
                    <div className="grid gap-3">
                        {(
                            [
                                { libelle: { en: "From", fr: "Du" }, date: startDate, setDate: setStartDate, heure: startTime, setHeure: setStartTime, vide: { en: "Start date", fr: "Date de début" }, borne: (d: Date) => (endDate ? d > endDate : false) },
                                { libelle: { en: "To", fr: "Au" }, date: endDate, setDate: setEndDate, heure: endTime, setHeure: setEndTime, vide: { en: "End date", fr: "Date de fin" }, borne: (d: Date) => (startDate ? d < startDate : false) },
                            ] as const
                        ).map((ligne) => (
                            <div key={ligne.vide.en} className="space-y-1.5">
                                <Label className="text-xs">{t(ligne.libelle)}</Label>
                                <div className="flex gap-2">
                                    <Popover>
                                        <PopoverTrigger asChild>
                                            <Button variant="outline" size="sm" className="w-[140px] justify-start text-left font-normal">
                                                <CalendarIcon className="mr-2 h-3.5 w-3.5" />
                                                {ligne.date ? format(ligne.date, "MMM dd, yyyy") : t(ligne.vide)}
                                            </Button>
                                        </PopoverTrigger>
                                        <PopoverContent className="w-auto p-0" align="start">
                                            <Calendar mode="single" selected={ligne.date} onSelect={ligne.setDate} disabled={ligne.borne} />
                                        </PopoverContent>
                                    </Popover>
                                    <Input
                                        type="time"
                                        value={ligne.heure}
                                        onChange={(e) => ligne.setHeure(e.target.value)}
                                        className="h-8 w-[100px] text-xs"
                                    />
                                </div>
                            </div>
                        ))}
                    </div>
                    <Separator />
                    <div className="flex justify-between">
                        <Button variant="ghost" size="sm" onClick={handleClear}>
                            {t({ en: "Clear", fr: "Effacer" })}
                        </Button>
                        <Button size="sm" onClick={handleDownload} disabled={isDownloading}>
                            <Download className="mr-1.5 h-3.5 w-3.5" />
                            {startDate || endDate
                                ? t({ en: "Download Filtered", fr: "Télécharger la période" })
                                : t({ en: "Download All", fr: "Tout télécharger" })}
                        </Button>
                    </div>
                </div>
            </PopoverContent>
        </Popover>
    );
};

export const ThemeAgent = ({
    resolue,
    workflowName,
    onSave,
    ouvert,
    onBasculer,
    workflowId,
    workflowUuid,
    variablesEnregistrees,
    enregistrerVariables,
    ouvrirModuleSite,
}: ProprietesThemeAgent & {
    workflowId: number;
    workflowUuid?: string | null;
    variablesEnregistrees: Record<string, string>;
    enregistrerVariables: (variables: Record<string, string>) => Promise<void>;
    ouvrirModuleSite: () => void;
}) => {
    const { t } = useLangue();
    const [nom, setNom] = useState(workflowName);
    const [contextVars, setContextVars] = useState<Record<string, string>>(variablesEnregistrees);
    const [newKey, setNewKey] = useState("");
    const [newValue, setNewValue] = useState("");
    const [fenetreVariables, setFenetreVariables] = useState(false);
    const schemaEnregistre = resolue.generer_schema_parcours ?? false;
    const [schema, setSchema] = useState(schemaEnregistre);
    const schemaModifie = schema !== schemaEnregistre;
    // Dans un groupe (accueil ou spécialisé), le code génère toujours le schéma : la case est grisée.
    const schemaForce = groupeForceLeSchema(resolue);
    // Chantier schema-parcours-unique (C2, C6): the retry reasoning, always shown, next to the map.
    const relanceEnregistree = resolue.reflexion_de_relance ?? null;
    const [relance, setRelance] = useState<ReflexionDeRelance | null>(relanceEnregistree);
    const relanceModifiee = relance !== relanceEnregistree;
    // Chantier repliques-coupees, lot 6 bis (D16): the model request trace, every mode.
    const traceEnregistree = resolue.trace_requetes_modele ?? false;
    const [trace, setTrace] = useState(traceEnregistree);
    const traceModifiee = trace !== traceEnregistree;
    // [.mark] Lot 12 (A5, A7, A18): the settings of the group, carried by its main agent. Shown only for
    // a main agent (editable) or a specialised one (read only: set on the main agent).
    const principal = estPrincipal(resolue);
    const specialise = estSpecialise(resolue);
    const groupeEnregistre = extraireGroupe(resolue);
    const [groupe, setGroupe] = useState(groupeEnregistre);
    const groupeModifie = principal && differe(groupe, groupeEnregistre);
    // Lot 2 d'orchestrateur-trois-cerveaux (B2): the end-of-call safety net, its own part (E6).
    const filetEnregistre = resolue.filet_de_fin ?? false;
    const [filet, setFilet] = useState(filetEnregistre);
    const filetModifie = principal && filet !== filetEnregistre;
    const contexteGroupe = useGroupe();
    // The retry reasoning and the trace follow the brain: read only on a specialised agent that has not
    // detached its own.
    const suitLeCerveau = specialise && !contexteGroupe.cerveauPropre;

    // Dograh's rule: a pair typed but not added yet is part of what is saved.
    const variablesAEnregistrer = useMemo(
        () => (newKey && newValue ? { ...contextVars, [newKey]: newValue } : contextVars),
        [contextVars, newKey, newValue],
    );
    const nomModifie = nom !== workflowName;
    const variablesModifiees = differe(variablesAEnregistrer, variablesEnregistrees);
    const modifie = nomModifie || variablesModifiees || schemaModifie || relanceModifiee || traceModifiee || groupeModifie || filetModifie;
    useEtatTheme(ID_THEME_AGENT, modifie, false);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_AGENT,
        resolue,
        workflowName,
        onSave,
        parties: [
            { nom: { en: "Agent name", fr: "Nom de l'agent" }, modifie: nomModifie, nomAgent: () => nom },
            {
                nom: { en: "Flow map", fr: "Schéma du parcours" },
                modifie: schemaModifie,
                config: () => ({ generer_schema_parcours: schema }),
            },
            {
                // Its own part, sent only when changed (E6).
                nom: { en: "Retry reasoning", fr: "Réflexion de relance" },
                modifie: relanceModifiee,
                config: () => ({ reflexion_de_relance: relance }),
            },
            {
                // Its own part, sent only when changed (E6).
                nom: { en: "Model request trace", fr: "Trace des requêtes au modèle" },
                modifie: traceModifiee,
                config: () => ({ trace_requetes_modele: trace }),
            },
            {
                // Its own part, sent only when changed (E6): the settings of the group.
                nom: TITRE_AGENTS_SPECIALISES,
                modifie: groupeModifie,
                config: () => groupe,
            },
            {
                // Its own part, sent only when changed (E6): the settings of the group stay what they were.
                nom: { en: "End-of-call safety net", fr: "Filet de fin d'appel" },
                modifie: filetModifie,
                config: () => ({ filet_de_fin: filet }),
            },
            {
                nom: { en: "Template variables", fr: "Variables du modèle" },
                modifie: variablesModifiees,
                enregistrerAutrement: () => enregistrerVariables(variablesAEnregistrer),
            },
        ],
    });

    const copierUuid = async () => {
        if (!workflowUuid) return;
        try {
            await copyTextToClipboard(workflowUuid);
            toast.success(t({ en: "Agent UUID copied", fr: "Identifiant de l'agent copié" }));
        } catch {
            toast.error(t({ en: "Failed to copy Agent UUID", fr: "Copie de l'identifiant impossible" }));
        }
    };

    const nombreDeVariables = Object.keys(contextVars).length;

    return (
        <Theme
            id={ID_THEME_AGENT}
            icone={Bot}
            titre={TITRE_AGENT}
            description={{ en: "Name, ID, variables, deployment and report.", fr: "Nom, identifiant, variables, diffusion et rapport." }}
            resume={[
                nom,
                `${nombreDeVariables} ${t({ en: "variables", fr: "variables" })}`,
                ...(schema ? [t({ en: "Flow map on", fr: "Schéma du parcours allumé" })] : []),
            ]}
            ouvert={ouvert}
            onBasculer={onBasculer}
            modifie={modifie}
            erreurs={[]}
            enregistrement={{ onEnregistrer: enregistrer, enCours }}
        >
            <Intertitre id="agent-nom" titre={{ en: "Name", fr: "Nom" }}>
                <ChampReglage cle="name" idControle="workflow_name" libelle={{ en: "Agent Name", fr: "Nom de l'agent" }}>
                    <Input
                        id="workflow_name"
                        value={nom}
                        onChange={(e) => setNom(e.target.value)}
                        placeholder={t({ en: "Enter Agent name", fr: "Nom de l'agent" })}
                    />
                </ChampReglage>
            </Intertitre>

            {workflowUuid && (
                <Intertitre id="agent-uuid" titre={{ en: "UUID", fr: "Identifiant" }}>
                    <ChampReglage
                        cle="workflow_uuid"
                        libelle={{ en: "Agent UUID", fr: "Identifiant de l'agent (UUID)" }}
                        aides={[
                            {
                                en: "Stable identifier for this agent. Used in agent-stream URLs and other integrations where a numeric workflow ID isn't portable.",
                                fr: "Identifiant stable de l'agent. Sert dans les adresses de flux et les intégrations où un numéro d'agent n'est pas portable.",
                            },
                        ]}
                    >
                        <div className="flex items-center gap-2">
                            <button
                                type="button"
                                onClick={copierUuid}
                                title={t({ en: "Click to copy", fr: "Cliquer pour copier" })}
                                className="group flex flex-1 items-center gap-2 rounded-md border bg-muted/20 p-2 text-left font-mono text-xs transition-colors hover:bg-muted/40"
                            >
                                <code className="flex-1 truncate">{workflowUuid}</code>
                                <Clipboard className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
                            </button>
                            <Button variant="outline" size="sm" onClick={copierUuid}>
                                <Clipboard className="mr-2 h-3.5 w-3.5" />
                                {t({ en: "Copy UUID", fr: "Copier" })}
                            </Button>
                        </div>
                    </ChampReglage>
                </Intertitre>
            )}

            <Intertitre id="agent-schema-parcours" titre={{ en: "Flow map", fr: "Schéma du parcours" }}>
                <ChampReglage
                    cle="generer_schema_parcours"
                    idControle="generer_schema_parcours"
                    libelle={{ en: "Generate the flow map", fr: "Générer le schéma du parcours" }}
                    aides={schemaForce ? [...AIDES_SCHEMA_DU_PARCOURS, AIDE_SCHEMA_TOUJOURS_ACTIF] : AIDES_SCHEMA_DU_PARCOURS}
                    disposition="ligne"
                >
                    <Switch
                        id="generer_schema_parcours"
                        checked={schemaForce || schema}
                        disabled={schemaForce}
                        onCheckedChange={setSchema}
                    />
                </ChampReglage>
                <ZoneCommune lecture={suitLeCerveau} bandeau={false}>
                <ChampReglage
                    cle="reflexion_de_relance"
                    idControle="reflexion_de_relance"
                    libelle={{ en: "Retry reasoning", fr: "Réflexion de relance" }}
                    aides={AIDES_REFLEXION_DE_RELANCE}
                    bornes={{ en: "Default: no retry reasoning (the agent's setting)", fr: "Par défaut : aucune réflexion de secours (le réglage de l'agent)" }}
                >
                    <Select
                        value={relance ?? RELANCE_DE_L_AGENT}
                        onValueChange={(v: string) => setRelance(v === RELANCE_DE_L_AGENT ? null : (v as ReflexionDeRelance))}
                    >
                        <SelectTrigger id="reflexion_de_relance">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value={RELANCE_DE_L_AGENT}>
                                {t({ en: "None (the agent's setting)", fr: "Aucune (le réglage de l'agent)" })}
                            </SelectItem>
                            {NIVEAUX_DE_RELANCE.map((niveau) => (
                                <SelectItem key={niveau} value={niveau}>
                                    {niveau}
                                </SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </ChampReglage>
                </ZoneCommune>
            </Intertitre>

            <ZoneCommune lecture={suitLeCerveau} bandeau={false}>
            <Intertitre id="agent-diagnostic" titre={{ en: "Diagnostic", fr: "Diagnostic" }}>
                <ChampReglage
                    cle="trace_requetes_modele"
                    idControle="trace_requetes_modele"
                    libelle={{ en: "Trace model requests", fr: "Tracer les requêtes au modèle" }}
                    aides={[
                        {
                            en: "Each answer the conversation model is asked for is recorded in the run: the exact request (never a key), every piece of the reply with its arrival time and finish reason, the token count, and what was spoken.",
                            fr: "Chaque réponse demandée au modèle de conversation est enregistrée dans le run : la requête exacte (jamais une clé), chaque morceau de la réponse avec son heure d'arrivée et sa raison de fin, le nombre de jetons, et ce qui a été dit.",
                        },
                        {
                            en: "Off by default. About 20 KB per answer: for test agents, not for a client's agent.",
                            fr: "Éteint par défaut. Environ 20 Ko par réponse : pour les agents d'essai, pas pour l'agent d'un client.",
                        },
                    ]}
                    disposition="ligne"
                >
                    <Switch id="trace_requetes_modele" checked={trace} onCheckedChange={setTrace} />
                </ChampReglage>
            </Intertitre>
            </ZoneCommune>

            {principal && (
                <IntertitreAgentsSpecialises
                    valeurs={groupe}
                    onChange={(cle, valeur) => setGroupe((avant) => ({ ...avant, [cle]: valeur }))}
                    filet={filet}
                    onFiletChange={setFilet}
                />
            )}
            {specialise && (
                <ZoneCommune lecture>
                    <IntertitreAgentsSpecialises valeurs={groupeEnregistre} onChange={() => undefined} filet={filetEnregistre} />
                </ZoneCommune>
            )}

            <Intertitre id="agent-variables" titre={{ en: "Template Variables", fr: "Variables du modèle" }}>
                <ChampReglage
                    cle="template_context_variables"
                    libelle={{ en: "Template Variables", fr: "Variables du modèle" }}
                    aides={[
                        {
                            en: "Variables available in workflow prompts via {{variable_name}} syntax for testing the workflow.",
                            fr: "Disponibles dans les prompts avec la syntaxe {{nom_variable}}, pour tester l'agent.",
                        },
                    ]}
                >
                    <div className="flex items-center justify-between gap-3 rounded border p-3 text-sm">
                        <span>
                            {nombreDeVariables} {t({ en: "variables", fr: "variables" })}
                        </span>
                        <Button variant="outline" size="sm" onClick={() => setFenetreVariables(true)}>
                            {t({ en: "Manage variables", fr: "Gérer les variables" })}
                        </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                        <EnSavoirPlus href={SETTINGS_DOCUMENTATION_URLS.templateVariables} />
                    </p>
                </ChampReglage>
            </Intertitre>

            <Intertitre id="agent-diffusion" titre={{ en: "Deployment and report", fr: "Diffusion et rapport" }}>
                <ChampReglage
                    cle="deployment"
                    libelle={{ en: "Add to Website", fr: "Ajouter au site internet" }}
                    aides={[
                        {
                            en: "Configure a widget to add this voice agent to your website.",
                            fr: "Configure un module pour ajouter cet agent vocal à votre site.",
                        },
                    ]}
                >
                    <div className="flex items-center gap-3">
                        <Button variant="outline" onClick={ouvrirModuleSite}>
                            {t({ en: "Configure Widget", fr: "Configurer le module" })}
                        </Button>
                        <span className="text-xs text-muted-foreground">
                            <EnSavoirPlus href={SETTINGS_DOCUMENTATION_URLS.deployment} />
                        </span>
                    </div>
                </ChampReglage>
                <ChampReglage
                    cle="recordings"
                    libelle={{ en: "Recordings", fr: "Enregistrements" }}
                    aides={[
                        {
                            en: "Recordings are now managed at the organization level and shared across all agents. Use @ in prompt fields to insert them.",
                            fr: "Les enregistrements se gèrent au niveau de l'organisation et sont partagés par tous les agents. Tapez @ dans un prompt pour en insérer un.",
                        },
                    ]}
                >
                    <div className="flex items-center gap-3">
                        <Button variant="outline" asChild>
                            <Link href="/recordings">
                                {t({ en: "Go to Recordings", fr: "Aller aux enregistrements" })}
                                <ExternalLink className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                        <span className="text-xs text-muted-foreground">
                            <EnSavoirPlus href={SETTINGS_DOCUMENTATION_URLS.recordings} />
                        </span>
                    </div>
                </ChampReglage>
                <ChampReglage
                    cle="report"
                    libelle={{ en: "Report", fr: "Rapport" }}
                    aides={[
                        {
                            en: "Download a CSV report of completed runs for this agent, optionally filtered by date range.",
                            fr: "Télécharge un rapport CSV des appels terminés de cet agent, filtrable par période.",
                        },
                    ]}
                >
                    <div>
                        <Rapport workflowId={workflowId} />
                    </div>
                </ChampReglage>
            </Intertitre>

            <Dialog open={fenetreVariables} onOpenChange={setFenetreVariables}>
                <DialogContent className="sm:max-w-2xl">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Template Variables", fr: "Variables du modèle" })}</DialogTitle>
                        <DialogDescription>
                            {t({
                                en: "Variables available in workflow prompts via {{variable_name}} syntax for testing the workflow.",
                                fr: "Disponibles dans les prompts avec la syntaxe {{nom_variable}}, pour tester l'agent.",
                            })}
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-4">
                        {Object.entries(contextVars).length > 0 && (
                            <div className="space-y-2">
                                <Label className="text-sm font-medium">{t({ en: "Current Variables", fr: "Variables actuelles" })}</Label>
                                {Object.entries(contextVars).map(([key, value]) => (
                                    <div key={key} className="flex items-center gap-2 rounded-md border p-2">
                                        <div className="min-w-0 flex-1">
                                            <div className="text-sm font-medium">{key}</div>
                                            <div className="truncate text-xs text-muted-foreground">{value}</div>
                                        </div>
                                        <Button
                                            size="sm"
                                            variant="ghost"
                                            aria-label={t({ en: `Remove variable ${key}`, fr: `Retirer la variable ${key}` })}
                                            onClick={() =>
                                                setContextVars((prev) => {
                                                    const next = { ...prev };
                                                    delete next[key];
                                                    return next;
                                                })
                                            }
                                        >
                                            <Trash2Icon className="h-4 w-4" />
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        )}
                        <div className="space-y-3">
                            <Label className="text-sm font-medium">{t({ en: "Add New Variable", fr: "Ajouter une variable" })}</Label>
                            <div className="flex gap-2">
                                <div className="flex-1 space-y-1">
                                    <Label htmlFor="var-key" className="text-xs">
                                        {t({ en: "Key", fr: "Nom" })}
                                    </Label>
                                    <Input
                                        id="var-key"
                                        placeholder={t({ en: "Enter variable key", fr: "Nom de la variable" })}
                                        value={newKey}
                                        onChange={(e) => setNewKey(e.target.value)}
                                    />
                                </div>
                                <div className="flex-1 space-y-1">
                                    <Label htmlFor="var-value" className="text-xs">
                                        {t({ en: "Value", fr: "Valeur" })}
                                    </Label>
                                    <Input
                                        id="var-value"
                                        placeholder={t({ en: "Enter variable value", fr: "Valeur de la variable" })}
                                        value={newValue}
                                        onChange={(e) => setNewValue(e.target.value)}
                                    />
                                </div>
                            </div>
                            <Button
                                size="sm"
                                onClick={() => {
                                    if (newKey && newValue) setContextVars((prev) => ({ ...prev, [newKey]: newValue }));
                                    setNewKey("");
                                    setNewValue("");
                                }}
                                disabled={!newKey || !newValue}
                            >
                                {t({ en: "Add Variable", fr: "Ajouter la variable" })}
                            </Button>
                        </div>
                    </div>
                    <DialogFooter>
                        <Button onClick={() => setFenetreVariables(false)}>{t({ en: "Done", fr: "Terminé" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Theme>
    );
};
