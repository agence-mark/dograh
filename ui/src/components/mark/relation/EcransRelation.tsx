"use client";

import { AlertTriangle, Bot, DoorOpen, Flag, Inbox, Mail, MessageSquare, PhoneCall, Plus, Search, Star, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { notifier } from "@/components/mark/notifications";

import {
    ajouterNoteApiV1RelationClientsOrganizationIdNotesPost,
    ajouterTemoignageApiV1RelationClientsOrganizationIdTemoignagesPost,
    avisEtTemoignagesApiV1RelationAvisGet,
    installationsOuvertesApiV1InstallationsClientOuvertesGet,
    listerEntreesApiV1RelationEntreesGet,
    listerNotesApiV1RelationClientsOrganizationIdNotesGet,
    maFileApiV1RelationFileGet,
    reglerAccordApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdPatch,
    supprimerNoteApiV1RelationClientsOrganizationIdNotesNoteIdDelete,
    supprimerTemoignageApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdDelete,
} from "@/client/sdk.gen";
import type { ClientOut, FilOut } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { useMoi } from "@/components/mark/studio/moi";
import { NouveauClient } from "@/components/mark/studio/selecteur-espace";
import { SuppressionConfirmee } from "@/components/mark/studio/suppression-confirmee";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Liste } from "@/components/mark/studio/liste";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Info, Marque, PointEtat } from "@/components/mark/studio/marques";
import { OngletsPage } from "@/components/mark/studio/onglets-page";
import { Paginee } from "@/components/mark/studio/pagination";
import { Cellule, Ligne, Tableau, TitreTableau } from "@/components/mark/studio/tableau";
import { TitrePage } from "@/components/mark/studio/titre-page";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { EnteteStudio } from "@/components/mark/studio/shell-studio";
import { FlecheRetour } from "@/components/mark/studio/titre-page";
import { RELATION_CLIENTS } from "@/components/mark/studio/nom-espace";

import { BoiteMessages } from "./BoiteMessages";
import { lireClientsRelation } from "./lecture-clients";
import { BoutonPortail } from "./BoutonPortail";
import { AvatarClient, EtatClient, MarqueEtat, Pret, quand, useCharge } from "./commun";

const CONTENEUR = "mx-auto w-full max-w-6xl space-y-6 px-4 py-8 sm:px-8";

// ---------------------------------------------------------------------- Accueil « Ma file » (E94)
export function AccueilRelation() {
    const { t } = useLangue();
    return (
        <Pret>
            <AccueilInterne t={t} />
        </Pret>
    );
}

type Dire = (x: { en: string; fr: string }) => string;
type Tache = { id: string; type: "message" | "demande" | "signalement" | "panne"; titre: string; client: ClientOut; qui: string; quand: string; href: string };
const TYPES_TACHE = {
    message: { icone: Mail, couleur: "var(--acc)", texte: { en: "Message", fr: "Message" }, geste: { en: "Reply", fr: "Répondre" } },
    demande: { icone: Inbox, couleur: "var(--violet-relation)", texte: { en: "Request", fr: "Demande" }, geste: { en: "Handle", fr: "Traiter" } },
    signalement: { icone: Flag, couleur: "var(--pastille-urgente)", texte: { en: "Report", fr: "Signalement" }, geste: { en: "Open", fr: "Ouvrir" } },
    panne: { icone: AlertTriangle, couleur: "var(--pastille-urgente)", texte: { en: "Outage", fr: "Panne" }, geste: { en: "Open", fr: "Ouvrir" } },
} as const;

/** Tout ce qui attend .mark, en une liste : fils à traiter et demandes (la file), signalements et pannes (par client). */
export function tachesDeLaFile(file: FilOut[], clients: ClientOut[], t: Dire): Tache[] {
    const parId = new Map(clients.map((c) => [c.id, c]));
    const taches: Tache[] = [];
    for (const f of file) {
        const client = parId.get(f.organization_id);
        if (!client) continue;
        const demande = f.sorte === "demande_logiciel";
        taches.push({
            id: `f${f.id}`,
            type: demande ? "demande" : "message",
            titre: demande && f.logiciel ? `${f.logiciel} : ${f.sujet}` : f.sujet,
            client,
            qui: f.dernier?.cote === "client" ? f.dernier.auteur : "",
            quand: quand(f.modifie_le),
            href: `/relation/messages?fil=${f.id}`,
        });
    }
    for (const c of clients) {
        const s = c.signalements ?? 0;
        const p = c.pannes ?? 0;
        if (s > 0) {
            taches.push({ id: `s${c.id}`, type: "signalement", titre: t({ en: `${s} report${s !== 1 ? "s" : ""} on a call`, fr: `${s} signalement${s > 1 ? "s" : ""} sur un appel` }), client: c, qui: "", quand: "", href: `/clients/${c.id}/a-ameliorer` });
        }
        if (p > 0) {
            taches.push({ id: `p${c.id}`, type: "panne", titre: t({ en: `${p} outage${p !== 1 ? "s" : ""} or alert${p !== 1 ? "s" : ""}`, fr: `${p} panne${p > 1 ? "s" : ""} ou alerte${p > 1 ? "s" : ""}` }), client: c, qui: "", quand: "", href: `/clients/${c.id}/a-ameliorer` });
        }
    }
    return taches;
}

