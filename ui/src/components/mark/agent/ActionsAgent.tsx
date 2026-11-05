"use client";

/**
 * [.mark] K2 : les actions à droite de la barre d'un agent, reprises de la maquette (`app/agents/[id]/page.tsx`) :
 * version ⌄ (point vert publiée, point creux brouillon) · Essayer ⌄ · Builder IA · Publier · ⋮.
 * Les mêmes sur le Parcours et sur les autres onglets. Sur le Parcours, `editeur` branche l'essai, le builder et
 * l'enregistrement de l'éditeur ; ailleurs, chaque entrée ouvre le Parcours là où l'éditeur la prend (`?essai=`,
 * `?builder=1`), sans rien dupliquer.
 */
import type { ReactFlowInstance } from "@xyflow/react";
import { ChevronDown, Clipboard, Copy, Download, FolderInput, FolderOutput, FlaskConical, Globe, History, Keyboard, MoreHorizontal, Pencil, Percent, Phone, Play, Send, Sparkles, Tag, Undo2, Users } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import {
    duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost,
    getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet,
} from "@/client/sdk.gen";
import type { WorkflowVersionResponse } from "@/client/types.gen";
import { BarreDuBuilder } from "@/components/builder/ecran/BarreDuBuilder";
import type { FlowEdge, FlowNode } from "@/components/flow/types";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { FenetreChamps } from "@/components/mark/studio/fenetre-champs";
import { PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuth } from "@/lib/auth";
import { ouvrirBranche } from "@/lib/brancheOuverte";
import { copyTextToClipboard } from "@/lib/clipboard";
import { espaceRetenu } from "@/lib/espaceCourant";

import { FenetreFusion, type SensDeFusion } from "./branches/FenetreFusion";
import { FenetreNouvelleBranche } from "./branches/FenetreNouvelleBranche";
import { FenetreRepartition } from "./branches/FenetreRepartition";
import { FenetreVersions } from "./branches/FenetreVersions";
import { SelecteurBranche } from "./branches/SelecteurBranche";
import { useBranches } from "./branches/useBranches";
import { FenetreCopieAgent } from "./copie/FenetreCopieAgent";
import { definitionSansSecrets } from "./definition-sans-secrets";
import { FenetreEtiquettes } from "./etiquettes/FenetreEtiquettes";
import { FenetreExportFichiers, FenetreImportFichiers } from "./fichiers/FenetreFichiersAgent";
import { adresseOnglet } from "./onglets-agent";
import { FenetreDePublication } from "./publication/FenetreDePublication";

export type ModeEssai = "audio" | "text" | "simulated";

/** Ce que l'éditeur du Parcours met à la disposition des actions ; absent, les actions ouvrent le Parcours. */
export type EditeurAgent = {
    estModifie: boolean;
    erreursDuParcours: number;
    rfInstance: React.RefObject<ReactFlowInstance<FlowNode, FlowEdge> | null>;
    enregistrer: () => Promise<void>;
    onEssayer: (mode: ModeEssai) => void;
    onTelephone: () => void;
    onPublie: () => void;
    builder: { ouvert: boolean; onToggle: () => void; raisonDeBlocage: string | null };
    renommer: (nom: string) => Promise<void>;
    /** La version affichée est une version passée (lecture seule). */
    versionPassee: boolean;
    retourAuBrouillon: () => void;
};

