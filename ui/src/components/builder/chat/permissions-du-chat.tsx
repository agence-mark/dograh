"use client";

/**
 * [.mark] Partie 3, N1 (SA-N1a) : les permissions du builder dans le chat (05, « Les permissions du builder » ; décision 12, mode Plan).
 * Repris de la maquette (`components/studio/permissions-builder.tsx`) : le sélecteur de mode dans la barre de saisie, le bandeau discret
 * hors « Demander », la fenêtre centrée qui confirme « Tout permettre », la carte de demande dans le fil (une fois, pour ce chat, refuser).
 *
 * L'écran ne décide rien : le mode et chaque autorisation sont vérifiés CÔTÉ SERVEUR à chaque action (`api/services/builder/modes.py`),
 * bornés par le rôle de la personne. Rien n'est exécuté sans clic ; une autorisation « pour ce chat » ne vit que dans ce chat.
 */
import { Check, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info, Marque } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

import type { CarteDuFil } from "./evenements";

export type ModeDuChat = "demander" | "agent" | "tout" | "plan";
export const MODES: ModeDuChat[] = ["demander", "agent", "tout", "plan"];
export type Decision = "une_fois" | "pour_ce_chat" | "refuser";
export type AutorisationDuChat = { id: string; nom?: string | null; famille?: string | null; objet?: string | null };

export const NOM_MODE: Record<ModeDuChat, { court: Texte; long: Texte; sous: Texte; info: Texte }> = {
    demander: {
        court: { en: "Ask", fr: "Demander" },
        long: { en: "Ask", fr: "Demander" },
        sous: { en: "It edits the open agent's draft; the rest waits for your agreement.", fr: "Il modifie le brouillon de l'agent ouvert ; le reste attend ton accord." },
        info: {
            en: "Default of every new chat. Without asking: read, and edit the open agent's draft (reversible, nothing is published). Everything else asks, one card at a time.",
            fr: "Défaut de chaque nouveau chat. Ce qui passe sans demander : lire, et modifier le brouillon de l'agent ouvert (réversible, rien n'est publié). Tout le reste demande, une carte à la fois.",
        },
    },
    agent: {
        court: { en: "This agent", fr: "Cet agent" },
        long: { en: "Allow everything on this agent", fr: "Tout permettre sur cet agent" },
        sous: { en: "Everything on this agent and its group, publishing included.", fr: "Tout ce qui touche cet agent et son groupe, publication comprise." },
        info: {
            en: "Draft, settings, the agent's tools, tests, publishing (if the blocking checks pass). Still asks: the company or another agent, what costs money, what calls real people, deleting.",
            fr: "Brouillon, réglages, outils de l'agent, tests, publication (si les contrôles bloquants passent). Demande encore : l'entreprise ou un autre agent, ce qui dépense, ce qui appelle de vrais gens, supprimer.",
        },
    },
    tout: {
        court: { en: "Everything", fr: "Tout" },
        long: { en: "Allow everything", fr: "Tout permettre" },
        sous: { en: "Also the company, the other agents, campaigns and telephony.", fr: "Aussi l'entreprise, les autres agents, les campagnes et la téléphonie." },
        info: {
            en: "Everything, within your role. Three guards hold in every mode: keys stay typed by a person, the monthly spending ceiling, the journal.",
            fr: "Tout, dans les limites de ton rôle. Trois gardes tiennent dans tous les modes : les clés restent à saisir par une personne, le plafond de dépense du mois, le journal.",
        },
    },
    plan: {
        court: { en: "Plan", fr: "Plan" },
        long: { en: "Plan", fr: "Plan" },
        sous: { en: "It searches and writes a plan; nothing changes before your agreement.", fr: "Il cherche et rédige un plan ; rien n'est modifié avant ton accord." },
        info: {
            en: "Read only: the builder reads, then writes its plan as steps. Approve the plan to go back to « Ask » and let it carry the plan out.",
            fr: "Lecture seule : le builder lit, puis rédige son plan en étapes. Approuver le plan revient à « Demander » et le laisse l'exécuter.",
        },
    },
};