function LigneTache({ tache, t }: { tache: Tache; t: Dire }) {
    const { icone: Icone, couleur, texte, geste } = TYPES_TACHE[tache.type];
    return (
        <div className="flex items-center gap-4 py-3.5">
            <AvatarClient id={tache.client.id} nom={tache.client.nom} logo />
            <div className="min-w-0 flex-1">
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Icone className="size-3.5" style={{ color: couleur }} />
                    <span className="font-medium" style={{ color: couleur }}>{t(texte)}</span>
                    <span>· {tache.client.nom}{tache.qui ? ` · ${tache.qui}` : ""}</span>
                </p>
                <p className="mt-0.5 truncate text-sm font-medium">{tache.titre}</p>
            </div>
            {tache.quand && <span className="shrink-0 text-xs text-muted-foreground">{tache.quand}</span>}
            <Button variant="outline" size="sm" className="w-24 shrink-0 cursor-pointer" asChild>
                <Link href={tache.href}>{t(geste)}</Link>
            </Button>
        </div>
    );
}

type FiltreAccueil = "tout" | "messages" | "demandes" | "technique";
const FILTRES_ACCUEIL: [FiltreAccueil, { en: string; fr: string }, (x: Tache) => boolean][] = [
    ["tout", { en: "All", fr: "Tout" }, () => true],
    ["messages", { en: "Messages", fr: "Messages" }, (x) => x.type === "message"],
    ["demandes", { en: "Requests", fr: "Demandes" }, (x) => x.type === "demande"],
    ["technique", { en: "Technical", fr: "Technique" }, (x) => x.type === "signalement" || x.type === "panne"],
];

function AccueilInterne({ t }: { t: Dire }) {
    const file = useCharge(() => maFileApiV1RelationFileGet());
    const clients = useCharge(() => lireClientsRelation());
    const moi = useMoi();
    const [nouveau, setNouveau] = useState(false);
    const [filtre, setFiltre] = useState<FiltreAccueil>("tout");
    const pret = file.donnees && clients.donnees;
    const taches = pret ? tachesDeLaFile(file.donnees!, clients.donnees!, t) : [];
    const actif = FILTRES_ACCUEIL.find(([n]) => n === filtre)!;
    const liste = taches.filter(actif[2]);
    const nbClients = new Set(taches.map((x) => x.client.id)).size;
    const erreur = file.etat === "erreur" || clients.etat === "erreur";
    const libelle = ([, nom, f]: (typeof FILTRES_ACCUEIL)[number]) => `${t(nom)} ${taches.filter(f).length}`;
    const bonjour = t({ en: "Hello", fr: "Bonjour" });
    return (
        <div className={CONTENEUR}>
            <div>
                <h2 className="text-2xl font-semibold tracking-tight">{moi?.prenom ? `${bonjour} ${moi.prenom}` : bonjour}</h2>
                {taches.length > 0 && (
                    <p className="mt-1 text-muted-foreground">
                        {t({
                            en: `${taches.length} thing${taches.length !== 1 ? "s are" : " is"} waiting for the team across ${nbClients} client${nbClients !== 1 ? "s" : ""}.`,
                            fr: `${taches.length} chose${taches.length > 1 ? "s attendent" : " attend"} l'équipe chez ${nbClients} client${nbClients > 1 ? "s" : ""}.`,
                        })}
                    </p>
                )}
            </div>
            <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_280px]">
                <div className="space-y-3">
                    <span className="flex h-9 items-center">
                        <Segmente
                            valeur={libelle(actif)}
                            options={FILTRES_ACCUEIL.map(libelle)}
                            changer={(v) => setFiltre(FILTRES_ACCUEIL.find((f) => libelle(f) === v)?.[0] ?? "tout")}
                        />
                    </span>
                    {!pret && !erreur && <EtatVide cas="chargement" />}
                    {erreur && <EtatVide cas="erreur" reessayer={() => { file.recharger(); clients.recharger(); }} />}
                    {pret && liste.length === 0 && (
                        <EtatVide cas="fait" titre={t({ en: "Nothing is waiting for the team", fr: "Rien n'attend l'équipe" })} donnee={`${clients.donnees!.length} client${clients.donnees!.length > 1 ? "s" : ""}`} />
                    )}
                    {pret && liste.length > 0 && (
                        <div className="divide-y border-y">
                            {liste.map((x) => <LigneTache key={x.id} tache={x} t={t} />)}
                        </div>
                    )}
                </div>
                <div className="space-y-3">
                    <p className="flex h-9 items-center text-xs font-medium tracking-wider text-muted-foreground uppercase">{t({ en: "Clients", fr: "Clients" })}</p>
                    {clients.donnees?.length === 0 && (
                        <EtatVide cas="premier" compact icone={Users} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />
                    )}
                    {clients.donnees && clients.donnees.length > 0 && (
                        <div className="divide-y border-y">
                            {clients.donnees.map((c) => {
                                const attente = taches.filter((x) => x.client.id === c.id).length;
                                return (
                                    <Link key={c.id} href={`/relation/clients/${c.id}`} className="flex cursor-pointer items-center gap-3 py-3 hover:font-semibold">
                                        <AvatarClient id={c.id} nom={c.nom} taille={32} logo />
                                        <span className="min-w-0 flex-1">
                                            <span className="block truncate text-sm">{c.nom}</span>
                                            <span className="block text-xs font-normal"><EtatClient etat={c.etat ?? "installation"} /></span>
                                        </span>
                                        {attente > 0 && <span className="text-xs font-normal text-muted-foreground tabular-nums">{t({ en: `${attente} waiting`, fr: `${attente} en attente` })}</span>}
                                    </Link>
                                );
                            })}
                        </div>
                    )}
                    {clients.donnees && clients.donnees.length > 0 && (
                        <Button variant="outline" size="sm" className="w-full cursor-pointer" onClick={() => setNouveau(true)}>
                            {t({ en: "New client", fr: "Nouveau client" })}
                        </Button>
                    )}
                </div>
            </div>
            <NouveauClient ouvert={nouveau} onOuvert={setNouveau} />
        </div>
    );
}

