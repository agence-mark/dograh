"use client";

import { Building2, Check, ExternalLink, Inbox, Lock, Search, Send } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
    lireFilApiV1RelationClientsOrganizationIdFilsFilIdGet,
    listerFilsApiV1RelationFilsGet,
    modifierFilApiV1RelationClientsOrganizationIdFilsFilIdPatch,
    repondreApiV1RelationClientsOrganizationIdFilsFilIdMessagesPost,
} from "@/client/sdk.gen";
import type { ClientOut, FilOut } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info, PointEtat } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

import { AvatarClient, ETATS_DEMANDE, ETATS_FIL, EtatClient, quand } from "./commun";
import { lireClientsRelation } from "./lecture-clients";

type Onglet = "a_traiter" | "moi" | "tous";
const ONGLETS: Onglet[] = ["a_traiter", "moi", "tous"];
type Dire = (x: { en: string; fr: string }) => string;

/** Le contact d'un fil : celui qui a écrit en premier côté client (fil lu en entier), sinon le dernier message du client, sinon le client. */
const contact = (f: FilOut) => f.messages?.find((m) => m.cote === "client")?.auteur ?? (f.dernier?.cote === "client" ? f.dernier.auteur : f.client);

/**
 * [.mark] Messages (E92, E93) : la boîte à trois colonnes comme Intercom, Front ou Crisp. Les fils à gauche (À traiter, À moi,
 * Tous, recherche, client, type), la conversation au centre (répondre au client ou écrire une note interne), le client à droite.
 * Une demande de logiciel est un fil comme un autre, avec son état propre. `client` fige la boîte sur un client (fiche d'un
 * client) : la colonne du client disparaît, on y est déjà. Une seule lecture par onglet, lancées ensemble.
 */
