"use client";

/**
 * [.mark] La barre d'un agent, onglet Parcours (U3, E37, E46).
 *
 * Première ligne : flèche retour, nom (un clic le renomme), version ⌄, puis à droite Essayer ⌄ (navigateur, téléphone,
 * clavier, appelant simulé, jouer les tests), Builder IA, Publier (avec la raison s'il est grisé), Enregistrer et ⋮
 * (appels, dupliquer, télécharger, copier l'UUID). Seconde ligne : le membre du groupe, les cinq onglets, et à droite
 * « non enregistré » et les erreurs du parcours. L'historique des versions est l'onglet Versions (plus de panneau).
 * « Exporter vers un client » n'est pas ici : il arrive avec H2.
 */
import { ReactFlowInstance } from "@xyflow/react";
import {
    AlertCircle,
    ArrowLeft,
    ChevronDown,
    Clipboard,
    Copy,
    Download,
    Eye,
    FlaskConical,
    History,
    Keyboard,
    LoaderCircle,
    Menu,
    MoreVertical,
    Pencil,
    Phone,
    Play,
    Rocket,
    Tag,
    Users,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost,
    publishWorkflowApiV1WorkflowWorkflowIdPublishPost,
} from "@/client/sdk.gen";
import { WorkflowError } from "@/client/types.gen";
import { BarreDuBuilder } from "@/components/builder/ecran/BarreDuBuilder";
import { FlowEdge, FlowNode } from "@/components/flow/types";
import { FenetreEtiquettes } from "@/components/mark/agent/etiquettes/FenetreEtiquettes";
import { adresseDesAgents } from "@/components/mark/agent/liste-des-agents";
import { MenuMembre } from "@/components/mark/agent/MenuMembre";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { OngletsAgent } from "@/components/mark/agent/OngletsAgent";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSidebar } from "@/components/ui/sidebar";
import { copyTextToClipboard } from "@/lib/clipboard";
import { espaceRetenu } from "@/lib/espaceCourant";

export type ModeEssai = "audio" | "text" | "simulated";

interface WorkflowEditorHeaderProps {
    workflowName: string;
    isDirty: boolean;
    workflowValidationErrors: WorkflowError[];
    rfInstance: React.RefObject<ReactFlowInstance<FlowNode, FlowEdge> | null>;
    workflowId: number;
    workflowUuid?: string;
    saveWorkflow: (updateWorkflowDefinition?: boolean) => Promise<void>;
    user: { id: string; email?: string };
    onPhoneCallClick: () => void;
    /** Ouvre le panneau d'essai, sur l'onglet demandé. */
    onTestAgentClick: (mode: ModeEssai) => void;
    activeVersionLabel?: string;
    isViewingHistoricalVersion: boolean;
    onBackToDraft: () => void;
    hasDraft: boolean;
    onPublished: () => void;
    renameWorkflow: (newName: string) => Promise<void>;
    /** [.mark] builder-agent-vocal (lot 4) : le bouton « Builder IA », et pourquoi « Publier » est grisé. */
    builder?: {
        ouvert: boolean;
        onToggle: () => void;
        raisonDeBlocage: string | null;
    };
}