// ---------------------------------------------------------------------- Messages (E92, E93)
export function EcranMessages({ fil }: { fil?: number | null }) {
    return (
        <Pret>
            {/* Pleine zone : la boîte porte son propre titre dans la colonne des fils (E92). */}
            <div className="h-full min-h-[480px]">
                <BoiteMessages filInitial={fil} />
            </div>
        </Pret>
    );
}

// ---------------------------------------------------------------------- Clients et fiche d'un client
export function EcranClients() {
    const { t } = useLangue();
    return (
        <Pret>
            <ClientsInterne t={t} />
        </Pret>
    );
}

type FiltreClients = "tous" | "actif" | "installation";
const FILTRES_CLIENTS: FiltreClients[] = ["tous", "actif", "installation"];

function ClientsInterne({ t }: { t: Dire }) {
    const { donnees, etat, recharger } = useCharge(() => lireClientsRelation());
    // Sous-lot 9 : les installations interrompues, lues en même temps que la liste (« Reprendre l'installation »).
    const installations = useCharge(() => installationsOuvertesApiV1InstallationsClientOuvertesGet());
    const [nouveau, setNouveau] = useState(false);
    const [reprendre, setReprendre] = useState<number | null>(null);
    const enInstallation = new Set((installations.donnees ?? []).map((i) => i.organization_id));
    const [filtre, setFiltre] = useState<FiltreClients>("tous");
    const [q, setQ] = useState("");
    const tous = donnees ?? [];
    const noms = { tous: t({ en: "All", fr: "Tous" }), actif: t({ en: "In service", fr: "En service" }), installation: t({ en: "Being set up", fr: "En installation" }) };
    const libelle = (f: FiltreClients) => `${noms[f]} ${tous.filter((c) => f === "tous" || c.etat === f).length}`;
    const visibles = tous.filter((c) => (filtre === "tous" || c.etat === filtre) && c.nom.toLowerCase().includes(q.trim().toLowerCase()));
    const recherche = t({ en: "Search a client", fr: "Rechercher un client" });
    return (
        <div className={CONTENEUR}>
            <TitrePage
                titre="Clients"
                action={
                    <Button className="cursor-pointer" onClick={() => setNouveau(true)}>
                        <Plus className="size-4" /> {t({ en: "New client", fr: "Nouveau client" })}
                    </Button>
                }
            />
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees && donnees.length === 0 && <EtatVide cas="premier" icone={Users} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />}
            {donnees && donnees.length > 0 && (
                <>
                    <div className="flex flex-wrap items-center gap-3">
                        <Segmente valeur={libelle(filtre)} options={FILTRES_CLIENTS.map(libelle)} changer={(v) => setFiltre(FILTRES_CLIENTS.find((f) => libelle(f) === v) ?? "tous")} />
                        <div className="relative w-full max-w-72">
                            <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                            <Input value={q} onChange={(e) => setQ(e.target.value)} aria-label={recherche} placeholder={recherche} className="h-8 border-transparent bg-muted/50 pl-8 text-sm shadow-none" />
                        </div>
                    </div>
                    {visibles.length === 0 ? (
                        <EtatVide cas="filtre" recherche={q} effacer={() => { setQ(""); setFiltre("tous"); }} />
                    ) : (
                        <div className="divide-y border-y">
                            {visibles.map((c) => {
                                const agents = c.agents ?? 0;
                                const appels = c.appels_7j ?? 0;
                                return (
                                    <div key={c.id} className="flex items-center gap-4 py-3.5">
                                        <AvatarClient id={c.id} nom={c.nom} taille={40} logo />
                                        <div className="min-w-0 flex-1">
                                            <p className="truncate text-sm font-medium">{c.nom}</p>
                                            <p className="mt-0.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                                <EtatClient etat={c.etat ?? "installation"} />
                                                <span className="inline-flex items-center gap-1"><Bot className="size-3.5" />{t({ en: `${agents} agent${agents !== 1 ? "s" : ""}`, fr: `${agents} agent${agents > 1 ? "s" : ""}` })}</span>
                                                <span className="inline-flex items-center gap-1"><PhoneCall className="size-3.5" />{t({ en: `${appels} call${appels !== 1 ? "s" : ""} in 7 days`, fr: `${appels} appel${appels > 1 ? "s" : ""} en 7 jours` })}</span>
                                                {c.note != null && <span className="inline-flex items-center gap-1" data-testid="note-du-juge" title={t({ en: "Judge's average score over 7 days", fr: "Note moyenne du juge sur 7 jours" })}><Star className="size-3.5" />{t({ en: "Judge score", fr: "Note du juge" })} {t({ en: String(c.note), fr: String(c.note).replace(".", ",") })}</span>}
                                            </p>
                                        </div>
                                        <div className="flex items-center gap-3 text-xs tabular-nums">
                                            {c.ouverts > 0 && <span title={t({ en: "Open threads", fr: "Fils ouverts" })} className="inline-flex items-center gap-1" style={{ color: "var(--acc)" }}><Mail className="size-3.5" />{c.ouverts}</span>}
                                            {c.demandes_nouvelles > 0 && <span title={t({ en: "New requests", fr: "Demandes nouvelles" })} className="inline-flex items-center gap-1" style={{ color: "var(--violet-relation)" }}><Inbox className="size-3.5" />{c.demandes_nouvelles}</span>}
                                            {(c.signalements ?? 0) > 0 && <span title={t({ en: "Reports", fr: "Signalements" })} className="inline-flex items-center gap-1" style={{ color: "var(--pastille-urgente)" }}><Flag className="size-3.5" />{c.signalements}</span>}
                                            {(c.pannes ?? 0) > 0 && <span title={t({ en: "Outages", fr: "Pannes" })} className="inline-flex items-center gap-1" style={{ color: "var(--pastille-urgente)" }}><AlertTriangle className="size-3.5" />{c.pannes}</span>}
                                        </div>
                                        {enInstallation.has(c.id) && (
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                className="cursor-pointer"
                                                data-reprendre-installation={c.id}
                                                onClick={() => {
                                                    setReprendre(c.id);
                                                    setNouveau(true);
                                                }}
                                            >
                                                {t({ en: "Resume the installation", fr: "Reprendre l'installation" })}
                                            </Button>
                                        )}
                                        <Button variant="outline" size="sm" className="cursor-pointer" asChild>
                                            <Link href={`/relation/clients/${c.id}`}>{t({ en: "Open the file", fr: "Ouvrir la fiche" })}</Link>
                                        </Button>
                                    </div>
                                );
                            })}
                        </div>
                    )}
                </>
            )}
            <NouveauClient
                ouvert={nouveau}
                organisationAReprendre={reprendre}
                onOuvert={(o) => {
                    setNouveau(o);
                    if (!o) {
                        setReprendre(null);
                        recharger();
                        installations.recharger();
                    }
                }}
            />
        </div>
    );
}

