"use client";

/**
 * [.mark] K2 : la liste des agents, reprise de la maquette (`liste-agents.tsx`, proposition C du 01/11) : dossiers à gauche,
 * recherche et filtres en pastilles (État, Étiquettes), tableau épuré (Agent · Version · Appels 7 j · Modifié), sans cadre.
 * Tout vient de la route : les dossiers, les groupes, les versions, les appels. Ce que la maquette ne montre pas et que
 * le serveur sait faire (déplacer, dupliquer, archiver, dossiers et sous-dossiers) vit dans le menu « ⋯ » de la ligne
 * et celui du dossier.
 */
import { Archive, Copy, Folder, FolderPlus, MoreHorizontal, Pencil, Plus, RotateCcw, Search, Tag, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import {
    createFolderApiV1FolderPost,
    deleteFolderApiV1FolderFolderIdDelete,
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost,
    moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut,
    renameFolderApiV1FolderFolderIdPut,
    updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut,
} from "@/client/sdk.gen";
import type { FolderResponse, LienDeGroupe, WorkflowListResponse } from "@/client/types.gen";
import { etiquettesDuFiltre, filtrerLesAgents } from "@/components/mark/agent/etiquettes/logique";
import { useEtiquettes } from "@/components/mark/agent/etiquettes/useEtiquettes";
import { ModaleNouvelAgent } from "@/components/mark/agent/ModaleNouvelAgent";
import { BadgeGroupe } from "@/components/mark/groupe/BadgeGroupe";
import { ChoixSpecialisesArchivage } from "@/components/mark/groupe/ChoixSpecialisesArchivage";
import { arbreDesDossiers, descendants, type NoeudDeDossier, rolesDesAgents } from "@/components/mark/groupe/liens-groupes";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { PointEtat } from "@/components/mark/studio/marques";
import { PageStudio, TitrePage } from "@/components/mark/studio/shell-studio";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuCheckboxItem,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuSub,
    DropdownMenuSubContent,
    DropdownMenuSubTrigger,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { UploadWorkflowButton } from "@/components/workflow/UploadWorkflowButton";
import { useOrganizationTimezone } from "@/hooks/useOrganizationTimezone";

import { adresseOnglet } from "./onglets-agent";

const T = {
    titre: { en: "Agents", fr: "Agents" },
    nouvelAgent: { en: "New agent", fr: "Nouvel agent" },
    tous: { en: "All agents", fr: "Tous les agents" },
    dossiers: { en: "FOLDERS", fr: "DOSSIERS" },
    archives: { en: "Archived", fr: "Archivés" },
    nouveauDossier: { en: "New folder", fr: "Nouveau dossier" },
    rechercher: { en: "Search an agent", fr: "Rechercher un agent" },
    etat: { en: "State", fr: "État" },
    etatInfo: { en: "Only show published agents, drafts or modified drafts.", fr: "Ne montrer que les agents publiés, en brouillon ou en brouillon modifié." },
    etiquettes: { en: "Labels", fr: "Étiquettes" },
    etiquettesInfo: { en: "Labels are set on the agent's page (menu « … › Labels »).", fr: "Les étiquettes se posent dans la page de l'agent (menu « … › Étiquettes »)." },
    toutEffacer: { en: "Clear all", fr: "Tout effacer" },
    agent: { en: "Agent", fr: "Agent" },
    version: { en: "Version", fr: "Version" },
    appels: { en: "Calls 7 d", fr: "Appels 7 j" },
    modifie: { en: "Modified", fr: "Modifié" },
    aucun: { en: "No agent", fr: "Aucun agent" },
    publiee: { en: "published", fr: "publiée" },
    brouillon: { en: "draft", fr: "brouillon" },
    brouillonModifie: { en: "modified draft", fr: "brouillon modifié" },
    aujourdhui: { en: "today", fr: "aujourd'hui" },
    menuLigne: { en: "Agent actions", fr: "Actions de l'agent" },
    ouvrir: { en: "Open", fr: "Ouvrir" },
    dupliquer: { en: "Duplicate", fr: "Dupliquer" },
    nomDuDossier: { en: "Folder name", fr: "Nom du dossier" },
    deplacer: { en: "Move to a folder", fr: "Déplacer vers un dossier" },
    sansDossier: { en: "No folder", fr: "Sans dossier" },
    archiver: { en: "Archive", fr: "Archiver" },
    restaurer: { en: "Restore", fr: "Restaurer" },
    menuDossier: { en: "Folder actions", fr: "Actions du dossier" },
    renommer: { en: "Rename", fr: "Renommer" },
    supprimer: { en: "Delete", fr: "Supprimer" },
    sousDossier: { en: "New sub-folder", fr: "Nouveau sous-dossier" },
    titreDossier: { en: "New folder", fr: "Nouveau dossier" },
    titreRenommer: { en: "Rename the folder", fr: "Renommer le dossier" },
    creer: { en: "Create", fr: "Créer" },
    supprimerDossierTitre: { en: "Delete the folder?", fr: "Supprimer le dossier ?" },
    supprimerDossierTexte: { en: "Its agents are not deleted: they move out of the folder.", fr: "Ses agents ne sont pas supprimés : ils sortent du dossier." },
    annuler: { en: "Cancel", fr: "Annuler" },
} satisfies Record<string, Texte>;

type Dossier = number | "archives" | null;
type EtatAgent = "publiee" | "brouillon" | "brouillon_modifie";

// Filtre en pastille : un menu à cocher ; la pastille dit combien de valeurs sont retenues (maquette).
function Filtre({
    icone,
    nom,
    info,
    options,
    choisis,
    changer,
    effacer,
}: {
    icone: React.ReactNode;
    nom: string;
    info: string;
    options: { valeur: string; libelle: string }[];
    choisis: string[];
    changer: (v: string[]) => void;
    effacer: string;
}) {
    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button variant={choisis.length ? "secondary" : "outline"} size="sm" className="rounded-full" title={info}>
                    {icone} {nom}
                    {choisis.length > 0 && <span className="ml-0.5 text-xs">· {choisis.length}</span>}
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
                {options.length === 0 && <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">—</DropdownMenuLabel>}
                {options.map((o) => (
                    <DropdownMenuCheckboxItem
                        key={o.valeur}
                        checked={choisis.includes(o.valeur)}
                        onSelect={(e) => e.preventDefault()}
                        onCheckedChange={() => changer(choisis.includes(o.valeur) ? choisis.filter((x) => x !== o.valeur) : [...choisis, o.valeur])}
                    >
                        {o.libelle}
                    </DropdownMenuCheckboxItem>
                ))}
                {choisis.length > 0 && (
                    <>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem onClick={() => changer([])}>{effacer}</DropdownMenuItem>
                    </>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}

export function ListeAgents({
    actifs,
    archives,
    dossiers,
    liens,
    dossierOuvertId,
}: {
    actifs: WorkflowListResponse[];
    archives: WorkflowListResponse[];
    dossiers: FolderResponse[];
    liens: LienDeGroupe[];
    dossierOuvertId: number | null;
}) {
    const { t } = useLangue();
    const router = useRouter();
    const fuseau = useOrganizationTimezone();
    const [, demarrer] = useTransition();
    const { donnees: donneesEtiquettes } = useEtiquettes();
    const [creation, setCreation] = useState(false);
    const [q, setQ] = useState("");
    const [dossier, setDossier] = useState<Dossier>(dossierOuvertId);
    const [etats, setEtats] = useState<string[]>([]);
    const [etiquettes, setEtiquettes] = useState<string[]>([]);
    const [creationDossier, setCreationDossier] = useState<{ parentId: number | null } | null>(null);
    const [renommage, setRenommage] = useState<FolderResponse | null>(null);
    const [suppression, setSuppression] = useState<FolderResponse | null>(null);
    const [principalAArchiver, setPrincipalAArchiver] = useState<{ id: number; name: string } | null>(null);

    const tous = useMemo(() => [...actifs, ...archives], [actifs, archives]);
    const roles = useMemo(() => rolesDesAgents(liens, new Map(tous.map((w) => [w.id, w.name]))), [liens, tous]);
    const arbre = useMemo(() => arbreDesDossiers(dossiers), [dossiers]);
    const dansDossier = useMemo(() => {
        if (typeof dossier !== "number") return null;
        return new Set([dossier, ...descendants(dossiers, dossier)]);
    }, [dossier, dossiers]);
    const compte = (id: number) => {
        const ids = new Set([id, ...descendants(dossiers, id)]);
        return actifs.filter((w) => w.folder_id != null && ids.has(w.folder_id)).length;
    };

    const baseDeLaVue = dossier === "archives" ? archives : dansDossier ? actifs.filter((w) => w.folder_id != null && dansDossier.has(w.folder_id)) : actifs;
    const parEtiquette = filtrerLesAgents(baseDeLaVue, donneesEtiquettes?.par_agent, etiquettes);
    const visibles = parEtiquette.filter(
        (w) => w.name.toLowerCase().includes(q.toLowerCase()) && (!etats.length || etats.includes(w.version_etat ?? "brouillon")),
    );

    const libelleEtat = (e: string) => (e === "publiee" ? t(T.publiee) : e === "brouillon_modifie" ? t(T.brouillonModifie) : t(T.brouillon));
    const effacerTout = () => {
        setQ("");
        setEtats([]);
        setEtiquettes([]);
        setDossier(null);
    };

    const rafraichir = () => demarrer(() => router.refresh());

    const archiverOuRestaurer = async (w: WorkflowListResponse) => {
        const role = roles.get(w.id);
        if (w.status === "active" && role?.role === "principal" && role.specialises.length > 0) {
            setPrincipalAArchiver({ id: w.id, name: w.name });
            return;
        }
        const nouveau = w.status === "active" ? "archived" : "active";
        const reponse = await updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut({ path: { workflow_id: w.id }, body: { status: nouveau } });
        if (reponse.error) {
            notifier.echec({ fr: "Opération impossible. Réessayez.", en: "Could not complete. Try again." });
            return;
        }
        notifier.reversible(
            nouveau === "archived" ? { fr: "Agent archivé.", en: "Agent archived." } : { fr: "Agent restauré.", en: "Agent restored." },
            async () => {
                await updateWorkflowStatusApiV1WorkflowWorkflowIdStatusPut({ path: { workflow_id: w.id }, body: { status: w.status } });
                rafraichir();
            },
        );
        rafraichir();
    };

    const deplacer = async (w: WorkflowListResponse, vers: number | null) => {
        const reponse = await moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut({ path: { workflow_id: w.id }, body: { folder_id: vers } });
        if (reponse.error) {
            notifier.echec({ fr: "Déplacement impossible. Réessayez.", en: "Could not move. Try again." });
            return;
        }
        const avant = w.folder_id ?? null;
        notifier.reversible(
            vers === null ? { fr: "Agent sorti du dossier.", en: "Agent moved out of the folder." } : { fr: "Agent déplacé.", en: "Agent moved." },
            async () => {
                await moveWorkflowToFolderApiV1WorkflowWorkflowIdFolderPut({ path: { workflow_id: w.id }, body: { folder_id: avant } });
                rafraichir();
            },
        );
        rafraichir();
    };

    const dupliquer = async (w: WorkflowListResponse) => {
        const reponse = await duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost({ path: { workflow_id: w.id } });
        if (reponse.error) {
            notifier.echec({ fr: "Duplication impossible. Réessayez.", en: "Could not duplicate. Try again." });
            return;
        }
        const copie = reponse.data?.id;
        notifier.succes(
            { fr: "Agent dupliqué. La copie est à la racine de la liste.", en: "Agent duplicated. The copy is at the root of the list." },
            copie === undefined ? undefined : { bouton: { libelle: { fr: "Ouvrir la copie", en: "Open the copy" }, action: () => router.push(adresseOnglet(copie, "parcours")) } },
        );
        rafraichir();
    };

    const creerDossier = async (nom: string) => {
        const reponse = await createFolderApiV1FolderPost({ body: { name: nom, parent_id: creationDossier?.parentId ?? undefined } });
        if (reponse.error) {
            notifier.echec({ fr: "Dossier non créé. Réessayez.", en: "Folder not created. Try again." });
            throw new Error("dossier");
        }
        notifier.succes({ fr: `Dossier « ${nom} » créé.`, en: `Folder "${nom}" created.` });
        rafraichir();
    };

    const renommer = async (nom: string) => {
        if (!renommage) return;
        const reponse = await renameFolderApiV1FolderFolderIdPut({ path: { folder_id: renommage.id }, body: { name: nom } });
        if (reponse.error) {
            notifier.echec({ fr: "Dossier non renommé. Réessayez.", en: "Folder not renamed. Try again." });
            throw new Error("renommer");
        }
        notifier.succes({ fr: "Dossier renommé.", en: "Folder renamed." });
        rafraichir();
    };

    const supprimer = async () => {
        if (!suppression) return;
        const { id, name } = suppression;
        setSuppression(null);
        notifier.annulable(
            { fr: `Dossier « ${name} » supprimé.`, en: `Folder "${name}" deleted.` },
            {
                restaurer: () => undefined,
                executer: async () => {
                    const reponse = await deleteFolderApiV1FolderFolderIdDelete({ path: { folder_id: id } });
                    if (reponse.error) notifier.echec({ fr: "Dossier non supprimé. Réessayez.", en: "Folder not deleted. Try again." });
                    else {
                        if (dossier === id) setDossier(null);
                        rafraichir();
                    }
                },
            },
        );
    };

    const ligneDossier = (n: NoeudDeDossier, profondeur: number): React.ReactNode => (
        <div key={n.dossier.id}>
            <div
                className={`group relative flex w-full items-center rounded-lg text-sm ${dossier === n.dossier.id ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted"}`}
                style={{ paddingLeft: profondeur * 14 }}
            >
                <button type="button" onClick={() => setDossier(n.dossier.id)} className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-3 py-2 text-left">
                    <Folder className="size-4 shrink-0" /> <span className="truncate">{n.dossier.name}</span>
                    <span className="ml-auto text-xs group-focus-within:invisible group-hover:invisible">{compte(n.dossier.id)}</span>
                </button>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="absolute right-1 top-1/2 size-6 -translate-y-1/2 opacity-0 focus-visible:opacity-100 group-hover:opacity-100" aria-label={t(T.menuDossier)}>
                            <MoreHorizontal className="size-3.5" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setRenommage(n.dossier)}>
                            <Pencil className="mr-2 size-4" /> {t(T.renommer)}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setCreationDossier({ parentId: n.dossier.id })}>
                            <FolderPlus className="mr-2 size-4" /> {t(T.sousDossier)}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => setSuppression(n.dossier)} className="text-destructive focus:text-destructive">
                            <Trash2 className="mr-2 size-4" /> {t(T.supprimer)}
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
            {n.enfants.map((e) => ligneDossier(e, profondeur + 1))}
        </div>
    );

    const motsDuFiltre =
        q || [...etats.map(libelleEtat), ...etiquettes, typeof dossier === "number" ? (dossiers.find((d) => d.id === dossier)?.name ?? "") : ""].filter(Boolean).join(", ");

    return (
        <PageStudio>
            <TitrePage
                titre={t(T.titre)}
                action={
                    <div className="flex gap-2">
                        <UploadWorkflowButton />
                        <Button onClick={() => setCreation(true)}>
                            <Plus className="size-4" /> {t(T.nouvelAgent)}
                        </Button>
                    </div>
                }
            />
            {tous.length === 0 && dossiers.length === 0 ? (
                <EtatVide cas="premier" icone={Workflow} titre={t(T.aucun)} />
            ) : (
                <div className="grid gap-6 lg:grid-cols-[200px_1fr]">
                    <aside className="space-y-1">
                        <button
                            type="button"
                            onClick={() => setDossier(null)}
                            className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm ${dossier === null ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted"}`}
                        >
                            <Workflow className="size-4" /> {t(T.tous)} <span className="ml-auto text-xs">{actifs.length}</span>
                        </button>
                        <p className="px-3 pb-1 pt-3 text-[10px] font-semibold tracking-wider text-muted-foreground">{t(T.dossiers)}</p>
                        {arbre.map((n) => ligneDossier(n, 0))}
                        {archives.length > 0 && (
                            <button
                                type="button"
                                onClick={() => setDossier("archives")}
                                className={`flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm ${dossier === "archives" ? "bg-accent font-medium text-accent-foreground" : "hover:bg-muted"}`}
                            >
                                <Archive className="size-4" /> {t(T.archives)} <span className="ml-auto text-xs">{archives.length}</span>
                            </button>
                        )}
                        <button
                            type="button"
                            onClick={() => setCreationDossier({ parentId: null })}
                            className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:font-medium"
                        >
                            <FolderPlus className="size-4" /> {t(T.nouveauDossier)}
                        </button>
                    </aside>
                    <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                            <div className="relative w-full max-w-72">
                                <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                                <Input
                                    value={q}
                                    onChange={(e) => setQ(e.target.value)}
                                    placeholder={t(T.rechercher)}
                                    className="h-9 border-transparent bg-muted/50 pl-9 shadow-none focus-visible:bg-background"
                                />
                            </div>
                            <Filtre
                                icone={<Plus className="size-3.5" />}
                                nom={t(T.etat)}
                                info={t(T.etatInfo)}
                                options={(["publiee", "brouillon", "brouillon_modifie"] as EtatAgent[]).map((e) => ({ valeur: e, libelle: libelleEtat(e) }))}
                                choisis={etats}
                                changer={setEtats}
                                effacer={t(T.toutEffacer)}
                            />
                            <Filtre
                                icone={<Tag className="size-3.5" />}
                                nom={t(T.etiquettes)}
                                info={t(T.etiquettesInfo)}
                                options={etiquettesDuFiltre(donneesEtiquettes).map((e) => ({ valeur: e, libelle: e }))}
                                choisis={etiquettes}
                                changer={setEtiquettes}
                                effacer={t(T.toutEffacer)}
                            />
                        </div>
                        {visibles.length === 0 ? (
                            // K2b : sans recherche ni filtre, une liste vide est « Aucun agent » (état premier), pas « Aucun résultat pour «  » ».
                            motsDuFiltre === "" ? (
                                <EtatVide cas="premier" icone={Workflow} titre={t(T.aucun)} />
                            ) : (
                                <EtatVide cas="filtre" recherche={motsDuFiltre} effacer={effacerTout} />
                            )
                        ) : (
                            <table className="w-full text-sm">
                                <thead className="border-b text-xs text-muted-foreground">
                                    <tr>
                                        <th className="py-2 text-left font-normal">{t(T.agent)}</th>
                                        <th className="text-left font-normal">{t(T.version)}</th>
                                        <th className="text-right font-normal">{t(T.appels)}</th>
                                        <th className="text-right font-normal">{t(T.modifie)}</th>
                                        <th className="w-10" />
                                    </tr>
                                </thead>
                                <tbody className="divide-y">
                                    {visibles.map((w) => {
                                        const etat = (w.version_etat ?? "brouillon") as EtatAgent;
                                        return (
                                            <tr key={w.id} className="hover:bg-muted/40" data-agent={w.id}>
                                                <td className="py-3">
                                                    <Link href={adresseOnglet(w.id, "parcours")} className="flex items-center gap-2 font-medium">
                                                        {w.name}
                                                        <BadgeGroupe role={roles.get(w.id)} />
                                                    </Link>
                                                </td>
                                                <td>
                                                    <PointEtat etat={etat === "publiee" ? "publie" : "brouillon"}>
                                                        {w.version_numero != null ? `v${w.version_numero} ` : ""}
                                                        {libelleEtat(etat)}
                                                    </PointEtat>
                                                </td>
                                                <td className="text-right tabular-nums text-muted-foreground">{w.appels_7j ?? 0}</td>
                                                <td className="text-right text-muted-foreground"><DateRelative valeur={w.modifie_le ?? w.created_at} fuseau={fuseau} /></td>
                                                <td className="text-right">
                                                    <DropdownMenu>
                                                        <DropdownMenuTrigger asChild>
                                                            <Button variant="ghost" size="icon" className="size-7" aria-label={`${t(T.menuLigne)} : ${w.name}`}>
                                                                <MoreHorizontal className="size-4" />
                                                            </Button>
                                                        </DropdownMenuTrigger>
                                                        <DropdownMenuContent align="end">
                                                            <DropdownMenuItem asChild>
                                                                <Link href={adresseOnglet(w.id, "parcours")}>{t(T.ouvrir)}</Link>
                                                            </DropdownMenuItem>
                                                            {w.status === "active" && (
                                                                <>
                                                                    <DropdownMenuSub>
                                                                        <DropdownMenuSubTrigger>{t(T.deplacer)}</DropdownMenuSubTrigger>
                                                                        <DropdownMenuSubContent>
                                                                            <DropdownMenuItem disabled={w.folder_id == null} onClick={() => void deplacer(w, null)}>
                                                                                {t(T.sansDossier)}
                                                                            </DropdownMenuItem>
                                                                            {dossiers.map((d) => (
                                                                                <DropdownMenuItem key={d.id} disabled={d.id === w.folder_id} onClick={() => void deplacer(w, d.id)}>
                                                                                    {d.name}
                                                                                </DropdownMenuItem>
                                                                            ))}
                                                                        </DropdownMenuSubContent>
                                                                    </DropdownMenuSub>
                                                                    <DropdownMenuItem onClick={() => void dupliquer(w)}>
                                                                        <Copy className="mr-2 size-4" /> {t(T.dupliquer)}
                                                                    </DropdownMenuItem>
                                                                </>
                                                            )}
                                                            <DropdownMenuItem onClick={() => void archiverOuRestaurer(w)}>
                                                                {w.status === "active" ? (
                                                                    <>
                                                                        <Archive className="mr-2 size-4" /> {t(T.archiver)}
                                                                    </>
                                                                ) : (
                                                                    <>
                                                                        <RotateCcw className="mr-2 size-4" /> {t(T.restaurer)}
                                                                    </>
                                                                )}
                                                            </DropdownMenuItem>
                                                        </DropdownMenuContent>
                                                    </DropdownMenu>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>
                </div>
            )}

            <ModaleNouvelAgent ouvert={creation} fermer={() => setCreation(false)} dossierId={null} />
            <FenetreChamps
                ouverte={creationDossier !== null}
                fermer={() => setCreationDossier(null)}
                titre={t(creationDossier?.parentId ? T.sousDossier : T.titreDossier)}
                valider={t(T.creer)}
                sections={[{ champs: [{ id: "nom", t: "texte", l: t(T.nomDuDossier), v: "" }] }]}
                onValider={(v) => {
                    const nom = String(v.nom ?? "").trim();
                    if (nom) return creerDossier(nom).then(() => true, () => false);
                }}
            />
            <FenetreChamps
                ouverte={renommage !== null}
                fermer={() => setRenommage(null)}
                titre={t(T.titreRenommer)}
                valider={t(T.renommer)}
                sections={[{ champs: [{ id: "nom", t: "texte", l: t(T.nomDuDossier), v: renommage?.name ?? "" }] }]}
                onValider={(v) => {
                    const nom = String(v.nom ?? "").trim();
                    if (nom && nom !== renommage?.name) return renommer(nom).then(() => true, () => false);
                }}
            />
            <AlertDialog open={suppression !== null} onOpenChange={(o) => !o && setSuppression(null)}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>{t(T.supprimerDossierTitre)}</AlertDialogTitle>
                        <AlertDialogDescription>
                            {suppression?.name} · {t(T.supprimerDossierTexte)}
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel>{t(T.annuler)}</AlertDialogCancel>
                        <AlertDialogAction
                            onClick={(e) => {
                                e.preventDefault();
                                void supprimer();
                            }}
                            className="bg-destructive text-white hover:bg-destructive/90"
                        >
                            {t(T.supprimer)}
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
            <ChoixSpecialisesArchivage
                principal={principalAArchiver}
                nombre={principalAArchiver ? (roles.get(principalAArchiver.id)?.specialises.length ?? 0) : 0}
                onFerme={() => setPrincipalAArchiver(null)}
                onFait={rafraichir}
            />
        </PageStudio>
    );
}