export function BoiteMessages({ client, filInitial }: { client?: number; filInitial?: number | null }) {
    const { t } = useLangue();
    const [onglet, setOnglet] = useState<Onglet>("a_traiter");
    const [q, setQ] = useState("");
    const [qui, setQui] = useState("");
    const [type, setType] = useState("");
    const [listes, setListes] = useState<Record<Onglet, FilOut[]> | null>(null);
    const [clients, setClients] = useState<ClientOut[]>([]);
    const [erreur, setErreur] = useState(false);
    const [actif, setActif] = useState<{ organisation: number; id: number } | null>(null);

    const charger = useCallback(() => {
        const lire = (suivi: "moi" | undefined, a_traiter: boolean) => listerFilsApiV1RelationFilsGet({ query: { a_traiter, suivi, client } });
        Promise.all([lire(undefined, true), lire("moi", false), lire(undefined, false), lireClientsRelation()]).then(([a, m, tous, cl]) => {
            if (a.error || m.error || tous.error || !a.data || !m.data || !tous.data) return setErreur(true);
            setErreur(false);
            setListes({ a_traiter: a.data, moi: m.data, tous: tous.data });
            if (cl.data) setClients(cl.data);
        });
    }, [client]);
    useEffect(charger, [charger]);

    useEffect(() => {
        if (filInitial && listes && !actif) {
            const f = listes.tous.find((x) => x.id === filInitial);
            if (f) setActif({ organisation: f.organization_id, id: f.id });
        }
    }, [filInitial, listes, actif]);

    const filtres = useCallback(
        (liste: FilOut[]) =>
            liste.filter(
                (f) =>
                    (!qui || String(f.organization_id) === qui) &&
                    (!type || (type === "demandes") === (f.sorte === "demande_logiciel")) &&
                    `${f.sujet} ${contact(f)} ${f.client} ${f.dernier?.texte ?? ""}`.toLowerCase().includes(q.trim().toLowerCase()),
            ),
        [qui, type, q],
    );
    const visibles = useMemo(() => (listes ? filtres(listes[onglet]) : []), [listes, onglet, filtres]);
    const parId = useMemo(() => new Map(clients.map((c) => [c.id, c])), [clients]);

    if (erreur) return <EtatVide cas="erreur" reessayer={charger} />;
    if (listes === null) return <EtatVide cas="chargement" />;

    const noms: Record<Onglet, string> = { a_traiter: t({ en: "To handle", fr: "À traiter" }), moi: t({ en: "Mine", fr: "À moi" }), tous: t({ en: "All", fr: "Tous" }) };
    const libelle = (o: Onglet) => `${noms[o]} ${listes[o].length}`;
    const ficheDuFil = actif ? listes.tous.find((f) => f.id === actif.id) : undefined;
    const clientDuFil = ficheDuFil ? parId.get(ficheDuFil.organization_id) : undefined;
    const filtreActif = Boolean(q.trim() || type || (qui && !client));

    return (
        <div className={`grid min-h-[460px] overflow-hidden ${client ? "h-[calc(100vh-17rem)] grid-cols-[300px_minmax(0,1fr)]" : "h-full grid-cols-[300px_minmax(0,1fr)_250px]"}`}>
            <div className="flex min-h-0 flex-col border-r">
                <div className="shrink-0 space-y-2 p-3">
                    {!client && (
                        <h1 className="flex items-center gap-2 px-1 pt-1 pb-1 text-lg font-semibold">
                            {t({ en: "Messages", fr: "Messages" })}
                            <Info>{t({ en: "Messages and software requests your clients send from their portal, with our replies. Internal notes stay between us: the portal never receives them.", fr: "Ce que les clients écrivent depuis leur portail : leurs messages et leurs demandes de logiciel, avec nos réponses. Les notes internes restent entre nous : le portail ne les reçoit jamais." })}</Info>
                        </h1>
                    )}
                    <Segmente valeur={libelle(onglet)} options={ONGLETS.map(libelle)} changer={(v) => setOnglet(ONGLETS.find((o) => libelle(o) === v) ?? "a_traiter")} />
                    <div className="relative w-full max-w-72">
                        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
                        <Input value={q} onChange={(e) => setQ(e.target.value)} aria-label={t({ en: "Search", fr: "Rechercher" })} placeholder={t({ en: "Search", fr: "Rechercher" })} className="h-8 border-transparent bg-muted/50 pl-8 text-sm shadow-none" />
                    </div>
                    <div className={`grid gap-2 ${client ? "" : "grid-cols-[minmax(0,1fr)_7.5rem]"}`}>
                        {!client && (
                            <Liste valeur={qui} changer={setQui} vide={t({ en: "All clients", fr: "Tous les clients" })} options={clients.map((c) => ({ valeur: String(c.id), libelle: c.nom }))} className="w-full" />
                        )}
                        <Liste valeur={type} changer={setType} vide={t({ en: "All", fr: "Tout" })} options={[{ valeur: "messages", libelle: "Messages" }, { valeur: "demandes", libelle: t({ en: "Requests", fr: "Demandes" }) }]} className="w-full" />
                    </div>
                </div>
                <div className="min-h-0 flex-1 space-y-0.5 overflow-auto px-2 pb-2">
                    {visibles.length === 0 ? (
                        filtreActif ? (
                            <EtatVide cas="filtre" compact recherche={q.trim() || (type ? (type === "demandes" ? t({ en: "Requests", fr: "Demandes" }) : "Messages") : clients.find((c) => String(c.id) === qui)?.nom ?? "")} effacer={() => { setQ(""); setType(""); setQui(""); }} />
                        ) : onglet !== "tous" ? (
                            <EtatVide cas="fait" compact titre={t({ en: "Nothing is waiting", fr: "Rien n'attend" })} />
                        ) : (
                            <EtatVide cas="premier" compact icone={Inbox} titre={t({ en: "No thread", fr: "Aucun fil" })} />
                        )
                    ) : (
                        visibles.map((f) => <CarteFil key={f.id} f={f} actif={actif?.id === f.id} ouvrir={() => setActif({ organisation: f.organization_id, id: f.id })} t={t} />)
                    )}
                </div>
            </div>
            <div className="min-w-0">
                {actif ? (
                    <Conversation key={`${actif.organisation}-${actif.id}`} organisation={actif.organisation} id={actif.id} onChange={charger} t={t} />
                ) : (
                    <EtatVide cas="premier" icone={Inbox} titre={t({ en: "Pick a thread", fr: "Choisis un fil" })} />
                )}
            </div>
            {!client && (
                <div className="min-w-0 overflow-auto border-l">
                    {ficheDuFil && <FicheMini fil={ficheDuFil} client={clientDuFil} autres={listes.tous.filter((x) => x.organization_id === ficheDuFil.organization_id && x.id !== ficheDuFil.id)} ouvrir={(f) => setActif({ organisation: f.organization_id, id: f.id })} t={t} />}
                </div>
            )}
        </div>
    );
}