export function FicheClient({ id }: { id: number }) {
    return (
        <Pret>
            <FicheInterne id={id} />
        </Pret>
    );
}

function FicheInterne({ id }: { id: number }) {
    const { t } = useLangue();
    const clients = useCharge(() => lireClientsRelation());
    const client = clients.donnees?.find((c) => c.id === id);
    if (clients.etat === "chargement") return <div className={CONTENEUR}><EtatVide cas="chargement" /></div>;
    if (!client) return <div className={CONTENEUR}><EtatVide cas="erreur" reessayer={clients.recharger} /></div>;
    const agents = client.agents ?? 0;
    const appels = client.appels_7j ?? 0;
    const signalements = client.signalements ?? 0;
    const pannes = client.pannes ?? 0;
    return (
        <div className="mx-auto flex h-full min-h-0 w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:px-8">
            {/* Le fil d'Ariane dit « Relation clients › Clients › <client> » comme la maquette ; la flèche retour reste (convention des pages ouvertes depuis une autre porte, test T6). */}
            <FlecheRetour href="/relation/clients" libelle={t({ en: "Back to the clients", fr: "Retour aux clients" })} />
            <EnteteStudio miettes={[{ libelle: t(RELATION_CLIENTS), href: "/relation" }, { libelle: t({ en: "Clients", fr: "Clients" }), href: "/relation/clients" }, { libelle: client.nom }]} />
            <div className="flex flex-wrap items-center gap-4">
                <AvatarClient id={client.id} nom={client.nom} taille={56} logo />
                <div className="min-w-0 flex-1">
                    <h2 className="truncate text-2xl font-semibold tracking-tight">{client.nom}</h2>
                    <p className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
                        <EtatClient etat={client.etat ?? "installation"} />
                        <span className="inline-flex items-center gap-1"><Bot className="size-4" />{t({ en: `${agents} agent${agents !== 1 ? "s" : ""}`, fr: `${agents} agent${agents > 1 ? "s" : ""}` })}</span>
                        <span className="inline-flex items-center gap-1"><PhoneCall className="size-4" />{t({ en: `${appels} call${appels !== 1 ? "s" : ""} in 7 days`, fr: `${appels} appel${appels > 1 ? "s" : ""} en 7 jours` })}</span>
                        {client.note != null && <span className="inline-flex items-center gap-1" data-testid="note-du-juge" title={t({ en: "Judge's average score over 7 days", fr: "Note moyenne du juge sur 7 jours" })}><Star className="size-4" />{t({ en: "Judge score", fr: "Note du juge" })} {t({ en: String(client.note), fr: String(client.note).replace(".", ",") })}</span>}
                    </p>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" size="sm" className="cursor-pointer" asChild>
                        <Link href={`/clients/${id}`}>{t({ en: "Open its space", fr: "Ouvrir son espace" })}</Link>
                    </Button>
                    <BoutonPortail organisation={id} />
                </div>
            </div>
            <OngletsPage
                remplir
                espacement="space-y-6"
                onglets={[
                    { id: "messages", titre: t({ en: "Messages", fr: "Messages" }), contenu: <BoiteMessages client={id} /> },
                    { id: "notes", titre: t({ en: "Notes", fr: "Notes" }), contenu: <NotesClient organisation={id} /> },
                    {
                        id: "technique",
                        titre: t({ en: "Technical", fr: "Technique" }),
                        contenu: (
                            <div className="space-y-3 text-sm">
                                {signalements + pannes === 0 ? (
                                    <EtatVide cas="fait" compact titre={t({ en: "Nothing technical is waiting", fr: "Rien de technique n'attend" })} />
                                ) : (
                                    <div className="divide-y border-y">
                                        {signalements > 0 && <p className="flex items-center gap-2 py-3"><Flag className="size-4" style={{ color: "var(--pastille-urgente)" }} />{t({ en: `${signalements} report${signalements !== 1 ? "s" : ""} on a call`, fr: `${signalements} signalement${signalements > 1 ? "s" : ""} sur un appel` })}</p>}
                                        {pannes > 0 && <p className="flex items-center gap-2 py-3"><AlertTriangle className="size-4" style={{ color: "var(--pastille-urgente)" }} />{t({ en: `${pannes} outage${pannes !== 1 ? "s" : ""} or alert${pannes !== 1 ? "s" : ""}`, fr: `${pannes} panne${pannes > 1 ? "s" : ""} ou alerte${pannes > 1 ? "s" : ""}` })}</p>}
                                    </div>
                                )}
                                <Button variant="outline" size="sm" className="cursor-pointer" asChild>
                                    <Link href={`/clients/${id}/a-ameliorer`}>{t({ en: "Open To improve", fr: "Ouvrir À améliorer" })}</Link>
                                </Button>
                            </div>
                        ),
                    },
                    { id: "entrees", titre: t({ en: "Portal entries", fr: "Entrées au portail" }), contenu: <ListeEntrees client={client.nom} /> },
                ]}
            />
        </div>
    );
}

