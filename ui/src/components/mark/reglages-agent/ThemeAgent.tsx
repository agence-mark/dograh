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
import { Separator } from "@/components/ui/separator";
import { SETTINGS_DOCUMENTATION_URLS } from "@/constants/documentation";
import { copyTextToClipboard } from "@/lib/clipboard";
import logger from "@/lib/logger";

import { ChampReglage } from "../ecran/ChampReglage";
import { Intertitre } from "../ecran/Intertitre";
import { Theme } from "../ecran/Theme";
import { useLangue } from "../langue/langue";
import { useEnregistrementTheme } from "./enregistrement";
import { differe, type ProprietesThemeAgent, useEtatTheme } from "./theme-commun";

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

    // Dograh's rule: a pair typed but not added yet is part of what is saved.
    const variablesAEnregistrer = useMemo(
        () => (newKey && newValue ? { ...contextVars, [newKey]: newValue } : contextVars),
        [contextVars, newKey, newValue],
    );
    const nomModifie = nom !== workflowName;
    const variablesModifiees = differe(variablesAEnregistrer, variablesEnregistrees);
    const modifie = nomModifie || variablesModifiees;
    useEtatTheme(ID_THEME_AGENT, modifie, false);

    const { enCours, enregistrer } = useEnregistrementTheme({
        titre: TITRE_AGENT,
        resolue,
        workflowName,
        onSave,
        parties: [
            { nom: { en: "Agent name", fr: "Nom de l'agent" }, modifie: nomModifie, nomAgent: () => nom },
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
            resume={[nom, `${nombreDeVariables} ${t({ en: "variables", fr: "variables" })}`]}
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
