"use client";

/**
 * [.mark] builder-agent-vocal (lot 4, B5): the « Builder IA » side panel of the editor.
 *
 * The conversation is drawn by assistant-ui (MIT, `@assistant-ui/react`, pinned): it owns the thread, the composer
 * and the message parts; this file gives it the builder's cards (Deposit, Client sheet, Design document, Knowledge
 * base, Changes, Prompt check, Tools, Tests, Report, Proposal) as the UI of each action (« tool UI »), and a line of
 * the checklist (« Tasks ») for every other action. Nothing here talks to a model provider: the route is the
 * builder's own (`/builder/conversation`), the brain lives on the server.
 *
 * Writing zone: `@` quotes a node of the graph, `+` deposits a file (opens the Deposit card) or inserts a recipe
 * word, `/` lists the commands.
 */
import {
    AssistantRuntimeProvider,
    ComposerPrimitive,
    MessagePrimitive,
    ThreadPrimitive,
    useAui,
    useAuiState,
    useLocalRuntime,
} from "@assistant-ui/react";
import { AtSign, Maximize2, Minimize2, Phone, Plus, Send, Settings, Slash, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { lireLeCerveauApiV1BuilderCerveauGet } from "@/client";
import type { FlowNode } from "@/components/flow/types";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

import { creerLAdaptateur, lireLHistorique } from "./adaptateur";
import { CarteBase } from "./cartes/CarteBase";
import { CarteChangements } from "./cartes/CarteChangements";
import { CarteConception } from "./cartes/CarteConception";
import { CarteDepot } from "./cartes/CarteDepot";
import { CarteFiche } from "./cartes/CarteFiche";
import { CarteResultat, LigneDeTache, TITRES_DES_CARTES } from "./cartes/CarteResultat";
import { type ContexteDuPanneau, FournisseurDuPanneau, useContexteDuPanneau } from "./contexte-du-panneau";
import { ReglagesDuBuilder } from "./ReglagesDuBuilder";
import { useRevueDesChangements } from "./revue";
import { useBuilderEcran } from "./store";

const T = {
    titre: { en: "Builder AI", fr: "Builder IA" },
    reglages: { en: "Builder settings", fr: "Réglages du builder" },
    appeler: { en: "Call the agent", fr: "Appeler l'agent" },
    clavier: { en: "Try by keyboard", fr: "Essayer au clavier" },
    agrandir: { en: "Full screen", fr: "Plein écran" },
    reduire: { en: "Reduce", fr: "Réduire" },
    fermer: { en: "Close the panel", fr: "Fermer le panneau" },
    vide: {
        en: "Describe the agent to build, or deposit the audit documents. Type / for the commands.",
        fr: "Décrivez l'agent à construire, ou déposez les dossiers d'audit. Tapez / pour les commandes.",
    },
    ecrire: { en: "Write to the builder...", fr: "Écrire au builder..." },
    envoyer: { en: "Send", fr: "Envoyer" },
    citer: { en: "Quote a node (@)", fr: "Citer un nœud (@)" },
    plus: { en: "Deposit or insert (+)", fr: "Déposer ou insérer (+)" },
    commandes: { en: "Commands (/)", fr: "Commandes (/)" },
    deposer: { en: "Deposit a file or a site", fr: "Déposer un fichier ou un site" },
    recette: { en: "Insert a recipe from the library", fr: "Insérer une recette de la bibliothèque" },
    aucunNoeud: { en: "No node yet", fr: "Aucun nœud pour l'instant" },
    modele: { en: "Brain", fr: "Cerveau" },
    sansCerveau: { en: "No brain set: open the settings.", fr: "Aucun cerveau réglé : ouvrez les réglages." },
    brouillon: { en: "unpublished change(s)", fr: "changement(s) non publié(s)" },
    voir: { en: "See", fr: "Voir" },
    jeter: { en: "Discard", fr: "Jeter" },
    publier: { en: "Publish", fr: "Publier" },
    publierRaison: { en: "Only a person publishes, from the top bar.", fr: "Seule une personne publie, depuis la barre du haut." },
    echec: { en: "The builder could not be reached.", fr: "Le builder n'a pas pu être joint." },
    enCours: { en: "The builder is working...", fr: "Le builder travaille..." },
} satisfies Record<string, Texte>;

/** `/` commands: each one writes a request the builder understands (the words stay editable before sending). */
const COMMANDES: { nom: string; texte: Texte }[] = [
    { nom: "/creer", texte: { en: "Build the agent from the validated sheet and the approved design document.", fr: "Construis l'agent depuis la fiche validée et le document de conception approuvé." } },
    { nom: "/tester", texte: { en: "Check the prompts and try the tools, then replay the tests.", fr: "Contrôle les prompts, essaie les outils, puis rejoue les tests." } },
    { nom: "/corriger", texte: { en: "Correct the draft from the failed tests.", fr: "Corrige le brouillon d'après les tests en échec." } },
    { nom: "/rapport", texte: { en: "Give me the report: proven, assumed, not testable, worst defect.", fr: "Donne-moi le rapport : prouvé, supposé, non testable, pire défaut." } },
    { nom: "/annuler", texte: { en: "Drop the pending operations.", fr: "Abandonne les opérations en attente." } },
];

// --- cards, as assistant-ui's « tool UI » ----------------------------------------------------------------------------

type PartieOutil = { toolCallId: string; toolName: string; result?: unknown; isError?: boolean };

/** Only the LAST call of a group draws the card (the card shows the live state, repeating it would only add noise). */
function useEstLaDerniere(toolCallId: string, groupe: string[]): boolean {
    const contenu = useAuiState((s) => s.message.content) as readonly { type: string; toolCallId?: string; toolName?: string }[];
    const memes = contenu.filter((p) => p.type === "tool-call" && p.toolName && groupe.includes(p.toolName));
    return memes[memes.length - 1]?.toolCallId === toolCallId;
}

const GROUPE_DEPOT = ["fiche_tirer_des_documents", "depot_ajouter_site"];
const GROUPE_FICHE = ["fiche_ecrire", "fiche_lire", "fiche_creer_les_objets"];
const GROUPE_CONCEPTION = ["conception_ecrire", "conception_lire"];
const GROUPE_BASE = ["base_proposer", "base_lister", "base_rattacher"];
const GROUPE_CHANGEMENTS = ["brouillon_operation"];

function carteVivante(groupe: string[], Carte: React.ComponentType<{ workflowId: number }>) {
    return function CarteDeLOutil({ toolCallId }: PartieOutil) {
        const { workflowId } = useContexteDuPanneau();
        return useEstLaDerniere(toolCallId, groupe) ? <Carte workflowId={workflowId} /> : null;
    };
}

function CarteDesChangements({ toolCallId }: PartieOutil) {
    return useEstLaDerniere(toolCallId, GROUPE_CHANGEMENTS) ? <CarteChangements /> : null;
}

function CarteDUnResultat({ toolName, result, isError }: PartieOutil) {
    return <CarteResultat nomDeLAction={toolName} resultat={result} erreur={isError} />;
}

function Tache({ toolName, result, isError }: PartieOutil) {
    return <LigneDeTache nom={toolName} termine={result !== undefined} erreur={Boolean(isError)} />;
}

const OUTILS = {
    by_name: {
        ...Object.fromEntries(GROUPE_DEPOT.map((n) => [n, carteVivante(GROUPE_DEPOT, CarteDepot)])),
        ...Object.fromEntries(GROUPE_FICHE.map((n) => [n, carteVivante(GROUPE_FICHE, CarteFiche)])),
        ...Object.fromEntries(GROUPE_CONCEPTION.map((n) => [n, carteVivante(GROUPE_CONCEPTION, CarteConception)])),
        ...Object.fromEntries(GROUPE_BASE.map((n) => [n, carteVivante(GROUPE_BASE, CarteBase)])),
        brouillon_operation: CarteDesChangements,
        ...Object.fromEntries(Object.keys(TITRES_DES_CARTES).map((n) => [n, CarteDUnResultat])),
    },
    Fallback: Tache,
} as never;

function TexteDuMessage({ text }: { text: string }) {
    return <p className="whitespace-pre-wrap break-words text-sm">{text}</p>;
}

function MessageDeLaPersonne() {
    return (
        <MessagePrimitive.Root className="my-2 flex justify-end">
            <div className="max-w-[85%] rounded-lg bg-primary px-3 py-2 text-primary-foreground" data-role="user">
                <MessagePrimitive.Parts components={{ Text: TexteDuMessage }} />
            </div>
        </MessagePrimitive.Root>
    );
}

function MessageDuBuilder() {
    return (
        <MessagePrimitive.Root className="my-2">
            <div className="max-w-full" data-role="assistant">
                <MessagePrimitive.Parts components={{ Text: TexteDuMessage, tools: OUTILS }} />
            </div>
        </MessagePrimitive.Root>
    );
}

// --- the writing zone ------------------------------------------------------------------------------------------------

function ZoneDEcriture({ noeuds }: { noeuds: FlowNode[] }) {
    const { t } = useLangue();
    const aui = useAui();
    const citation = useBuilderEcran((s) => s.citation);
    const citer = useBuilderEcran((s) => s.citer);
    const enCours = useBuilderEcran((s) => s.enCours);
    const texte = useAuiState((s) => s.composer.text);

    // A node asked about from the canvas (« Ask the builder ») lands in the writing zone as a quote.
    useEffect(() => {
        if (!citation) return;
        aui.composer().setText(`${texte}${texte && !texte.endsWith(" ") ? " " : ""}@${citation.nom} `);
        citer(null);
    }, [citation, aui, citer, texte]);

    const inserer = (mot: string) => aui.composer().setText(`${texte}${texte && !texte.endsWith(" ") ? " " : ""}${mot}`);

    return (
        <ComposerPrimitive.Root className="border-t p-2" data-zone="ecriture">
            {enCours && <p className="mb-1 text-xs text-muted-foreground">{t(T.enCours)}</p>}
            <ComposerPrimitive.Input
                placeholder={t(T.ecrire)}
                aria-label={t(T.ecrire)}
                rows={2}
                className="w-full resize-none rounded-md border bg-background p-2 text-sm"
            />
            <div className="mt-1 flex items-center gap-1">
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.citer)} title={t(T.citer)}>
                            <AtSign className="h-4 w-4" aria-hidden />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start" className="max-h-64 overflow-y-auto">
                        {noeuds.length === 0 && <DropdownMenuItem disabled>{t(T.aucunNoeud)}</DropdownMenuItem>}
                        {noeuds.map((n) => (
                            <DropdownMenuItem key={n.id} onClick={() => inserer(`@${(n.data as { name?: string }).name ?? n.id} `)}>
                                {(n.data as { name?: string }).name ?? n.id}
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.plus)} title={t(T.plus)}>
                            <Plus className="h-4 w-4" aria-hidden />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                        <DropdownMenuItem onClick={() => useBuilderEcran.getState().montrerLeDepot(true)}>
                            {t(T.deposer)}
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => inserer("recette:")}>{t(T.recette)}</DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.commandes)} title={t(T.commandes)}>
                            <Slash className="h-4 w-4" aria-hidden />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="start">
                        {COMMANDES.map((c) => (
                            <DropdownMenuItem key={c.nom} onClick={() => aui.composer().setText(`${c.nom} ${t(c.texte)}`)}>
                                <b className="mr-2">{c.nom}</b>
                                <span className="text-xs text-muted-foreground">{t(c.texte)}</span>
                            </DropdownMenuItem>
                        ))}
                    </DropdownMenuContent>
                </DropdownMenu>
                <ComposerPrimitive.Send asChild>
                    <Button type="button" size="sm" className="ml-auto" disabled={enCours}>
                        <Send className="mr-1 h-4 w-4" aria-hidden />
                        {t(T.envoyer)}
                    </Button>
                </ComposerPrimitive.Send>
            </div>
        </ComposerPrimitive.Root>
    );
}