function NotesClient({ organisation }: { organisation: number }) {
    const { t } = useLangue();
    const { donnees, etat, recharger } = useCharge(() => listerNotesApiV1RelationClientsOrganizationIdNotesGet({ path: { organization_id: organisation } }));
    const [texte, setTexte] = useState("");
    const ajouter = async () => {
        const res = await ajouterNoteApiV1RelationClientsOrganizationIdNotesPost({ path: { organization_id: organisation }, body: { texte } });
        if (res.error) return notifier.echec({ fr: "Note non enregistrée. Réessayez.", en: "Note not saved. Try again." }, { erreur: res.error });
        setTexte("");
        recharger();
    };
    const retirer = async (noteId: number) => {
        const res = await supprimerNoteApiV1RelationClientsOrganizationIdNotesNoteIdDelete({ path: { organization_id: organisation, note_id: noteId } });
        if (res.error) return notifier.echec({ fr: "Opération impossible. Réessayez.", en: "Could not complete. Try again." }, { erreur: res.error });
        recharger();
    };
    return (
        <div className="space-y-4">
            <div className="flex items-start gap-2">
                <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} rows={2} />
                <Button size="sm" disabled={!texte.trim()} onClick={ajouter}>{t({ en: "Add", fr: "Ajouter" })}</Button>
                <Info>{t({ en: "Never shown to the client.", fr: "Jamais montrées au client." })}</Info>
            </div>
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees?.length === 0 && <EtatVide cas="premier" icone={MessageSquare} titre={t({ en: "No note yet", fr: "Aucune note pour l'instant" })} />}
            <div className="divide-y">
                {donnees?.map((n) => (
                    <div key={n.id} className="flex items-start justify-between gap-3 py-2 text-sm">
                        <div>
                            <p className="text-xs text-muted-foreground">{n.auteur} · {quand(n.cree_le)}</p>
                            <p className="whitespace-pre-wrap">{n.texte}</p>
                        </div>
                        <SuppressionConfirmee onConfirmer={() => void retirer(n.id)}>{t({ en: "Delete", fr: "Supprimer" })}</SuppressionConfirmee>
                    </div>
                ))}
            </div>
        </div>
    );
}