const FAMILLES: Record<string, Texte> = {
    lecture: { en: "Reading", fr: "Lecture" },
    brouillon: { en: "Draft", fr: "Brouillon" },
    reglages: { en: "Agent settings", fr: "Réglages de l'agent" },
    publication: { en: "Publishing", fr: "Publication" },
    entreprise: { en: "Company", fr: "Entreprise" },
    autre_agent: { en: "Other agent or group", fr: "Autre agent ou groupe" },
    depense: { en: "Spending", fr: "Dépense" },
    appels_reels: { en: "Real calls", fr: "Appels réels" },
    irreversible: { en: "Irreversible", fr: "Irréversible" },
};

// Le titre des gestes de personne entrés au registre (N1) ; les autres actions gardent leur nom de code.
const ACTIONS: Record<string, Texte> = {
    agent_publier: { en: "Publish the agent", fr: "Publier l'agent" },
    groupe_publier: { en: "Publish the group", fr: "Publier le groupe" },
    branche_publier: { en: "Publish a branch", fr: "Publier une branche" },
    branche_fusionner: { en: "Merge a branch", fr: "Fusionner une branche" },
    repartition_regler: { en: "Set the traffic split", fr: "Régler la répartition du trafic" },
    agent_archiver: { en: "Archive the agent", fr: "Archiver l'agent" },
    outil_supprimer: { en: "Delete a tool", fr: "Supprimer un outil" },
    bibliotheque_marquer: { en: "Change a library status", fr: "Changer le statut d'un élément de la bibliothèque" },
    bibliotheque_accepter_proposition: { en: "Accept a library proposal", fr: "Accepter une proposition de la bibliothèque" },
    bibliotheque_refuser_proposition: { en: "Refuse a library proposal", fr: "Refuser une proposition de la bibliothèque" },
    bibliotheque_retour_arriere: { en: "Go back to an earlier library version", fr: "Revenir à une version de la bibliothèque" },
    reglages_regler: { en: "Change the agent's settings", fr: "Changer les réglages de l'agent" },
    tests_rejouer: { en: "Replay the tests", fr: "Rejouer les tests" },
    attaques_lancer: { en: "Launch the attacks", fr: "Lancer les attaques" },
};

