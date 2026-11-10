"use client";

/**
 * [.mark] Builder partie 3, sous-lot 10 (SE-3, E-3) : les vues « tous clients » de l'équipe, dans le Labo.
 *
 * Lecture seule : les deux listes (appels, conversations du builder) viennent de `GET /vues-equipe/...`, qui ne montre que les clients
 * que le rôle du compte ouvre. Une ligne mène chez le client (là où l'on agit). Requêtes partagées avec le reste de la page : une par liste.
 */
import { ChevronRight, MessageSquare, Phone, Search } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { chatDeTousLesClientsApiV1VuesEquipeChatGet, conversationsDeTousLesClientsApiV1VuesEquipeConversationsGet } from "@/client";
import type { ConversationsEquipeResponse, FilsEquipe } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EnDirect, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { NoteJuge, Pastille } from "@/components/mark/studio/marques";
import { dureeLisible, RechercheAppels } from "@/components/mark/studio/recherche-appels";
import { Input } from "@/components/ui/input";
import { DateRelative } from "@/components/mark/studio/date-relative";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { espaceDe } from "@/components/mark/studio/navigation-studio";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth";

const PAR_PAGE = 25;

/** Vrai dans le Labo : c'est là, et seulement là, que la vue « tous clients » existe. */
export const useDansLeLabo = () => espaceDe(usePathname() ?? "/labo").espace === "labo";

type Charge<T> = { etat: "chargement" } | { etat: "erreur" } | { etat: "acces" } | { etat: "pret"; donnees: T };

const T = {
    client: { en: "Client", fr: "Client" },
    agent: { en: "Agent", fr: "Agent" },
    motif: { en: "Reason", fr: "Motif" },
    resume: { en: "Summary", fr: "Résumé" },
    issue: { en: "Outcome", fr: "Issue" },
    duree: { en: "Duration", fr: "Durée" },
    jugePar: { en: "Judged by", fr: "Jugé par" },
    note: { en: "Grade", fr: "Note" },
    quand: { en: "When", fr: "Quand" },
    titre: { en: "Title", fr: "Titre" },
    changements: { en: "Changes", fr: "Changements" },
    aucunAppel: { en: "No call yet", fr: "Aucun appel encore" },
    aucunChat: { en: "No chat yet", fr: "Aucun chat encore" },
    rechercher: { en: "Search a chat", fr: "Rechercher un chat" },
    precedent: { en: "Previous", fr: "Précédent" },
    suivant: { en: "Next", fr: "Suivant" },
};