const T = {
    versions: { en: "Versions", fr: "Versions" },
    toutesLesVersions: { en: "All versions", fr: "Toutes les versions" },
    repartition: { en: "Traffic split", fr: "Répartition du trafic" },
    brouillonDeTravail: { en: "Working draft", fr: "Brouillon de travail" },
    brouillon: { en: "draft", fr: "brouillon" },
    publiee: { en: "published", fr: "publiée" },
    essayer: { en: "Try", fr: "Essayer" },
    builder: { en: "Builder AI", fr: "Builder IA" },
    navigateur: { en: "Call in the browser", fr: "Appel dans le navigateur" },
    telephone: { en: "Phone call", fr: "Appel téléphonique" },
    clavier: { en: "With the keyboard", fr: "Au clavier" },
    appelantSimule: { en: "Simulated caller", fr: "Appelant simulé" },
    jouerLesTests: { en: "Play the tests", fr: "Jouer les tests" },
    publier: { en: "Publish", fr: "Publier" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    enregistrement: { en: "Saving...", fr: "Enregistrement..." },
    nonEnregistre: { en: "Unsaved changes", fr: "Non enregistré" },
    retourBrouillon: { en: "Back to draft", fr: "Retour au brouillon" },
    lectureSeule: { en: "Read only", fr: "Lecture seule" },
    menuAgent: { en: "Agent menu", fr: "Menu de l'agent" },
    appels: { en: "See the calls", fr: "Voir les appels" },
    exporter: { en: "Export to a client", fr: "Exporter vers un client" },
    ramener: { en: "Bring back to the Labo", fr: "Ramener au Labo" },
    avecTests: { en: "With its tests", fr: "Avec ses tests" },
    etiquettes: { en: "Labels", fr: "Étiquettes" },
    renommer: { en: "Rename", fr: "Renommer" },
    nomAgent: { en: "Agent name", fr: "Nom de l'agent" },
    dupliquer: { en: "Duplicate", fr: "Dupliquer" },
    duplication: { en: "Duplicating...", fr: "Duplication..." },
    telecharger: { en: "Download (JSON)", fr: "Télécharger (JSON)" },
    exporterFichiers: { en: "Export as files", fr: "Exporter en fichiers" },
    importerFichiers: { en: "Import files", fr: "Importer des fichiers" },
    copierId: { en: "Copy the identifier", fr: "Copier l'identifiant" },
    erreur: { en: "error", fr: "erreur" },
    erreurs: { en: "errors", fr: "erreurs" },
    titreDuplication: { en: "Duplicate the agent", fr: "Dupliquer l'agent" },
    infoDuplication: {
        en: "A copy in the same organization, as a draft. The tools, documents and keys stay the same: nothing is copied. The tests follow only if you ask.",
        fr: "Une copie dans la même organisation, en brouillon. Les outils, documents et clés restent les mêmes : rien n'est recopié. Les tests suivent seulement si vous le demandez.",
    },
    nomCopie: { en: "Name of the copy", fr: "Nom de la copie" },
    copie: { en: "(copy)", fr: "(copie)" },
    titreRenommer: { en: "Rename the agent", fr: "Renommer l'agent" },
} satisfies Record<string, Texte>;

// [.mark] SA-L3b : la version en ligne d'une BRANCHE est rangée au statut « archived » (jamais « published », réservé à la principale) ;
// sur une branche ouverte, elle porte le point plein d'une version publiée.
const POINT = (statut: string, surUneBranche = false): "publie" | "brouillon" =>
    statut === "published" || (surUneBranche && statut === "archived") ? "publie" : "brouillon";

export function ActionsAgent({
    agentId,
    nom,
    workflowUuid,
    versionNumero,
    versionStatut,
    aUnBrouillon,
    editeur,
}: {
    agentId: number;
    nom: string;
    workflowUuid?: string | null;
    versionNumero: number | null;
    versionStatut: string | null;
    aUnBrouillon: boolean;
    editeur?: EditeurAgent;
}) {
    const { t } = useLangue();
    const router = useRouter();
    const { user, loading: authLoading } = useAuth();
    const [versions, setVersions] = useState<WorkflowVersionResponse[]>([]);
    const [enregistrement, setEnregistrement] = useState(false);
    const [duplication, setDuplication] = useState(false);
    const [fenetre, setFenetre] = useState<"etiquettes" | "dupliquer" | "renommer" | "publier" | "exporter" | "ramener" | "branche" | "versions" | "repartition" | "fusion" | "fichiers-export" | "fichiers-import" | null>(null);
    // [.mark] Partie 3, SA-L3c : la fenêtre Fusionner / Mettre à jour (quelle branche, dans quel sens).
    const [fusion, setFusion] = useState<{ sens: SensDeFusion; brancheId: number } | null>(null);
    // [.mark] Partie 3, SA-L3b : la branche ouverte dans cet onglet ; en changer relit tout l'écran avec son brouillon.
    const branches = useBranches(agentId);
    const ouvrirEtRelire = (brancheId: number | null) => {
        ouvrirBranche(agentId, brancheId);
        window.location.reload();
    };
    // Espace inconnu (onglet neuf, sans mémoire) : ni les gestes du Labo ni ceux du client ne sont montrés.
    const [espace, setEspace] = useState<"labo" | "client" | null>(null);
    useEffect(() => {
        const retenu = espaceRetenu();
        setEspace(retenu === "labo" ? "labo" : typeof retenu === "number" ? "client" : null);
    }, []);

    const lire = useCallback(async () => {
        try {
            const reponse = await getWorkflowVersionsApiV1WorkflowWorkflowIdVersionsGet({ path: { workflow_id: agentId } });
            setVersions(reponse.data ?? []);
        } catch {
            setVersions([]);
        }
    }, [agentId]);
    useEffect(() => {
        if (authLoading || !user) return;
        void lire();
    }, [authLoading, user, lire, versionNumero, versionStatut]);

    const versionsTriees = [...versions].sort((a, b) => (b.version_number ?? 0) - (a.version_number ?? 0));
    const libelleVersion = versionNumero != null ? `v${versionNumero}` : t(T.brouillon);
    const surLeParcours = (suite: string) => `${adresseOnglet(agentId, "parcours")}${suite}`;
    const raison = editeur?.builder.raisonDeBlocage ?? null;
    const bloque = Boolean(editeur && (editeur.estModifie || editeur.erreursDuParcours > 0 || raison));
    // N2 (03 § 3) : la raison d'un « Publier » grisé est écrite à côté du bouton, plus seulement au survol.
    const raisonEnClair: string | null = !bloque
        ? null
        : (raison ??
          (editeur?.estModifie
              ? t({ en: "Save the changes before publishing.", fr: "Enregistrez les changements avant de publier." })
              : t({ en: "Fix the errors of the flow before publishing.", fr: "Corrigez les erreurs du parcours avant de publier." })));

    // [.mark] U11 : « Publier » ouvre TOUJOURS la fenêtre « Publier vX » (contrôles, forcer, part des appels).
    const apresPublication = async () => {
        editeur?.onPublie();
        await lire();
        if (!editeur) router.refresh();
    };

    const enregistrer = async () => {
        if (!editeur) return;
        setEnregistrement(true);
        await editeur.enregistrer();
        setEnregistrement(false);
    };

    const dupliquer = async (nomDeLaCopie: string, avecTests: boolean): Promise<boolean> => {
        if (duplication) return false;
        setDuplication(true);
        const promesse = duplicateWorkflowEndpointApiV1WorkflowWorkflowIdDuplicatePost({
            path: { workflow_id: agentId },
            // `nom` (SE-9, A-5) : le nom tapé dans la fenêtre ; le client généré le reçoit au prochain passage du générateur.
            query: { avec_tests: avecTests, nom: nomDeLaCopie.trim() } as { avec_tests: boolean },
        });
        notifier.suivre(promesse, {
            encours: { fr: "Duplication en cours…", en: "Duplicating…" },
            succes: { fr: "Agent dupliqué.", en: "Agent duplicated." },
            echec: { fr: "Duplication impossible. Réessayez.", en: "Could not duplicate. Try again." },
            echecSi: (reponse) => reponse.error,
            groupe: "duplication-agent",
        });
        try {
            const { data } = await promesse;
            if (!data?.id) return false;
            router.push(adresseOnglet(data.id, "parcours"));
            return true;
        } finally {
            setDuplication(false);
        }
    };

    const copierId = async () => {
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

    const telecharger = () => {
        const instance = editeur?.rfInstance.current;
        if (!instance) {
            router.push(surLeParcours(""));
            return;
        }
        const blob = new Blob([JSON.stringify({ name: nom, workflow_definition: definitionSansSecrets(instance.toObject()) }, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const lien = document.createElement("a");
        lien.href = url;
        lien.download = `${nom}.json`;
        document.body.appendChild(lien);
        lien.click();
        document.body.removeChild(lien);
        URL.revokeObjectURL(url);
    };

    const essayer = (mode: ModeEssai) => (editeur ? editeur.onEssayer(mode) : router.push(surLeParcours(`?essai=${mode}`)));

    return (
        <>
            {editeur?.estModifie && !editeur.versionPassee && (
                <span className="flex items-center gap-2 text-sm" data-non-enregistre>
                    <span className="size-2 rounded-full bg-(--acc)" />
                    {t(T.nonEnregistre)}
                </span>
            )}
            {editeur && editeur.erreursDuParcours > 0 && (
                <span className="text-sm text-destructive">
                    {editeur.erreursDuParcours} {editeur.erreursDuParcours === 1 ? t(T.erreur) : t(T.erreurs)}
                </span>
            )}
            {editeur?.versionPassee && (
                <>
                    <span className="text-sm text-muted-foreground">
                        {libelleVersion} · {t(T.lectureSeule)}
                    </span>
                    <Button size="sm" onClick={editeur.retourAuBrouillon}>
                        {t(T.retourBrouillon)}
                    </Button>
                </>
            )}

            {/* Branche et version : un seul repère `⑂● · v12 ▾` (Evan, 04/11) ; « Toutes les versions » en bas du menu de la version. */}
            <span className="flex items-center">
            <SelecteurBranche vue={branches.vue} ouverte={branches.ouverte} choisir={ouvrirEtRelire} nouvelle={() => setFenetre("branche")} />
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button data-menu-version className="flex cursor-pointer items-center gap-1.5 rounded-md px-2 py-1 text-sm hover:bg-muted">
                        <PointEtat etat={POINT(versionStatut ?? "draft", branches.ouverte !== null)}>{libelleVersion}</PointEtat>
                        <ChevronDown className="size-3.5 text-muted-foreground" />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuLabel className="text-xs text-muted-foreground">{t(T.versions)}</DropdownMenuLabel>
                    {aUnBrouillon && (
                        <DropdownMenuItem asChild className="cursor-pointer">
                            <Link href={adresseOnglet(agentId, "versions")}>{t(T.brouillonDeTravail)}</Link>
                        </DropdownMenuItem>
                    )}
                    {versionsTriees
                        .filter((v) => v.status !== "draft")
                        .map((v) => (
                            <DropdownMenuItem key={v.id} asChild className="cursor-pointer">
                                <Link href={adresseOnglet(agentId, "versions")}>
                                    v{v.version_number}
                                    <span className="ml-auto text-xs text-muted-foreground">
                                        {v.status === "published" ? t(T.publiee) : ""}
                                    </span>
                                </Link>
                            </DropdownMenuItem>
                        ))}
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => setFenetre("versions")} disabled={!branches.vue} className="cursor-pointer gap-2">
                        <History className="size-4" /> {t(T.toutesLesVersions)}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>
            </span>

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm" data-menu-essayer>
                        <Play className="size-3.5" /> {t(T.essayer)}
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => essayer("audio")}>
                        <Globe className="mr-2 size-4" /> {t(T.navigateur)}
                    </DropdownMenuItem>
                    {!editeur?.versionPassee && (
                        <DropdownMenuItem
                            disabled={Boolean(editeur && (editeur.estModifie || editeur.erreursDuParcours > 0))}
                            onClick={() => (editeur ? editeur.onTelephone() : router.push(surLeParcours("?essai=telephone")))}
                        >
                            <Phone className="mr-2 size-4" /> {t(T.telephone)}
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => essayer("text")}>
                        <Keyboard className="mr-2 size-4" /> {t(T.clavier)}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => essayer("simulated")}>
                        <Users className="mr-2 size-4" /> {t(T.appelantSimule)}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem asChild>
                        <Link href={adresseOnglet(agentId, "tests")}>
                            <FlaskConical className="mr-2 size-4" /> {t(T.jouerLesTests)}
                        </Link>
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            {!editeur?.versionPassee &&
                (editeur ? (
                    <BarreDuBuilder ouvert={editeur.builder.ouvert} onToggle={editeur.builder.onToggle} />
                ) : (
                    <Button variant="ghost" size="sm" asChild>
                        <Link href={surLeParcours("?builder=1")}>
                            <Sparkles className="size-3.5 text-(--acc)" /> {t(T.builder)}
                        </Link>
                    </Button>
                ))}

            {!editeur?.versionPassee && aUnBrouillon && (
                <>
                    {/* SA-V : en dessous de 1536 px, la raison reste lue (lecteur d’écran, survol de Publier) mais n’écrase plus les onglets de la barre. */}
                    {raisonEnClair && (
                        <span role="status" data-raison-publier className="sr-only max-w-64 text-xs text-muted-foreground 2xl:not-sr-only">
                            {raisonEnClair}
                        </span>
                    )}
                    <Button size="sm" onClick={() => setFenetre("publier")} disabled={bloque} title={raisonEnClair ?? undefined} className="gap-1.5">
                        {t(T.publier)}
                    </Button>
                </>
            )}
            {editeur && !editeur.versionPassee && editeur.estModifie && (
                <Button size="sm" variant="outline" onClick={enregistrer} disabled={enregistrement}>
                    {enregistrement ? t(T.enregistrement) : t(T.enregistrer)}
                </Button>
            )}

            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="size-8" aria-label={t(T.menuAgent)}>
                        <MoreHorizontal className="size-4" />
                    </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                    <DropdownMenuItem asChild>
                        <Link href={adresseOnglet(agentId, "appels")}>{t(T.appels)}</Link>
                    </DropdownMenuItem>
                    {espace === "labo" && (
                        <DropdownMenuItem onClick={() => setFenetre("exporter")}>
                            <Send className="mr-2 size-4" /> {t(T.exporter)}
                        </DropdownMenuItem>
                    )}
                    {espace === "client" && (
                        <DropdownMenuItem onClick={() => setFenetre("ramener")}>
                            <Undo2 className="mr-2 size-4" /> {t(T.ramener)}
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => setFenetre("repartition")} disabled={!branches.vue}>
                        <Percent className="mr-2 size-4" /> {t(T.repartition)}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setFenetre("etiquettes")}>
                        <Tag className="mr-2 size-4" /> {t(T.etiquettes)}
                    </DropdownMenuItem>
                    {editeur && !editeur.versionPassee && (
                        <DropdownMenuItem onClick={() => setFenetre("renommer")}>
                            <Pencil className="mr-2 size-4" /> {t(T.renommer)}
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={() => setFenetre("dupliquer")} disabled={duplication}>
                        <Copy className="mr-2 size-4" /> {t(T.dupliquer)}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={telecharger}>
                        <Download className="mr-2 size-4" /> {t(T.telecharger)}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => setFenetre("fichiers-export")}>
                        <FolderOutput className="mr-2 size-4" /> {t(T.exporterFichiers)}
                    </DropdownMenuItem>
                    {editeur && !editeur.versionPassee && (
                        <DropdownMenuItem onClick={() => setFenetre("fichiers-import")}>
                            <FolderInput className="mr-2 size-4" /> {t(T.importerFichiers)}
                        </DropdownMenuItem>
                    )}
                    <DropdownMenuItem onClick={copierId} disabled={!workflowUuid}>
                        <Clipboard className="mr-2 size-4" /> {t(T.copierId)}
                    </DropdownMenuItem>
                </DropdownMenuContent>
            </DropdownMenu>

            {fenetre === "publier" && (
                <FenetreDePublication
                    agentId={agentId}
                    version={versionNumero}
                    branche={branches.courante && !branches.courante.principale ? branches.courante.nom : null}
                    fermer={() => setFenetre(null)}
                    onPublie={() => void apresPublication()}
                />
            )}
            <FenetreNouvelleBranche
                agentId={agentId}
                ouverte={fenetre === "branche"}
                fermer={() => setFenetre(null)}
                vue={branches.vue}
                cree={(brancheId) => ouvrirEtRelire(brancheId)}
            />
            {fenetre === "versions" && branches.vue && (
                <FenetreVersions
                    ouverte
                    fermer={() => setFenetre(null)}
                    vue={branches.vue}
                    ouverteId={branches.ouverte}
                    ouvrir={ouvrirEtRelire}
                    repartition={() => setFenetre("repartition")}
                    agentId={agentId}
                    fusionner={(brancheId) => {
                        setFusion({ sens: "fusion", brancheId });
                        setFenetre("fusion");
                    }}
                    mettreAJour={(brancheId) => {
                        setFusion({ sens: "maj", brancheId });
                        setFenetre("fusion");
                    }}
                    apres={() => void branches.recharger()}
                />
            )}
            {fenetre === "fusion" && fusion && (
                <FenetreFusion
                    agentId={agentId}
                    brancheId={fusion.brancheId}
                    sens={fusion.sens}
                    ouverte
                    fermer={() => setFenetre("versions")}
                    apres={(ecrit) => {
                        // Une mise à jour change le brouillon de la branche ouverte, une fusion archive la branche : l'écran se relit.
                        if (ecrit === "maj" && branches.ouverte === fusion.brancheId) return window.location.reload();
                        if (ecrit === "fusion" && branches.ouverte === fusion.brancheId) return ouvrirEtRelire(null);
                        void branches.recharger();
                        void lire();
                    }}
                />
            )}
            {fenetre === "repartition" && branches.vue && (
                <FenetreRepartition
                    agentId={agentId}
                    ouverte
                    fermer={() => setFenetre(null)}
                    vue={branches.vue}
                    apres={() => void branches.recharger()}
                />
            )}
            {(fenetre === "exporter" || fenetre === "ramener") && (
                <FenetreCopieAgent agentId={agentId} nom={nom} sens={fenetre} fermer={() => setFenetre(null)} />
            )}
            {fenetre === "fichiers-export" && <FenetreExportFichiers agentId={agentId} nom={nom} fermer={() => setFenetre(null)} />}
            {fenetre === "fichiers-import" && <FenetreImportFichiers agentId={agentId} fermer={() => setFenetre(null)} apres={() => void lire()} />}
            <FenetreEtiquettes agentId={agentId} ouvert={fenetre === "etiquettes"} onOuvertChange={(o) => setFenetre(o ? "etiquettes" : null)} />
            <FenetreChamps
                ouverte={fenetre === "dupliquer"}
                fermer={() => setFenetre(null)}
                valider={t(T.dupliquer)}
                titre={t(T.titreDuplication)}
                info={t(T.infoDuplication)}
                sections={[
                    {
                        champs: [
                            { id: "nom", t: "texte", l: t(T.nomCopie), v: `${nom} ${t(T.copie)}` },
                            { id: "tests", t: "inter", l: t(T.avecTests), v: true },
                        ],
                    },
                ]}
                onValider={(valeurs) => dupliquer(String(valeurs.nom ?? ""), valeurs.tests === true)}
            />
            <FenetreChamps
                ouverte={fenetre === "renommer"}
                fermer={() => setFenetre(null)}
                valider={t(T.renommer)}
                titre={t(T.titreRenommer)}
                sections={[{ champs: [{ id: "nom", t: "texte", l: t(T.nomAgent), v: nom }] }]}
                onValider={(valeurs) => {
                    const propre = String(valeurs.nom ?? "").trim();
                    if (!propre || propre === nom || !editeur) return;
                    return editeur
                        .renommer(propre)
                        .then(() => true)
                        .catch(() => {
                            notifier.echec({ fr: "Renommage impossible. Réessayez.", en: "Could not rename. Try again." });
                            return false;
                        });
                }}
            />
        </>
    );
}