const T = {
    titreSelecteur: { en: "What the builder may do without asking", fr: "Ce que le builder peut faire sans demander" },
    infoSelecteur: {
        en: "The mode applies to this chat and goes back to « Ask » in a new chat. The builder never has more rights than the person using it.",
        fr: "Le mode vaut pour ce chat et revient à « Demander » dans un nouveau chat. Le builder ne donne jamais plus de droits que la personne qui l'utilise.",
    },
    defaut: { en: "default", fr: "défaut" },
    permissions: { en: "Builder permissions", fr: "Permissions du builder" },
    pourCeChat: { en: "Allowed for this chat", fr: "Autorisé pour ce chat" },
    infoPourCeChat: {
        en: "This type of action, on this object, until the end of the chat. Withdrawing it brings the request back.",
        fr: "Ce type d'action, sur cet objet, jusqu'à la fin du chat. Retirer l'autorisation remet la demande.",
    },
    retirer: { en: "Withdraw the permission", fr: "Retirer l'autorisation" },
    confirmerTitre: { en: "Allow everything in this chat?", fr: "Tout permettre dans ce chat ?" },
    confirmerTexte: {
        en: "The builder will act without asking, for this chat only. The mode goes back to « Ask » in a new chat.",
        fr: "Le builder agira sans demander, pour ce chat seulement. Le mode revient à « Demander » dans un nouveau chat.",
    },
    confirmer1: { en: "It edits and publishes this agent, and touches the other agents.", fr: "Il modifie et publie cet agent, et touche aux autres agents." },
    confirmer2: { en: "It edits the company: sites, team, sentences, announcement, objects.", fr: "Il modifie l'entreprise : établissements, équipe, phrases, annonce, objets." },
    confirmer3: { en: "It can launch real call campaigns and what costs money.", fr: "Il peut lancer des campagnes d'appels réels et ce qui dépense." },
    confirmerGardes: {
        en: "Keys stay invisible to it, the monthly spending ceiling holds, every action is written in the journal.",
        fr: "Les clés restent invisibles pour lui, le plafond de dépense du mois tient, chaque action est journalisée.",
    },
    annuler: { en: "Cancel", fr: "Annuler" },
    confirmer: { en: "Confirm", fr: "Confirmer" },
    bandeauAgent: { en: "the builder acts without asking on this agent.", fr: "le builder agit sans demander sur cet agent." },
    bandeauTout: { en: "the builder acts without asking, company included.", fr: "le builder agit sans demander, entreprise comprise." },
    bandeauPlan: { en: "the builder reads and writes a plan; nothing is changed.", fr: "le builder lit et rédige un plan ; rien n'est modifié." },
    revenir: { en: "Back to « Ask »", fr: "Revenir à « Demander »" },
    approuver: { en: "Approve the plan", fr: "Approuver le plan" },
    demande: { en: "Request", fr: "Demande" },
    definitif: { en: "Final", fr: "Définitif" },
    definitifInfo: { en: "This cannot be undone by the builder: a person restores it by hand.", fr: "Le builder ne peut pas le défaire : une personne le restaure à la main." },
    apres: { en: "After", fr: "Après" },
    cout: { en: "Cost", fr: "Coût" },
    coutTexte: { en: "This action runs paid models (the monthly ceiling still holds).", fr: "Cette action fait tourner des modèles payants (le plafond du mois tient toujours)." },
    une: { en: "Allow once", fr: "Autoriser une fois" },
    chat: { en: "Allow for this chat", fr: "Autoriser pour ce chat" },
    chatInfo: {
        en: "« For this chat »: this type of action, on this object, without asking again until the end of the chat. It can be withdrawn in the permissions selector.",
        fr: "« Pour ce chat » : ce type d'action, sur cet objet, sans redemander jusqu'à la fin du chat. Elle se retire dans le sélecteur de permissions.",
    },
    refuser: { en: "Refuse", fr: "Refuser" },
    raison: { en: "Reason (optional), the builder reads it", fr: "Raison (facultative), le builder la lit" },
    raisonLibelle: { en: "Reason for refusing", fr: "Raison du refus" },
    retour: { en: "Back", fr: "Retour" },
    confirmerRefus: { en: "Confirm the refusal", fr: "Confirmer le refus" },
    autoriseeUne: { en: "allowed once", fr: "autorisé une fois" },
    autoriseeChat: { en: "allowed for this chat", fr: "autorisé pour ce chat" },
    refusee: { en: "refused", fr: "refusé" },
    retiree: { en: "permission withdrawn", fr: "autorisation retirée" },
    agent: { en: "Agent", fr: "Agent" },
    cetAgent: { en: "This agent", fr: "Cet agent" },
    organisation: { en: "The organisation", fr: "L'organisation" },
} satisfies Record<string, Texte>;

export const libelleFamille = (famille: unknown): Texte => FAMILLES[String(famille)] ?? { en: String(famille), fr: String(famille) };
export const libelleAction = (nom: unknown): Texte => ACTIONS[String(nom)] ?? { en: String(nom), fr: String(nom) };