// ---------------------------------------------------------------------- Entrées dans les portails
/** V4 : la durée d'une visite, mesurée à la sortie dite par le portail : « 45 s », « 4 min 12 s », « 1 h 05 ». */
export function dureeDeVisite(secondes: number): string {
    if (secondes < 60) return `${secondes} s`;
    if (secondes < 3600) return `${Math.floor(secondes / 60)} min ${String(secondes % 60).padStart(2, "0")} s`;
    return `${Math.floor(secondes / 3600)} h ${String(Math.floor((secondes % 3600) / 60)).padStart(2, "0")}`;
}

function ListeEntrees({ client }: { client?: string }) {
    const { t } = useLangue();
    const { donnees, etat, recharger } = useCharge(() => listerEntreesApiV1RelationEntreesGet());
    const [qui, setQui] = useState("");
    const lignes = (donnees ?? []).filter((e) => !client || e.client === client);
    const auteurs = [...new Set(lignes.map((e) => e.auteur))];
    const libelle = (a: string) => `${a || t({ en: "All", fr: "Tous" })} ${lignes.filter((e) => !a || e.auteur === a).length}`;
    const visibles = lignes.filter((e) => !qui || e.auteur === qui);
    if (etat === "chargement") return <EtatVide cas="chargement" />;
    if (etat === "erreur") return <EtatVide cas="erreur" reessayer={recharger} />;
    if (lignes.length === 0) return <EtatVide cas="premier" icone={DoorOpen} titre={t({ en: "No entry yet", fr: "Aucune entrée pour l'instant" })} />;
    return (
        <div className="space-y-4">
            <div className="flex h-9 items-center">
                <Segmente valeur={libelle(qui)} options={["", ...auteurs].map(libelle)} changer={(v) => setQui(["", ...auteurs].find((a) => libelle(a) === v) ?? "")} />
            </div>
            <Paginee liste={visibles}>
                {(page) => (
                    <div className="divide-y border-y">
                        {page.map((e) => (
                            <div key={e.id} className="flex items-center gap-4 py-3.5">
                                <span aria-hidden className="flex size-9 shrink-0 items-center justify-center rounded-full bg-foreground text-sm font-semibold text-background">{e.auteur.slice(0, 1).toUpperCase()}</span>
                                <div className="min-w-0 flex-1">
                                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                                        <DoorOpen className="size-3.5" />
                                        {e.utilise_le ? t({ en: `${e.auteur} entered`, fr: `${e.auteur} est entré chez` }) : t({ en: `${e.auteur} asked for a link to`, fr: `${e.auteur} a demandé un lien pour` })}
                                        {!client && <span className="font-medium text-foreground">{e.client}</span>}
                                    </p>
                                    <p className="mt-0.5 truncate text-sm font-medium">{e.motif ?? ""}</p>
                                </div>
                                <span data-colonne-duree className="w-28 shrink-0 text-right text-xs text-muted-foreground">
                                    {e.duree_secondes != null ? (
                                        <span data-duree-visite={e.duree_secondes}>{dureeDeVisite(e.duree_secondes)}</span>
                                    ) : e.utilise_le ? (
                                        "—"
                                    ) : (
                                        t({ en: "Not used", fr: "Non utilisé" })
                                    )}
                                </span>
                                <span className="w-28 shrink-0 text-right text-xs text-muted-foreground">{quand(e.cree_le)}</span>
                            </div>
                        ))}
                    </div>
                )}
            </Paginee>
        </div>
    );
}