/** Charge une page d'une liste « tous clients ». Une lecture refusée (403) dit « accès », une panne « erreur ». */
function usePage<T>(
    lire: (decalage: number) => Promise<{ data?: T; error?: unknown; response?: { status?: number } }>,
    /** Clôture SA-5 : ce qui change la requête (recherche, motif) : la liste revient à la première page. */
    cle = "",
) {
    const { user, loading } = useAuth();
    const [decalage, setDecalage] = useState(0);
    const [charge, setCharge] = useState<Charge<T>>({ etat: "chargement" });
    const derniere = useRef(0);
    const cleAvant = useRef(cle);
    const charger = useCallback(async () => {
        const numero = ++derniere.current;
        // Les données déjà là restent affichées pendant une nouvelle lecture (la barre de recherche garde son focus).
        setCharge((c) => (c.etat === "pret" ? c : { etat: "chargement" }));
        const r = await lire(decalage);
        if (numero !== derniere.current) return; // une lecture plus récente a pris la suite
        if (r.error || r.data === undefined) setCharge({ etat: r.response?.status === 403 ? "acces" : "erreur" });
        else setCharge({ etat: "pret", donnees: r.data });
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [decalage, cle]);
    useEffect(() => {
        if (cleAvant.current !== cle) {
            cleAvant.current = cle;
            if (decalage !== 0) {
                setDecalage(0); // la lecture repart d'elle-même avec le nouveau décalage
                return;
            }
        }
        if (loading || !user) return;
        void charger();
    }, [loading, user, charger, cle, decalage]);
    return { charge, decalage, setDecalage, recharger: charger };
}

function Pagination({ decalage, total, aller }: { decalage: number; total: number; aller: (d: number) => void }) {
    const { t } = useLangue();
    if (total <= PAR_PAGE) return null;
    return (
        <div className="flex items-center justify-end gap-2 pt-3 text-xs text-muted-foreground">
            <span>
                {decalage + 1}-{Math.min(decalage + PAR_PAGE, total)} / {total}
            </span>
            <Button size="sm" variant="ghost" disabled={decalage === 0} onClick={() => aller(Math.max(0, decalage - PAR_PAGE))}>
                {t(T.precedent)}
            </Button>
            <Button size="sm" variant="ghost" disabled={decalage + PAR_PAGE >= total} onClick={() => aller(decalage + PAR_PAGE)}>
                {t(T.suivant)}
            </Button>
        </div>
    );
}

/**
 * Les appels de tous les clients ouverts : la liste de la maquette (`ListeAppelsPlus`) : « Chercher un mot », « Tous les motifs », puis
 * Quand, Agent, Client, Motif, Résumé, Issue, Durée, Jugé par, Note. Recherche et motif sont lus par le serveur (dans la requête,
 * cloisonnée par le rôle), jamais filtrés ici. Clôture SA-5 (É8).
 */
export function ConversationsTousClients() {
    const { t } = useLangue();
    const [recherche, setRecherche] = useState("");
    const [motif, setMotif] = useState("");
    const { charge, decalage, setDecalage, recharger } = usePage<ConversationsEquipeResponse>(
        (d) =>
            conversationsDeTousLesClientsApiV1VuesEquipeConversationsGet({
                query: { limit: PAR_PAGE, offset: d, ...(recherche && { recherche }), ...(motif && { motif }) },
            }),
        `${recherche}|${motif}`,
    );
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={() => void recharger()} />;
    const { conversations, total, motifs = [] } = charge.donnees;
    const filtre = recherche !== "" || motif !== "";
    if (conversations.length === 0 && !filtre) return <EtatVide cas="premier" icone={Phone} titre={t(T.aucunAppel)} />;
    const effacer = () => {
        setRecherche("");
        setMotif("");
    };
    return (
        <>
            <div className="mb-3">
                <RechercheAppels recherche={recherche} onRecherche={setRecherche} motif={motif} onMotif={setMotif} motifs={motifs} />
            </div>
            {conversations.length === 0 ? (
                <EtatVide cas="filtre" recherche={motif || recherche} effacer={effacer} />
            ) : (
                <>
                    <Tableau
                        colonnes={[
                            { titre: t(T.quand) },
                            { titre: t(T.agent), secondaire: 3 },
                            { titre: t(T.client) },
                            { titre: t(T.motif) },
                            { titre: t(T.resume), largeur: "w-[30%]", secondaire: 2 },
                            { titre: t(T.issue), secondaire: 4 },
                            { titre: t(T.duree), droite: true, secondaire: 5 },
                            { titre: t(T.jugePar), secondaire: 1 },
                            { titre: t(T.note), droite: true },
                        ]}
                    >
                        {conversations.map((c) => (
                            <Ligne key={c.id} href={`/clients/${c.organization_id}/conversations`}>
                                <Cellule principale>
                                    <DateRelative valeur={c.created_at} />
                                </Cellule>
                                <Cellule>{c.workflow_name ?? ""}</Cellule>
                                <Cellule>{c.organization_nom}</Cellule>
                                <Cellule>{c.motif || "–"}</Cellule>
                                <Cellule className="py-2.5 align-top">
                                    <span data-resume-appel={c.resume_source ?? "aucun"} className="line-clamp-2 text-xs leading-snug">
                                        {c.resume || "–"}
                                    </span>
                                </Cellule>
                                <Cellule>{c.issue || "–"}</Cellule>
                                <Cellule droite className="whitespace-nowrap">{typeof c.duree === "number" ? dureeLisible(c.duree) : "–"}</Cellule>
                                <Cellule>{c.juge_par || "–"}</Cellule>
                                <Cellule droite>
                                    <NoteJuge note={c.note_juge ?? null} />
                                </Cellule>
                            </Ligne>
                        ))}
                    </Tableau>
                    <Pagination decalage={decalage} total={total} aller={setDecalage} />
                </>
            )}
        </>
    );
}

/** Le Chat du Labo : les conversations du builder de tous les clients ouverts (lecture seule ; on les ouvre chez le client). */
export function ChatTousClients() {
    const { t } = useLangue();
    const [q, setQ] = useState("");
    const { charge, decalage, setDecalage, recharger } = usePage<FilsEquipe>((d) =>
        chatDeTousLesClientsApiV1VuesEquipeChatGet({ query: { limit: PAR_PAGE, offset: d } }),
    );
    if (charge.etat === "chargement") return <EtatVide cas="chargement" />;
    if (charge.etat === "acces") return <EtatVide cas="acces" />;
    if (charge.etat === "erreur") return <EtatVide cas="erreur" reessayer={() => void recharger()} />;
    const { fils, total } = charge.donnees;
    if (fils.length === 0) return <EtatVide cas="premier" icone={MessageSquare} titre={t(T.aucunChat)} />;
    const vus = fils.filter((f) => `${f.titre} ${f.organization_nom}`.toLowerCase().includes(q.toLowerCase()));
    return (
        <>
            {/* Clôture D2 (É6) : la forme de la maquette : une recherche, une liste nue (titre, client, marque « Claude Code · prénom » et « En direct »,
                pastille rouge des changements, quand, flèche). Lecture seule : une ligne mène chez le client, où l'on agit. */}
            <div className="relative mb-3 w-full max-w-72">
                <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                <Input value={q} onChange={(e) => setQ(e.target.value)} aria-label={t(T.rechercher)} placeholder={t(T.rechercher)} className="h-9 border-transparent bg-muted/50 pl-8 shadow-none" />
            </div>
            {vus.length === 0 ? (
                <EtatVide cas="filtre" recherche={q} effacer={() => setQ("")} />
            ) : (
                <ul className="divide-y border-y" data-testid="chat-tous-clients">
                    {vus.map((f) => (
                        <li key={f.id}>
                            <Link href={`/clients/${f.organization_id}/chat/${f.id}`} className="flex cursor-pointer items-center gap-3 px-1 py-3.5 hover:bg-muted/40 hover:font-semibold">
                                <span className="min-w-0 flex-1">
                                    <span className="block truncate text-sm font-medium">{f.titre}</span>
                                    <span className="flex items-center gap-3 text-xs font-normal text-muted-foreground">
                                        {f.organization_nom}
                                        {f.genre === "claude_code" && <MarqueClaudeCode par={f.auteur} />}
                                        {f.genre === "claude_code" && f.etat === "en_cours" && <EnDirect />}
                                    </span>
                                </span>
                                {f.changements > 0 && <Pastille n={f.changements} urgent />}
                                <span className="text-xs font-normal text-muted-foreground">
                                    <DateRelative valeur={f.modifie_le as string} />
                                </span>
                                <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                            </Link>
                        </li>
                    ))}
                </ul>
            )}
            <Pagination decalage={decalage} total={total} aller={setDecalage} />
        </>
    );
}