// --- the thread ------------------------------------------------------------------------------------------------------

function Conversation({ contexte, noeuds, historique }: { contexte: ContexteDuPanneau; noeuds: FlowNode[]; historique: Parameters<typeof useLocalRuntime>[1] }) {
    const { t } = useLangue();
    const adaptateur = useMemo(
        () =>
            creerLAdaptateur({
                workflowId: contexte.workflowId,
                lireLeGraphe: contexte.lireLeGraphe,
                recharger: contexte.recharger,
                echec: t(T.echec),
            }),
        // The adapter reads the graph through the functions of the context at call time.
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [contexte.workflowId],
    );
    const runtime = useLocalRuntime(adaptateur, historique);
    return (
        <AssistantRuntimeProvider runtime={runtime}>
            <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
                <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                    <ThreadPrimitive.Empty>
                        <p className="py-6 text-center text-sm text-muted-foreground">{t(T.vide)}</p>
                    </ThreadPrimitive.Empty>
                    <ThreadPrimitive.Messages components={{ UserMessage: MessageDeLaPersonne, AssistantMessage: MessageDuBuilder }} />
                </ThreadPrimitive.Viewport>
                <ZoneDEcriture noeuds={noeuds} />
            </ThreadPrimitive.Root>
        </AssistantRuntimeProvider>
    );
}