export function EcranEntrees() {
    const { t } = useLangue();
    return (
        <Pret>
            <div className={CONTENEUR}>
                <TitrePage
                    titre={t({ en: "Portal entries", fr: "Entrées dans les portails" })}
                    info={t({ en: "Each entry uses a one-minute, single-use link. The client's manager sees it too.", fr: "Chaque entrée passe par un lien d'une minute, à usage unique. Le dirigeant du client la voit aussi." })}
                />
                <ListeEntrees />
            </div>
        </Pret>
    );
}

// ---------------------------------------------------------------------- Avis et témoignages
export function EcranAvis() {
    const { t } = useLangue();
    return (
        <Pret>
            <AvisInterne t={t} />
        </Pret>
    );
}

type FiltreAvis = "tous" | "donne" | "a_demander";
const FILTRES_AVIS: FiltreAvis[] = ["tous", "donne", "a_demander"];

function AvisInterne({ t }: { t: Dire }) {
    const { donnees, etat, recharger } = useCharge(() => avisEtTemoignagesApiV1RelationAvisGet());
    const [filtre, setFiltre] = useState<FiltreAvis>("tous");
    const [ajout, setAjout] = useState(false);
    const [asupprimer, setAsupprimer] = useState<{ organisation: number; id: number } | null>(null);
    const lignes = (donnees ?? []).flatMap((c) => c.temoignages.map((x) => ({ client: c, x })));
    const noms: Record<FiltreAvis, string> = { tous: t({ en: "All", fr: "Tous" }), donne: t({ en: "Agreed", fr: "Accord donné" }), a_demander: t({ en: "Agreement to ask", fr: "Accord à demander" }) };
    const dans = (f: FiltreAvis, accord: boolean) => f === "tous" || (f === "donne") === accord;
    const libelle = (f: FiltreAvis) => `${noms[f]} ${lignes.filter((l) => dans(f, l.x.accord)).length}`;
    const visibles = lignes.filter((l) => dans(filtre, l.x.accord));
    const decider = async (organisation: number, id: number, accord: boolean) => {
        const res = await reglerAccordApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdPatch({ path: { organization_id: organisation, temoignage_id: id }, body: { accord } });
        if (res.error) return notifier.echec({ fr: "Accord non enregistré. Réessayez.", en: "Agreement not saved. Try again." }, { erreur: res.error });
        notifier.succes(accord ? { fr: "Accord noté.", en: "Agreement noted." } : { fr: "Accord retiré.", en: "Agreement withdrawn." });
        recharger();
    };
    const supprimer = async () => {
        if (!asupprimer) return;
        // suppression-confirmee : la fenêtre « Supprimer ce témoignage ? » précède `supprimer`.
        const res = await supprimerTemoignageApiV1RelationClientsOrganizationIdTemoignagesTemoignageIdDelete({ path: { organization_id: asupprimer.organisation, temoignage_id: asupprimer.id } });
        setAsupprimer(null);
        if (res.error) return notifier.echec({ fr: "Suppression impossible. Réessayez.", en: "Could not delete. Try again." }, { erreur: res.error });
        notifier.succes({ fr: "Témoignage supprimé.", en: "Testimonial deleted." });
        recharger();
    };
    return (
        <div className={CONTENEUR}>
            <TitrePage
                titre={t({ en: "Reviews and testimonials", fr: "Avis et témoignages" })}
                info={t({ en: "The average comes from the visitors' reviews on each client's site. A testimonial is publishable only with the client's agreement.", fr: "La moyenne vient des avis des visiteurs du site de chaque client. Un témoignage n'est publiable qu'avec l'accord du client." })}
                action={
                    donnees && donnees.length > 0 ? (
                        <Button className="cursor-pointer" onClick={() => setAjout(true)}>
                            <Plus className="size-4" /> {t({ en: "Add a testimonial", fr: "Ajouter un témoignage" })}
                        </Button>
                    ) : undefined
                }
            />
            {etat === "chargement" && <EtatVide cas="chargement" />}
            {etat === "erreur" && <EtatVide cas="erreur" reessayer={recharger} />}
            {donnees?.length === 0 && <EtatVide cas="premier" icone={Star} titre={t({ en: "No client yet", fr: "Aucun client pour l'instant" })} />}
            {donnees && donnees.length > 0 && (
                <>
                    <Segmente valeur={libelle(filtre)} options={FILTRES_AVIS.map(libelle)} changer={(v) => setFiltre(FILTRES_AVIS.find((f) => libelle(f) === v) ?? "tous")} />
                    {visibles.length === 0 ? (
                        <EtatVide cas="premier" icone={Star} titre={t({ en: "No testimonial", fr: "Aucun témoignage" })} />
                    ) : (
                        <div className="divide-y border-y">
                            {visibles.map(({ client: c, x }) => (
                                <div key={x.id} className="flex items-center gap-4 py-3.5">
                                    <AvatarClient id={c.organization_id} nom={c.client} taille={40} logo />
                                    <div className="min-w-0 flex-1">
                                        <p className="text-xs text-muted-foreground"><span className="font-medium text-foreground">{c.client}</span> · {x.auteur}</p>
                                        <p className="mt-0.5 text-sm italic">« {x.texte} »</p>
                                    </div>
                                    {c.note !== null && (
                                        <span className="inline-flex shrink-0 items-center gap-1 text-sm tabular-nums">
                                            <Star className="size-4 fill-current" />
                                            <span className="font-medium">{t({ en: String(c.note), fr: String(c.note).replace(".", ",") })}</span>
                                            <span className="text-muted-foreground">({c.avis} {t({ en: "reviews", fr: "avis" })})</span>
                                        </span>
                                    )}
                                    <span className="w-40 shrink-0">
                                        <PointEtat etat={x.accord ? "publie" : "attente"}>{x.accord ? t({ en: "Agreement given", fr: "Accord donné" }) : t({ en: "Agreement to ask", fr: "Accord à demander" })}</PointEtat>
                                    </span>
                                    <Button variant="ghost" size="sm" className="cursor-pointer" onClick={() => void decider(c.organization_id, x.id, !x.accord)}>
                                        {x.accord ? t({ en: "Withdraw", fr: "Retirer l'accord" }) : t({ en: "Mark agreed", fr: "Accord obtenu" })}
                                    </Button>
                                    <Button variant="ghost" size="sm" className="cursor-pointer" onClick={() => setAsupprimer({ organisation: c.organization_id, id: x.id })}>
                                        {t({ en: "Delete", fr: "Supprimer" })}
                                    </Button>
                                </div>
                            ))}
                        </div>
                    )}
                </>
            )}
            <AjoutTemoignage ouvert={ajout} fermer={() => setAjout(false)} clients={(donnees ?? []).map((c) => ({ id: c.organization_id, nom: c.client }))} fait={recharger} />
            <Dialog centree open={asupprimer !== null} onOpenChange={(o) => !o && setAsupprimer(null)}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{t({ en: "Delete this testimonial?", fr: "Supprimer ce témoignage ?" })}</DialogTitle>
                        <DialogDescription>{t({ en: "It is removed for good. The client's agreement goes with it.", fr: "Il est retiré définitivement, avec l'accord du client." })}</DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" className="cursor-pointer" onClick={() => setAsupprimer(null)}>{t({ en: "Cancel", fr: "Annuler" })}</Button>
                        <Button variant="destructive" className="cursor-pointer" onClick={() => void supprimer()}>{t({ en: "Delete", fr: "Supprimer" })}</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}

/** Ajouter un témoignage : le client, le texte et son auteur, dans une fenêtre centrée à corps blanc. */
function AjoutTemoignage({ ouvert, fermer, clients, fait }: { ouvert: boolean; fermer: () => void; clients: { id: number; nom: string }[]; fait: () => void }) {
    const { t } = useLangue();
    const [client, setClient] = useState("");
    const [texte, setTexte] = useState("");
    const [auteur, setAuteur] = useState("");
    const choisi = client || String(clients[0]?.id ?? "");
    const ajouter = async () => {
        const res = await ajouterTemoignageApiV1RelationClientsOrganizationIdTemoignagesPost({ path: { organization_id: Number(choisi) }, body: { texte, auteur, accord: false } });
        if (res.error) return notifier.echec({ fr: "Témoignage non enregistré. Réessayez.", en: "Testimonial not saved. Try again." }, { erreur: res.error });
        notifier.succes({ fr: "Témoignage ajouté.", en: "Testimonial added." });
        setTexte("");
        setAuteur("");
        fermer();
        fait();
    };
    return (
        <Dialog centree open={ouvert} onOpenChange={(o) => !o && fermer()}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Add a testimonial", fr: "Ajouter un témoignage" })}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <Liste valeur={choisi} changer={setClient} options={clients.map((c) => ({ valeur: String(c.id), libelle: c.nom }))} className="w-full" />
                    <Textarea value={texte} onChange={(e) => setTexte(e.target.value)} rows={3} aria-label={t({ en: "Testimonial", fr: "Témoignage" })} placeholder={t({ en: "Testimonial", fr: "Témoignage" })} />
                    <Input value={auteur} onChange={(e) => setAuteur(e.target.value)} aria-label={t({ en: "Author, role", fr: "Auteur, fonction" })} placeholder={t({ en: "Author, role", fr: "Auteur, fonction" })} />
                </div>
                <DialogFooter>
                    <Button variant="outline" className="cursor-pointer" onClick={fermer}>{t({ en: "Cancel", fr: "Annuler" })}</Button>
                    <Button className="cursor-pointer" disabled={!texte.trim() || !auteur.trim()} onClick={() => void ajouter()}>{t({ en: "Add", fr: "Ajouter" })}</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