const T = {
    retour: { en: "Back to the agents", fr: "Retour aux agents" },
    menu: { en: "Open menu", fr: "Ouvrir le menu" },
    menuAgent: { en: "Agent menu", fr: "Menu de l'agent" },
    renommer: { en: "Rename the agent", fr: "Renommer l'agent" },
    nomAgent: { en: "Agent name", fr: "Nom de l'agent" },
    nomVide: { en: "The name cannot be empty", fr: "Le nom ne peut pas être vide" },
    renommageEchoue: { en: "The agent could not be renamed", fr: "L'agent n'a pas pu être renommé" },
    versionPassee: { en: "Read only", fr: "Lecture seule" },
    retourBrouillon: { en: "Back to draft", fr: "Retour au brouillon" },
    version: { en: "Version", fr: "Version" },
    toutesLesVersions: { en: "All versions", fr: "Toutes les versions" },
    essayer: { en: "Try", fr: "Essayer" },
    navigateur: { en: "In the browser", fr: "Dans le navigateur" },
    telephone: { en: "By phone", fr: "Par téléphone" },
    clavier: { en: "With the keyboard", fr: "Au clavier" },
    appelantSimule: { en: "With a simulated caller", fr: "Avec un appelant simulé" },
    jouerLesTests: { en: "Play the tests", fr: "Jouer les tests" },
    publier: { en: "Publish", fr: "Publier" },
    publication: { en: "Publishing...", fr: "Publication..." },
    publie: { en: "Agent published", fr: "Agent publié" },
    publicationEchoue: { en: "The agent could not be published", fr: "L'agent n'a pas pu être publié" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    enregistrement: { en: "Saving...", fr: "Enregistrement..." },
    nonEnregistre: { en: "Unsaved changes", fr: "Non enregistré" },
    erreur: { en: "error", fr: "erreur" },
    erreurs: { en: "errors", fr: "erreurs" },
    erreursTitre: { en: "Errors in the flow", fr: "Erreurs du parcours" },
    noeud: { en: "Node", fr: "Nœud" },
    liaison: { en: "Link", fr: "Liaison" },
    appels: { en: "Calls", fr: "Appels" },
    dupliquer: { en: "Duplicate", fr: "Dupliquer" },
    duplication: { en: "Duplicating...", fr: "Duplication..." },
    duplique: { en: "Agent duplicated", fr: "Agent dupliqué" },
    duplicationEchoue: { en: "The agent could not be duplicated", fr: "L'agent n'a pas pu être dupliqué" },
    telecharger: { en: "Download (JSON)", fr: "Télécharger (JSON)" },
    copierUuid: { en: "Copy the UUID", fr: "Copier l'UUID" },
    etiquettes: { en: "Labels", fr: "Étiquettes" },
    uuidCopie: { en: "UUID copied", fr: "UUID copié" },
    uuidIndisponible: { en: "UUID not available", fr: "UUID indisponible" },
    uuidEchoue: { en: "The UUID could not be copied", fr: "L'UUID n'a pas pu être copié" },
} satisfies Record<string, Texte>;

export const WorkflowEditorHeader = ({
    workflowName,
    isDirty,
    workflowValidationErrors,
    rfInstance,
    saveWorkflow,
    onPhoneCallClick,
    onTestAgentClick,
    activeVersionLabel,
    isViewingHistoricalVersion,
    onBackToDraft,
    hasDraft,
    onPublished,
    workflowId,
    workflowUuid,
    renameWorkflow,
    builder,
}: WorkflowEditorHeaderProps) => {
    const { t } = useLangue();
    const router = useRouter();
    const { toggleSidebar } = useSidebar();
    const [savingWorkflow, setSavingWorkflow] = useState(false);
    const [duplicating, setDuplicating] = useState(false);
    const [publishing, setPublishing] = useState(false);
    const [etiquettesOuvert, setEtiquettesOuvert] = useState(false);
    const [retour, setRetour] = useState("/labo/agents");
    useEffect(() => setRetour(adresseDesAgents(espaceRetenu())), []);
    // Un seul état pour le renommage : l'erreur et l'enregistrement s'excluent, et ni l'un ni l'autre n'a de sens à l'affichage.
    type RenameState =
        | { kind: "display" }
        | { kind: "editing"; draft: string; error: string | null }
        | { kind: "saving"; draft: string };
    const [rename, setRename] = useState<RenameState>({ kind: "display" });
    const nameInputRef = useRef<HTMLInputElement>(null);
    const renameButtonRef = useRef<HTMLButtonElement>(null);

    const hasValidationErrors = workflowValidationErrors.length > 0;
    const isCallDisabled = isDirty || hasValidationErrors;

    const handleSave = async () => {
        setSavingWorkflow(true);
        await saveWorkflow();
        setSavingWorkflow(false);
    };

    const handlePublish = async () => {
        if (publishing) return;
        setPublishing(true);
        const promise = publishWorkflowApiV1WorkflowWorkflowIdPublishPost({
            path: { workflow_id: workflowId },
        });
        notifier.suivre(promise, {
            encours: { fr: "Publication en cours…", en: "Publishing…" },
            succes: { fr: "Agent publié.", en: "Agent published." },
            echec: { fr: "Publication impossible. Réessayez.", en: "Could not publish. Try again." },
            echecSi: (reponse) => reponse.error,
            reessayer: () => void handlePublish(),
            groupe: "publication-agent",
        });
        try {
            await promise;
            onPublished();
        } finally {
            setPublishing(false);
        }
    };

    const handleDuplicate = async () => {
        if (duplicating) return;
        setDuplicating(true);
        const promise = duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost({
            path: { workflow_id: workflowId },
        });
        notifier.suivre(promise, {
            encours: { fr: "Duplication en cours…", en: "Duplicating…" },
            succes: { fr: "Agent dupliqué.", en: "Agent duplicated." },
            echec: { fr: "Duplication impossible. Réessayez.", en: "Could not duplicate. Try again." },
            echecSi: (reponse) => reponse.error,
            groupe: "duplication-agent",
        });
        try {
            const { data } = await promise;
            if (data?.id) {
                router.push(adresseOnglet(data.id, "parcours"));
            }
        } finally {
            setDuplicating(false);
        }
    };

    const handleCopyAgentUuid = async () => {
        if (!workflowUuid) {
            notifier.echec({ fr: "Identifiant indisponible.", en: "ID unavailable." });
            return;
        }
        try {
            await copyTextToClipboard(workflowUuid);
            notifier.succes({ fr: "Identifiant copié.", en: "ID copied." });
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };

    const handleDownloadWorkflow = () => {
        if (!rfInstance.current) return;

        const workflowDefinition = rfInstance.current.toObject();
        const exportData = {
            name: workflowName,
            workflow_definition: workflowDefinition,
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `${workflowName}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    const enterEditMode = () => {
        setRename({ kind: "editing", draft: workflowName, error: null });
    };

    const exitEditMode = () => {
        setRename({ kind: "display" });
        // Rend le focus au nom pour que le clavier ne reste pas sans repère.
        setTimeout(() => renameButtonRef.current?.focus(), 0);
    };

    const attemptSave = async () => {
        // Seul « editing » peut lancer l'enregistrement (cela évite aussi le blur déclenché quand le champ se désactive).
        if (rename.kind !== "editing") return;
        const trimmed = rename.draft.trim();
        if (trimmed.length === 0) {
            setRename({ ...rename, error: t(T.nomVide) });
            return;
        }
        if (trimmed === workflowName) {
            exitEditMode();
            return;
        }
        setRename({ kind: "saving", draft: rename.draft });
        try {
            await renameWorkflow(trimmed);
            exitEditMode();
        } catch {
            notifier.echec({ fr: "Renommage impossible. Réessayez.", en: "Could not rename. Try again." });
            setRename({ kind: "editing", draft: trimmed, error: null });
            setTimeout(() => nameInputRef.current?.focus(), 0);
        }
    };

    const handleRenameKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
        if (event.key === "Enter") {
            event.preventDefault();
            void attemptSave();
        } else if (event.key === "Escape") {
            event.preventDefault();
            exitEditMode();
        }
    };

    const handleRenameBlur = () => {
        if (rename.kind !== "editing") return;
        // Un nom vide quand on quitte le champ : retour silencieux à l'affichage, personne n'est coincé.
        if (rename.draft.trim().length === 0) {
            exitEditMode();
            return;
        }
        void attemptSave();
    };

    const raison = builder?.raisonDeBlocage ?? null;

    return (
        <div data-barre-agent>
            <div className="flex h-14 w-full items-center justify-between border-b border-border bg-background px-4">
                <div className="mr-4 flex items-center gap-3">
                    <button
                        onClick={toggleSidebar}
                        className="flex size-8 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-accent md:hidden"
                        aria-label={t(T.menu)}
                    >
                        <Menu className="size-5 text-muted-foreground" />
                    </button>
                    <Link
                        href={retour}
                        aria-label={t(T.retour)}
                        className="flex size-8 cursor-pointer items-center justify-center rounded-lg transition-colors hover:bg-accent"
                    >
                        <ArrowLeft className="size-5 text-muted-foreground" />
                    </Link>

                    <div className="flex items-center gap-1">
                        {rename.kind !== "display" ? (
                            <div className="flex flex-col gap-1">
                                <Input
                                    ref={nameInputRef}
                                    value={rename.draft}
                                    onChange={(e) => {
                                        if (rename.kind === "editing") {
                                            setRename({ ...rename, draft: e.target.value, error: null });
                                        }
                                    }}
                                    onKeyDown={handleRenameKeyDown}
                                    onBlur={handleRenameBlur}
                                    disabled={rename.kind === "saving"}
                                    autoFocus
                                    onFocus={(e) => e.currentTarget.select()}
                                    aria-label={t(T.nomAgent)}
                                    aria-invalid={rename.kind === "editing" && rename.error !== null}
                                    className="h-8 max-w-xs border-border bg-muted text-base font-medium text-foreground"
                                />
                                {rename.kind === "editing" && rename.error && (
                                    <span className="text-xs text-destructive" role="alert">
                                        {rename.error}
                                    </span>
                                )}
                            </div>
                        ) : isViewingHistoricalVersion ? (
                            <h1 className="max-w-[14rem] truncate text-base font-medium text-foreground md:max-w-md">{workflowName}</h1>
                        ) : (
                            // Le nom est le bouton : un clic le renomme.
                            <button
                                ref={renameButtonRef}
                                type="button"
                                onClick={enterEditMode}
                                aria-label={`${t(T.renommer)} : ${workflowName}`}
                                title={t(T.renommer)}
                                className="group flex max-w-[14rem] cursor-pointer items-center gap-1.5 rounded-lg px-2 py-1 hover:bg-accent md:max-w-md"
                            >
                                <h1 className="truncate text-base font-medium text-foreground">{workflowName}</h1>
                                <Pencil className="size-3.5 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100" aria-hidden />
                            </button>
                        )}
                    </div>

                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="sm" className="cursor-pointer gap-1 hover:font-medium" data-menu-version>
                                <History className="size-4 text-muted-foreground" aria-hidden />
                                {activeVersionLabel ?? t(T.version)}
                                <ChevronDown className="size-3.5" aria-hidden />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="start">
                            <DropdownMenuItem asChild className="cursor-pointer hover:font-medium">
                                <Link href={adresseOnglet(workflowId, "versions")}>{t(T.toutesLesVersions)}</Link>
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>

                <div className="flex items-center gap-2">
                    {isViewingHistoricalVersion && (
                        <>
                            <div className="flex items-center gap-2 rounded-md bg-muted px-3 py-1.5">
                                <Eye className="size-4 text-foreground" />
                                <span className="text-sm text-foreground">
                                    {activeVersionLabel} · {t(T.versionPassee)}
                                </span>
                            </div>
                            <Button onClick={onBackToDraft} className="cursor-pointer px-4">
                                {t(T.retourBrouillon)}
                            </Button>
                        </>
                    )}

                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" className="cursor-pointer gap-1.5 hover:font-medium" data-menu-essayer>
                                <Play className="size-4" aria-hidden />
                                {t(T.essayer)}
                                <ChevronDown className="size-3.5" aria-hidden />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => onTestAgentClick("audio")} className="cursor-pointer hover:font-medium">
                                <Play className="mr-2 size-4" />
                                {t(T.navigateur)}
                            </DropdownMenuItem>
                            {!isViewingHistoricalVersion && (
                                <DropdownMenuItem
                                    disabled={isCallDisabled}
                                    onClick={onPhoneCallClick}
                                    className="cursor-pointer hover:font-medium"
                                >
                                    <Phone className="mr-2 size-4" />
                                    {t(T.telephone)}
                                </DropdownMenuItem>
                            )}
                            <DropdownMenuItem onClick={() => onTestAgentClick("text")} className="cursor-pointer hover:font-medium">
                                <Keyboard className="mr-2 size-4" />
                                {t(T.clavier)}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => onTestAgentClick("simulated")} className="cursor-pointer hover:font-medium">
                                <Users className="mr-2 size-4" />
                                {t(T.appelantSimule)}
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem asChild className="cursor-pointer hover:font-medium">
                                <Link href={adresseOnglet(workflowId, "tests")}>
                                    <FlaskConical className="mr-2 size-4" />
                                    {t(T.jouerLesTests)}
                                </Link>
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>

                    {/* [.mark] Lot 4 du builder : « Builder IA » */}
                    {builder && !isViewingHistoricalVersion && <BarreDuBuilder ouvert={builder.ouvert} onToggle={builder.onToggle} />}

                    {!isViewingHistoricalVersion && hasDraft && raison && (
                        <span className="max-w-40 truncate text-xs text-muted-foreground" data-raison-publication title={raison}>
                            {raison}
                        </span>
                    )}
                    {!isViewingHistoricalVersion && hasDraft && (
                        <Button
                            onClick={handlePublish}
                            title={raison ?? undefined}
                            disabled={isDirty || publishing || hasValidationErrors || Boolean(raison)}
                            variant="outline"
                            className="cursor-pointer border-border px-4"
                        >
                            {publishing ? (
                                <>
                                    <LoaderCircle className="mr-2 size-4 animate-spin" />
                                    {t(T.publication)}
                                </>
                            ) : (
                                <>
                                    <Rocket className="mr-2 size-4" />
                                    {t(T.publier)}
                                </>
                            )}
                        </Button>
                    )}

                    {!isViewingHistoricalVersion && (
                        <Button onClick={handleSave} disabled={!isDirty || savingWorkflow} className="cursor-pointer px-4">
                            {savingWorkflow ? (
                                <>
                                    <LoaderCircle className="mr-2 size-4 animate-spin" />
                                    {t(T.enregistrement)}
                                </>
                            ) : (
                                t(T.enregistrer)
                            )}
                        </Button>
                    )}

                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="cursor-pointer text-muted-foreground hover:bg-accent hover:text-foreground" aria-label={t(T.menuAgent)}>
                                <MoreVertical className="size-5" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem asChild className="cursor-pointer hover:font-medium">
                                <Link href={adresseOnglet(workflowId, "appels")}>
                                    <History className="mr-2 size-4" />
                                    {t(T.appels)}
                                </Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={handleDuplicate} disabled={duplicating} className="cursor-pointer hover:font-medium">
                                {duplicating ? <LoaderCircle className="mr-2 size-4 animate-spin" /> : <Copy className="mr-2 size-4" />}
                                {duplicating ? t(T.duplication) : t(T.dupliquer)}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={handleDownloadWorkflow} className="cursor-pointer hover:font-medium">
                                <Download className="mr-2 size-4" />
                                {t(T.telecharger)}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={() => setEtiquettesOuvert(true)} className="cursor-pointer hover:font-medium">
                                <Tag className="mr-2 size-4" />
                                {t(T.etiquettes)}
                            </DropdownMenuItem>
                            <DropdownMenuItem onClick={handleCopyAgentUuid} disabled={!workflowUuid} className="cursor-pointer hover:font-medium">
                                <Clipboard className="mr-2 size-4" />
                                {t(T.copierUuid)}
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>
            </div>

            <FenetreEtiquettes agentId={workflowId} ouvert={etiquettesOuvert} onOuvertChange={setEtiquettesOuvert} />
            <OngletsAgent
                agentId={workflowId}
                actif="parcours"
                debut={<MenuMembre agentId={workflowId} onglet="parcours" />}
                droite={
                    <>
                        {isDirty && !isViewingHistoricalVersion && (
                            <span className="flex items-center gap-2 text-sm text-foreground" data-non-enregistre>
                                <span className="size-2 rounded-full bg-(--acc)" />
                                {t(T.nonEnregistre)}
                            </span>
                        )}
                        {hasValidationErrors && (
                            <Popover>
                                <PopoverTrigger asChild>
                                    <button className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1 transition-colors hover:bg-accent hover:font-medium">
                                        <AlertCircle className="size-4 text-destructive" />
                                        <span className="text-sm text-destructive">
                                            {workflowValidationErrors.length} {workflowValidationErrors.length === 1 ? t(T.erreur) : t(T.erreurs)}
                                        </span>
                                    </button>
                                </PopoverTrigger>
                                <PopoverContent align="end" className="w-80 border-border bg-card p-0">
                                    <div className="border-b border-border px-4 py-3">
                                        <h3 className="text-sm font-medium text-foreground">{t(T.erreursTitre)}</h3>
                                    </div>
                                    <div className="max-h-64 overflow-y-auto">
                                        {workflowValidationErrors.map((error, index) => (
                                            <div key={index} className="border-b border-border px-4 py-3 last:border-b-0">
                                                <div className="flex items-start gap-2">
                                                    <AlertCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
                                                    <div className="min-w-0 flex-1">
                                                        {(error.kind === "node" || error.kind === "edge") && error.id && (
                                                            <p className="mb-1 text-xs text-muted-foreground">
                                                                {error.kind === "node" ? t(T.noeud) : t(T.liaison)} : {error.id}
                                                                {error.field && <span> • {error.field}</span>}
                                                            </p>
                                                        )}
                                                        <p className="break-words text-sm text-foreground">{error.message}</p>
                                                    </div>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </PopoverContent>
                            </Popover>
                        )}
                    </>
                }
            />
        </div>
    );
};