function BandeauBrouillon() {
    const { t } = useLangue();
    const revue = useRevueDesChangements();
    if (!revue.resume) return null;
    return (
        <div className="flex flex-wrap items-center gap-2 border-b bg-(--signal-warn)/10 px-3 py-2 text-xs" data-bandeau="brouillon">
            <span>
                <b>{revue.resume.total}</b> {t(T.brouillon)}
            </span>
            <Button type="button" size="sm" variant="outline" disabled={!revue.peutVoir} onClick={() => void revue.voir()}>
                {t(T.voir)}
            </Button>
            <Button type="button" size="sm" variant="outline" disabled={revue.enAttente || revue.occupe} onClick={() => void revue.refuser()}>
                {t(T.jeter)}
            </Button>
            <Button type="button" size="sm" disabled title={t(T.publierRaison)}>
                {t(T.publier)}
            </Button>
            {revue.dialogue}
        </div>
    );
}

export function PanneauBuilder({ contexte, noeuds }: { contexte: ContexteDuPanneau; noeuds: FlowNode[] }) {
    const { t } = useLangue();
    const pleinEcran = useBuilderEcran((s) => s.pleinEcran);
    const definirPleinEcran = useBuilderEcran((s) => s.definirPleinEcran);
    const fermer = useBuilderEcran((s) => s.fermer);
    const reglagesOuverts = useBuilderEcran((s) => s.reglagesOuverts);
    const depotVisible = useBuilderEcran((s) => s.depotVisible);
    const ouvrirLesReglages = useBuilderEcran((s) => s.ouvrirLesReglages);
    const rafraichir = useBuilderEcran((s) => s.rafraichirLeContexte);
    const [historique, setHistorique] = useState<Parameters<typeof useLocalRuntime>[1] | null>(null);
    const [modele, setModele] = useState<string | null>(null);

    useEffect(() => {
        let annule = false;
        void (async () => {
            const [messages] = await Promise.all([lireLHistorique(contexte.workflowId), rafraichir(contexte.workflowId)]);
            if (!annule) setHistorique({ initialMessages: messages });
        })();
        return () => {
            annule = true;
        };
    }, [contexte.workflowId, rafraichir]);

    useEffect(() => {
        if (reglagesOuverts) return;
        void (async () => {
            const reponse = await lireLeCerveauApiV1BuilderCerveauGet();
            setModele(reponse.data?.modele && reponse.data.cle_posee ? reponse.data.modele : "");
        })();
    }, [reglagesOuverts]);

    return (
        <FournisseurDuPanneau value={contexte}>
            <aside
                className={`flex h-full min-h-0 flex-col border-l bg-background ${pleinEcran ? "fixed inset-0 z-40 w-full" : "w-[420px] shrink-0"}`}
                aria-label={t(T.titre)}
                data-panneau="builder-ia"
            >
                <header className="flex items-center gap-1 border-b px-3 py-2">
                    <h2 className="whitespace-nowrap text-sm font-semibold">{t(T.titre)}</h2>
                    <span className="ml-2 truncate text-xs text-muted-foreground" data-cerveau>
                        {modele === null ? "" : modele ? `${t(T.modele)} : ${modele}` : t(T.sansCerveau)}
                    </span>
                    <div className="ml-auto flex items-center">
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.appeler)} title={t(T.appeler)} onClick={contexte.appelerLAgent}>
                            <Phone className="h-4 w-4" aria-hidden />
                        </Button>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.reglages)} title={t(T.reglages)} onClick={() => ouvrirLesReglages(true)}>
                            <Settings className="h-4 w-4" aria-hidden />
                        </Button>
                        <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            aria-label={pleinEcran ? t(T.reduire) : t(T.agrandir)}
                            title={pleinEcran ? t(T.reduire) : t(T.agrandir)}
                            onClick={() => definirPleinEcran(!pleinEcran)}
                        >
                            {pleinEcran ? <Minimize2 className="h-4 w-4" aria-hidden /> : <Maximize2 className="h-4 w-4" aria-hidden />}
                        </Button>
                        <Button type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(T.fermer)} title={t(T.fermer)} onClick={fermer}>
                            <X className="h-4 w-4" aria-hidden />
                        </Button>
                    </div>
                </header>
                <BandeauBrouillon />
                <div className="border-b px-3 py-1">
                    <button type="button" className="text-xs underline" onClick={contexte.essayerAuClavier}>
                        {t(T.clavier)}
                    </button>
                </div>
                {depotVisible && (
                    <div className="max-h-72 overflow-y-auto border-b px-3" data-depot-epingle>
                        <CarteDepot workflowId={contexte.workflowId} />
                    </div>
                )}
                {historique ? <Conversation contexte={contexte} noeuds={noeuds} historique={historique} /> : <div className="flex-1" />}
                <ReglagesDuBuilder ouvert={reglagesOuverts} onOuvertChange={ouvrirLesReglages} />
            </aside>
        </FournisseurDuPanneau>
    );
}