/** Une ligne de la boîte : avatar du client, contact, sujet, aperçu, heure, point bleu si non lu. */
function CarteFil({ f, actif, ouvrir, t }: { f: FilOut; actif: boolean; ouvrir: () => void; t: Dire }) {
    const demande = f.sorte === "demande_logiciel";
    const dernier = f.dernier;
    const prefixe = dernier?.cote === "interne" ? `${t({ en: "Internal note", fr: "Note interne" })} : ` : dernier?.cote === "mark" ? `${t({ en: "You", fr: "Vous" })} : ` : "";
    return (
        <button type="button" onClick={ouvrir} aria-current={actif} className={`flex w-full cursor-pointer gap-3 rounded-lg px-3 py-3 text-left transition-colors hover:font-semibold ${actif ? "bg-muted" : "hover:bg-muted/50"}`}>
            <AvatarClient id={f.organization_id} nom={contact(f)} />
            <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                    <span className={`flex-1 truncate text-sm ${f.lu_par_mark ? "" : "font-semibold"}`}>{contact(f)}</span>
                    <span className="shrink-0 text-xs font-normal text-muted-foreground">{quand(f.modifie_le)}</span>
                </span>
                <span className="flex items-center gap-2">
                    <span className={`flex-1 truncate text-sm ${f.lu_par_mark ? "text-muted-foreground" : "font-medium"}`}>
                        {demande && <span className="mr-1 inline-flex items-center gap-1" style={{ color: "var(--violet-relation)" }}><Inbox className="size-3.5" />{t({ en: "Request", fr: "Demande" })} :</span>}
                        {f.sujet}
                    </span>
                    {!f.lu_par_mark && <span role="img" aria-label={t({ en: "Unread", fr: "Non lu" })} className="size-2 shrink-0 rounded-full bg-(--acc)" />}
                </span>
                <span className="block truncate text-xs font-normal text-muted-foreground">
                    {f.client}
                    {dernier ? ` · ${prefixe}${dernier.texte}` : ""}
                </span>
            </span>
        </button>
    );
}

/** La colonne du client : qui c'est, où il en est, ses autres échanges, la porte vers son espace. */
function FicheMini({ fil, client, autres, ouvrir, t }: { fil: FilOut; client?: ClientOut; autres: FilOut[]; ouvrir: (f: FilOut) => void; t: Dire }) {
    return (
        <div className="space-y-5 p-5 text-sm">
            <div className="flex flex-col items-center gap-2 text-center">
                <AvatarClient id={fil.organization_id} nom={contact(fil)} taille={52} />
                <p className="font-semibold">{contact(fil)}</p>
                <p className="flex items-center gap-1 text-xs text-muted-foreground"><Building2 className="size-3.5" />{fil.client}</p>
            </div>
            <div className="divide-y border-y">
                <p className="flex justify-between py-2"><span className="text-muted-foreground">{t({ en: "State", fr: "État" })}</span>{client ? <EtatClient etat={client.etat ?? "installation"} /> : null}</p>
                <p className="flex justify-between py-2"><span className="text-muted-foreground">{t({ en: "Agents", fr: "Agents" })}</span><span>{client?.agents ?? 0}</span></p>
                <p className="flex justify-between py-2"><span className="text-muted-foreground">{t({ en: "Followed by", fr: "Suivi par" })}</span><span>{fil.suivi_nom ?? t({ en: "Nobody", fr: "Personne" })}</span></p>
            </div>
            <div className="space-y-1">
                <p className="text-xs font-medium tracking-wider text-muted-foreground uppercase">{t({ en: "Other threads", fr: "Autres échanges" })}</p>
                {autres.length ? (
                    autres.map((x) => {
                        const e = ETATS_FIL[x.etat];
                        return (
                            <button key={x.id} type="button" onClick={() => ouvrir(x)} className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted/50 hover:font-semibold">
                                <span className="flex-1 truncate">{x.sujet}</span>
                                <PointEtat etat={x.etat === "nouveau" ? "attente" : x.etat === "repondu" ? "publie" : x.etat === "clos" ? "fini" : "brouillon"}>{e ? t(e.texte) : x.etat}</PointEtat>
                            </button>
                        );
                    })
                ) : (
                    <p className="text-muted-foreground">{t({ en: "No other thread.", fr: "Aucun autre échange." })}</p>
                )}
            </div>
            <Button variant="outline" size="sm" className="w-full cursor-pointer" asChild>
                <Link href={`/clients/${fil.organization_id}`}><ExternalLink className="size-3.5" /> {t({ en: "Open the client's space", fr: "Ouvrir l'espace du client" })}</Link>
            </Button>
        </div>
    );
}