/** L'objet d'une autorisation, lisible : « Cet agent », « Agent 77 », l'outil, l'élément de bibliothèque. */
export function libelleObjet(objet: unknown, agentOuvert: number | null | undefined): Texte {
    const brut = String(objet ?? "");
    if (brut === "organisation") return T.organisation;
    const [genre, valeur] = [brut.slice(0, brut.indexOf(":")), brut.slice(brut.indexOf(":") + 1)];
    if (genre === "agent") return agentOuvert != null && valeur === String(agentOuvert) ? T.cetAgent : { en: `${T.agent.en} ${valeur}`, fr: `${T.agent.fr} ${valeur}` };
    return { en: valeur || brut, fr: valeur || brut };
}

/** Dans la barre de saisie, à côté des pièces jointes et des sous-agents. « Tout permettre » demande une confirmation centrée. */
export function SelecteurMode({
    mode,
    choisir,
    autorisations,
    retirer,
    agentOuvert,
    desactive = false,
}: {
    mode: ModeDuChat;
    choisir: (m: ModeDuChat) => void;
    autorisations: AutorisationDuChat[];
    retirer: (id: string) => void;
    agentOuvert?: number | null;
    desactive?: boolean;
}) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    const [confirme, setConfirme] = useState(false);
    const ligne = (actif: boolean) => `flex w-full cursor-pointer items-start gap-2.5 rounded-md px-2 py-1.5 text-left text-sm ${actif ? "bg-muted" : "hover:bg-muted/60"}`;
    return (
        <>
            <Popover open={ouvert} onOpenChange={setOuvert}>
                <PopoverTrigger asChild>
                    <Button
                        variant="ghost"
                        size="sm"
                        disabled={desactive}
                        className={`h-7 cursor-pointer gap-1.5 px-2 ${mode !== "demander" ? "bg-muted" : ""}`}
                        aria-label={`${t(T.permissions)} : ${t(NOM_MODE[mode].long)}`}
                        data-selecteur-mode={mode}
                    >
                        <ShieldCheck className="size-3.5" />
                        <span className="text-xs">{t(NOM_MODE[mode].court)}</span>
                    </Button>
                </PopoverTrigger>
                <PopoverContent side="top" align="end" className="w-96 p-1.5">
                    <p className="flex items-center gap-1.5 px-2 pt-1 pb-1.5 text-xs font-medium text-muted-foreground">
                        {t(T.titreSelecteur)}
                        <Info>{t(T.infoSelecteur)}</Info>
                    </p>
                    {MODES.map((m) => (
                        <button
                            key={m}
                            type="button"
                            data-mode={m}
                            onClick={() => {
                                setOuvert(false);
                                if (m === "tout" && mode !== "tout") setConfirme(true);
                                else if (m !== mode) choisir(m);
                            }}
                            className={ligne(mode === m)}
                        >
                            <span className="mt-0.5 flex size-4 shrink-0 items-center justify-center">{mode === m && <Check className="size-4" strokeWidth={2.5} />}</span>
                            <span className="flex-1">
                                <span className="flex items-center gap-1.5 font-medium">
                                    {t(NOM_MODE[m].long)}
                                    {m === "demander" && <span className="text-[11px] font-normal text-muted-foreground">{t(T.defaut)}</span>}
                                    <Info>{t(NOM_MODE[m].info)}</Info>
                                </span>
                                <span className="block text-xs text-muted-foreground">{t(NOM_MODE[m].sous)}</span>
                            </span>
                        </button>
                    ))}
                    {autorisations.length > 0 && (
                        <div className="mt-1 border-t px-2 pt-2 pb-1">
                            <p className="flex items-center gap-1.5 pb-1 text-xs font-medium text-muted-foreground">
                                {t(T.pourCeChat)}
                                <Info>{t(T.infoPourCeChat)}</Info>
                            </p>
                            {autorisations.map((a) => (
                                <div key={a.id} className="flex items-center gap-2 py-1 text-sm" data-autorisation-du-chat={a.id}>
                                    <span className="flex-1 truncate">
                                        {t(libelleAction(a.nom))} · {t(libelleObjet(a.objet, agentOuvert))}
                                    </span>
                                    <button
                                        type="button"
                                        aria-label={t(T.retirer)}
                                        title={t(T.retirer)}
                                        onClick={() => retirer(a.id)}
                                        className="cursor-pointer rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                                    >
                                        <X className="size-3.5" />
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </PopoverContent>
            </Popover>
            <Dialog centree open={confirme} onOpenChange={setConfirme}>
                <DialogContent className="sm:max-w-md" data-fenetre-tout-permettre>
                    <DialogHeader>
                        <DialogTitle>{t(T.confirmerTitre)}</DialogTitle>
                        <DialogDescription>{t(T.confirmerTexte)}</DialogDescription>
                    </DialogHeader>
                    <ul className="list-disc space-y-1 pl-5 text-sm">
                        <li>{t(T.confirmer1)}</li>
                        <li>{t(T.confirmer2)}</li>
                        <li>{t(T.confirmer3)}</li>
                    </ul>
                    <p className="text-xs text-muted-foreground">{t(T.confirmerGardes)}</p>
                    <DialogFooter>
                        <Button variant="outline" className="cursor-pointer" onClick={() => setConfirme(false)}>
                            {t(T.annuler)}
                        </Button>
                        <Button
                            autoFocus
                            className="cursor-pointer"
                            data-confirmer-tout
                            onClick={() => {
                                setConfirme(false);
                                choisir("tout");
                            }}
                        >
                            {t(T.confirmer)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}

/** Un bandeau discret quand le mode n'est pas « Demander » (en tête de la saisie, comme la maquette). */
export function BandeauMode({ mode, revenir, approuverLePlan, desactive = false }: { mode: ModeDuChat; revenir: () => void; approuverLePlan: () => void; desactive?: boolean }) {
    const { t } = useLangue();
    if (mode === "demander") return null;
    const phrase = mode === "agent" ? T.bandeauAgent : mode === "tout" ? T.bandeauTout : T.bandeauPlan;
    return (
        <div className="flex items-center gap-2 border-b px-3 py-2 text-xs" data-bandeau-mode={mode}>
            <ShieldCheck className="size-3.5 shrink-0" />
            <span className="flex-1">
                <span className="font-medium">{t(NOM_MODE[mode].long)}</span> : {t(phrase)}
            </span>
            {mode === "plan" && (
                <button type="button" disabled={desactive} onClick={approuverLePlan} className="cursor-pointer font-medium hover:font-semibold disabled:cursor-not-allowed disabled:opacity-50">
                    {t(T.approuver)}
                </button>
            )}
            <button type="button" disabled={desactive} onClick={revenir} className="cursor-pointer font-medium hover:font-semibold disabled:cursor-not-allowed disabled:opacity-50">
                {t(T.revenir)}
            </button>
        </div>
    );
}

function Apres({ carte }: { carte: CarteDuFil }) {
    const { t } = useLangue();
    const apres = (carte.apres as Record<string, unknown>) ?? {};
    // L'agent visé est déjà dit par l'objet de la carte : l'après ne garde que ce qui change.
    const lignes = Object.entries(apres).filter(([cle, v]) => cle !== "workflow_id" && v !== null && v !== undefined && v !== "");
    if (!lignes.length && !carte.depense) return null;
    return (
        <div className="grid grid-cols-[3.5rem_1fr] gap-x-3 gap-y-1 text-sm">
            {lignes.length > 0 && (
                <>
                    <span className="text-xs text-muted-foreground">{t(T.apres)}</span>
                    <span className="min-w-0 space-y-0.5">
                        {lignes.map(([cle, v]) => (
                            <span key={cle} className="block break-words">
                                <span className="text-muted-foreground">{cle} : </span>
                                <span className="font-medium">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                            </span>
                        ))}
                    </span>
                </>
            )}
            {Boolean(carte.depense) && (
                <>
                    <span className="text-xs text-muted-foreground">{t(T.cout)}</span>
                    <span>{t(T.coutTexte)}</span>
                </>
            )}
        </div>
    );
}

/** La carte d'une demande dans le fil : ce qu'il veut faire, sur quoi, l'après, le coût ; trois boutons ; « Définitif » sur l'irréversible. */
export function CarteAutorisation({
    carte,
    active,
    repondre,
    agentOuvert,
}: {
    carte: CarteDuFil;
    active: boolean;
    repondre: (decision: Decision, raison?: string) => void;
    agentOuvert?: number | null;
}) {
    const { t } = useLangue();
    const [refus, setRefus] = useState(false);
    const [raison, setRaison] = useState("");
    const statut = String(carte.statut ?? "attente");
    const titre = (
        <div>
            <p className="font-medium">{t(libelleAction(carte.action))}</p>
            <p className="text-xs text-muted-foreground">{t(libelleObjet(carte.objet, agentOuvert))}</p>
        </div>
    );
    if (statut !== "attente") {
        const etat = statut === "une_fois" ? T.autoriseeUne : statut === "pour_ce_chat" ? T.autoriseeChat : statut === "retiree" ? T.retiree : T.refusee;
        const ok = statut === "une_fois" || statut === "pour_ce_chat";
        return (
            <div className="flex items-center gap-2 rounded-xl border bg-card px-4 py-3 text-sm" data-carte="autorisation" data-statut={statut}>
                {ok ? <Check className="size-4 text-(--point-publie)" strokeWidth={2.5} /> : <X className="size-4 text-muted-foreground" />}
                <span className="flex-1">
                    <span className="font-medium">{t(libelleAction(carte.action))}</span>
                    <span className="text-muted-foreground"> · {t(etat)}</span>
                </span>
                <Marque>{t(libelleFamille(carte.famille))}</Marque>
            </div>
        );
    }
    return (
        <div className="space-y-3 rounded-xl border bg-card p-4" data-carte="autorisation" data-statut="attente">
            <div className="flex flex-wrap items-center gap-2">
                <Marque ton="plein">{t(T.demande)}</Marque>
                <Marque>{t(libelleFamille(carte.famille))}</Marque>
                {Boolean(carte.definitif) && (
                    <span className="inline-flex items-center gap-1.5">
                        <Marque ton="danger">{t(T.definitif)}</Marque>
                        <Info>{t(T.definitifInfo)}</Info>
                    </span>
                )}
            </div>
            {titre}
            <Apres carte={carte} />
            {!refus ? (
                <div className="flex flex-wrap items-center gap-2">
                    <Button size="sm" className="cursor-pointer" disabled={!active} onClick={() => repondre("une_fois")}>
                        {t(T.une)}
                    </Button>
                    <Button size="sm" variant="outline" className="cursor-pointer" disabled={!active} onClick={() => repondre("pour_ce_chat")}>
                        {t(T.chat)}
                    </Button>
                    <Info>{t(T.chatInfo)}</Info>
                    <Button size="sm" variant="ghost" className="ml-auto cursor-pointer" disabled={!active} onClick={() => setRefus(true)}>
                        {t(T.refuser)}
                    </Button>
                </div>
            ) : (
                <div className="space-y-2">
                    <Input
                        value={raison}
                        maxLength={500}
                        onChange={(e) => setRaison(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter") repondre("refuser", raison.trim() || undefined);
                            if (e.key === "Escape") setRefus(false);
                        }}
                        placeholder={t(T.raison)}
                        className="h-8"
                        aria-label={t(T.raisonLibelle)}
                        autoFocus
                    />
                    <div className="flex gap-2">
                        <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => setRefus(false)}>
                            {t(T.retour)}
                        </Button>
                        <Button size="sm" className="cursor-pointer" disabled={!active} onClick={() => repondre("refuser", raison.trim() || undefined)}>
                            {t(T.confirmerRefus)}
                        </Button>
                    </div>
                </div>
            )}
        </div>
    );
}