function Conversation({ organisation, id, onChange, t }: { organisation: number; id: number; onChange: () => void; t: Dire }) {
    const [fil, setFil] = useState<FilOut | null>(null);
    const [mode, setMode] = useState<"mark" | "interne">("mark");
    const [texte, setTexte] = useState("");
    const [envoi, setEnvoi] = useState(false);
    const interne = mode === "interne";

    const lire = useCallback(() => {
        lireFilApiV1RelationClientsOrganizationIdFilsFilIdGet({ path: { organization_id: organisation, fil_id: id } }).then((res) => {
            if (res.data) setFil(res.data);
            else notifier.echec({ fr: "Fil illisible. Rechargez la page.", en: "Could not load the thread. Reload the page." }, { erreur: res.error });
        });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [organisation, id]);
    useEffect(lire, [lire]);

    const changer = async (corps: { etat?: "nouveau" | "en_cours" | "repondu" | "clos"; suivi?: "moi" | "personne"; etat_demande?: "nouvelle" | "proposee" | "a_coder" | "refusee" }) => {
        const res = await modifierFilApiV1RelationClientsOrganizationIdFilsFilIdPatch({ path: { organization_id: organisation, fil_id: id }, body: corps });
        if (res.error) return notifier.echec({ fr: "Modification impossible. Réessayez.", en: "Could not change. Try again." }, { erreur: res.error });
        lire();
        onChange();
    };

    const envoyer = async () => {
        if (!texte.trim()) return;
        setEnvoi(true);
        const res = await repondreApiV1RelationClientsOrganizationIdFilsFilIdMessagesPost({ path: { organization_id: organisation, fil_id: id }, body: { cote: mode, texte } });
        setEnvoi(false);
        if (res.error) return notifier.echec({ fr: "Message non envoyé. Réessayez.", en: "Message not sent. Try again." }, { erreur: res.error, reessayer: () => void envoyer() });
        setTexte("");
        lire();
        onChange();
    };

    if (!fil) return <EtatVide cas="chargement" />;
    const demande = fil.sorte === "demande_logiciel";
    return (
        <div className="flex h-full min-h-0 flex-col">
            <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b px-5 py-3">
                <div className="min-w-0 basis-full">
                    <p className="truncate font-semibold">{fil.sujet}</p>
                    <p className="text-xs text-muted-foreground">{contact(fil)} · {fil.client}</p>
                </div>
                <Button variant="outline" size="sm" className="cursor-pointer" onClick={() => changer({ suivi: fil.suivi_par ? "personne" : "moi" })}>
                    {fil.suivi_par ? `${t({ en: "Followed by", fr: "Suivi par" })} ${fil.suivi_nom ?? ""} · ${t({ en: "Release", fr: "Lâcher" })}` : t({ en: "Take it", fr: "Je m'en occupe" })}
                </Button>
                <Liste valeur={fil.etat} changer={(v) => changer({ etat: v as "nouveau" })} options={Object.entries(ETATS_FIL).map(([valeur, e]) => ({ valeur, libelle: t(e.texte) }))} className="w-32" />
                {fil.etat !== "clos" ? (
                    <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => changer({ etat: "clos" })}><Check className="size-3.5" /> {t({ en: "Close", fr: "Clore" })}</Button>
                ) : (
                    <Button size="sm" variant="outline" className="cursor-pointer" onClick={() => changer({ etat: "en_cours" })}>{t({ en: "Reopen", fr: "Rouvrir" })}</Button>
                )}
            </div>
            {demande && (
                <div className="flex shrink-0 flex-wrap items-center gap-3 border-b px-5 py-3 text-sm">
                    <div className="min-w-48 flex-1">
                        <p className="font-medium">{fil.logiciel}</p>
                        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                            {t({ en: "Software request", fr: "Demande de logiciel" })}
                            <Info>{t({ en: "A software request. Propose it to the client when it is in the catalogue, mark it to build, or decline it.", fr: "Une demande de logiciel. La proposer au client si elle est au catalogue, la marquer à coder, ou la refuser." })}</Info>
                        </p>
                    </div>
                    <Liste valeur={fil.etat_demande ?? "nouvelle"} changer={(v) => changer({ etat_demande: v as "nouvelle" })} options={Object.entries(ETATS_DEMANDE).map(([valeur, l]) => ({ valeur, libelle: t(l) }))} />
                </div>
            )}
            <div className="min-h-0 flex-1 space-y-4 overflow-auto px-5 py-5">
                {(fil.messages ?? []).map((m) =>
                    m.cote === "interne" ? (
                        <div key={m.id} className="rounded-xl border border-dashed px-4 py-3 text-sm">
                            <p className="mb-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                                <Lock className="size-3" />
                                <span className="font-medium text-foreground">{m.auteur}</span>· {t({ en: "Internal note, never seen by the client", fr: "Note interne, jamais vue du client" })}
                                <span className="ml-auto">{quand(m.cree_le)}</span>
                            </p>
                            <p className="whitespace-pre-wrap">{m.texte}</p>
                        </div>
                    ) : (
                        <div key={m.id} className={`flex items-end gap-2 ${m.cote === "mark" ? "flex-row-reverse" : ""}`}>
                            {m.cote === "mark" ? (
                                <span aria-hidden className="flex size-7 shrink-0 items-center justify-center rounded-full bg-foreground text-[10px] font-semibold text-background">{m.auteur.slice(0, 2).toUpperCase()}</span>
                            ) : (
                                <AvatarClient id={fil.organization_id} nom={m.auteur} taille={28} />
                            )}
                            <div className={`max-w-[75%] space-y-1 ${m.cote === "mark" ? "text-right" : ""}`}>
                                <div className={`w-fit rounded-2xl px-4 py-2.5 text-left text-sm whitespace-pre-wrap ${m.cote === "mark" ? "ml-auto rounded-br-md bg-foreground text-background" : "rounded-bl-md bg-muted"}`}>{m.texte}</div>
                                <p className="text-[11px] text-muted-foreground">{m.auteur} · {quand(m.cree_le)}</p>
                            </div>
                        </div>
                    ),
                )}
            </div>
            <div className="shrink-0 p-4 pt-0">
                <div className={`rounded-xl border bg-card shadow-sm ${interne ? "border-dashed" : ""}`}>
                    <div className="flex items-center gap-1 border-b px-2 pt-1.5">
                        {(["mark", "interne"] as const).map((o) => (
                            <button key={o} type="button" onClick={() => setMode(o)} className={`-mb-px flex cursor-pointer items-center gap-1.5 border-b-2 px-2.5 py-1.5 text-sm hover:font-medium ${mode === o ? "border-foreground font-medium" : "border-transparent text-muted-foreground"}`}>
                                {o === "interne" && <Lock className="size-3" />}
                                {o === "mark" ? t({ en: "Reply", fr: "Répondre" }) : t({ en: "Internal note", fr: "Note interne" })}
                            </button>
                        ))}
                    </div>
                    <Textarea
                        value={texte}
                        onChange={(e) => setTexte(e.target.value)}
                        rows={2}
                        aria-label={interne ? t({ en: "Internal note", fr: "Note interne" }) : t({ en: "Your reply", fr: "Votre réponse" })}
                        placeholder={interne ? t({ en: "A note for the team", fr: "Une note pour l'équipe" }) : `${t({ en: "Reply to", fr: "Répondre à" })} ${contact(fil)}`}
                        className="resize-none border-0 shadow-none focus-visible:ring-0"
                    />
                    <div className="flex items-center gap-2 px-3 pb-2.5">
                        <Info>{interne ? t({ en: "An internal note stays in Dograh: the server never sends it to the portal.", fr: "Une note interne reste dans Dograh : le serveur ne l'envoie jamais au portail." }) : t({ en: "A reply goes to « Your exchanges with .mark » in the client's portal.", fr: "Une réponse part dans « Vos échanges avec .mark » du portail du client." })}</Info>
                        <Button size="sm" className="ml-auto cursor-pointer" disabled={envoi || !texte.trim()} onClick={envoyer}>
                            <Send className="size-3.5" />
                            {interne ? t({ en: "Add the note", fr: "Ajouter la note" }) : t({ en: "Send", fr: "Envoyer" })}
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    );
}
