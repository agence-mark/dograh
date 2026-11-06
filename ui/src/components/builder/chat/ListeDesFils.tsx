"use client";

/**
 * [.mark] builder partie 2, U5 (E86) : la liste des conversations du builder, à la forme de la maquette (`app/labo/builder`) :
 * une ligne par chat (titre, puis l'agent et la marque « Claude Code · prénom » avec « En direct »), la pastille rouge des changements
 * à valider, « quand », la flèche. Liste nue, jamais dans un cadre. `variante="accueil"` : les trois lignes sous la saisie, sans flèche.
 * K7 : le menu ⋮ de la maquette (« Renommer » en place, « Supprimer » avec confirmation) sur `PUT /builder/fils/{id}/titre` et
 * `DELETE /builder/fils/{id}` ; la liste se relit seule quand un autre onglet ou un collègue renomme ou supprime (direct d'I1, objet
 * `conversations`).
 */
import { ChevronRight, MessageSquare, MoreHorizontal, Pencil, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    getWorkflowsSummaryApiV1WorkflowSummaryGet,
    listerLesFilsApiV1BuilderFilsGet,
    renommerUnFilApiV1BuilderFilsFilIdTitrePut,
    supprimerUnFilApiV1BuilderFilsFilIdDelete,
    type VueFil,
} from "@/client";
import { type Langue, type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications";
import { EnDirect, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { useModifications } from "@/components/mark/sources/useModifications";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Pastille } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

import { useAdressesDuBuilder } from "./adresses";

const T = {
    vide: { en: "No chat", fr: "Aucun chat" },
    rechercher: { en: "Search a chat", fr: "Rechercher un chat" },
    ouvrir: { en: "Open", fr: "Ouvrir" },
    plus: { en: "More", fr: "Plus" },
    renommer: { en: "Rename", fr: "Renommer" },
    supprimer: { en: "Delete", fr: "Supprimer" },
    annuler: { en: "Cancel", fr: "Annuler" },
    nouveauTitre: { en: "New title", fr: "Nouveau titre" },
    titreSuppression: { en: "Delete this chat?", fr: "Supprimer ce chat ?" },
    renomme: { en: "Chat renamed.", fr: "Chat renommé." },
    renommageImpossible: { en: "Could not rename. Try again.", fr: "Renommage impossible. Réessayez." },
    supprime: { en: "Chat deleted.", fr: "Chat supprimé." },
    suppressionImpossible: { en: "Could not delete. Try again.", fr: "Suppression impossible. Réessayez." },
} satisfies Record<string, Texte>;

/** « À l'instant », « Il y a 2 h », « Hier », puis la date : calculé sur la date de dernière modification. */
export function quand(date: unknown, langue: Langue, maintenant = Date.now()): string {
    const ms = typeof date === "string" ? Date.parse(date) : NaN;
    if (Number.isNaN(ms)) return "";
    const minutes = Math.round((maintenant - ms) / 60000);
    const rtf = new Intl.RelativeTimeFormat(langue, { numeric: "auto" });
    const maj = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
    if (minutes < 1) return langue === "fr" ? "À l'instant" : "Just now";
    if (minutes < 60) return maj(rtf.format(-minutes, "minute"));
    if (minutes < 60 * 24) return maj(rtf.format(-Math.round(minutes / 60), "hour"));
    if (minutes < 60 * 24 * 2) return maj(rtf.format(-1, "day"));
    return new Date(ms).toLocaleDateString(langue === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit" });
}

export function ListeDesFils({ limite, workflowId, variante = "page" }: { limite?: number; workflowId?: number; variante?: "page" | "accueil" }) {
    const { t, langue } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const adresses = useAdressesDuBuilder();
    const [fils, setFils] = useState<VueFil[] | null>(null);
    const [agents, setAgents] = useState<Record<number, string>>({});
    const [erreur, setErreur] = useState(false);
    const [q, setQ] = useState("");
    const [edition, setEdition] = useState<number | null>(null);
    const [nomSaisi, setNomSaisi] = useState("");
    const [aSupprimer, setASupprimer] = useState<VueFil | null>(null);

    const lire = useCallback(() => {
        // Les deux lectures partent ensemble ; le nom de l'agent est un plus, jamais bloquant.
        void Promise.all([
            listerLesFilsApiV1BuilderFilsGet({ query: workflowId ? { workflow_id: workflowId } : undefined }),
            getWorkflowsSummaryApiV1WorkflowSummaryGet(),
        ]).then(([f, a]) => {
            if (f.error || !f.data) return setErreur(true);
            setFils(f.data);
            if (Array.isArray(a.data)) setAgents(Object.fromEntries((a.data as { id: number; name: string }[]).map((x) => [x.id, x.name])));
        });
    }, [workflowId]);

    useEffect(() => {
        if (authLoading || !user) return;
        lire();
    }, [authLoading, user, lire]);

    // Direct : un autre onglet ou un collègue renomme ou supprime un chat. On ne relit pas sous les doigts d'une saisie en cours.
    useModifications(variante === "page" ? "conversations" : null, () => {
        if (edition === null) lire();
    });

    const renommer = async (f: VueFil) => {
        const titre = nomSaisi.trim();
        setEdition(null);
        if (!titre || titre === f.titre) return;
        const r = await renommerUnFilApiV1BuilderFilsFilIdTitrePut({ path: { fil_id: f.id }, body: { titre } });
        if (r.error || !r.data) return notifier.echec(T.renommageImpossible, { erreur: r.error });
        const nouveau = r.data.titre;
        setFils((liste) => (liste ?? []).map((x) => (x.id === f.id ? { ...x, titre: nouveau } : x)));
        notifier.succes(T.renomme);
    };

    const supprimer = async (f: VueFil) => {
        setASupprimer(null);
        // suppression-confirmee : la fenêtre « Supprimer ce chat ? » précède `supprimer`.
        const r = await supprimerUnFilApiV1BuilderFilsFilIdDelete({ path: { fil_id: f.id } });
        if (r.error) return notifier.echec(T.suppressionImpossible, { erreur: r.error });
        setFils((liste) => (liste ?? []).filter((x) => x.id !== f.id));
        notifier.succes(T.supprime);
    };

    if (erreur) return <EtatVide cas="erreur" reessayer={() => window.location.reload()} compact={variante === "accueil"} />;
    if (fils === null) return <EtatVide cas="chargement" lignes={3} />;
    if (fils.length === 0) return <EtatVide cas="premier" icone={MessageSquare} titre={t(T.vide)} compact={variante === "accueil"} />;

    const nom = (f: VueFil) => (f.workflow_id ? (agents[f.workflow_id] ?? "") : "");
    const vus = fils.filter((f) => `${f.titre} ${nom(f)}`.toLowerCase().includes(q.toLowerCase())).slice(0, limite);
    const accueil = variante === "accueil";

    return (
        <>
            {!accueil && (
                <div className="relative mb-3 w-full max-w-72">
                    <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                    <Input
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        aria-label={t(T.rechercher)}
                        placeholder={t(T.rechercher)}
                        className="h-9 border-transparent bg-muted/50 pl-8 shadow-none"
                    />
                </div>
            )}
            {vus.length === 0 ? (
                <EtatVide cas="filtre" recherche={q} effacer={() => setQ("")} />
            ) : (
                <ul className={`divide-y ${accueil ? "" : "border-y"}`}>
                    {vus.map((f) =>
                        !accueil && edition === f.id ? (
                            <li key={f.id} className="flex items-center gap-2 px-1 py-2.5">
                                <Input
                                    autoFocus
                                    value={nomSaisi}
                                    maxLength={200}
                                    aria-label={t(T.nouveauTitre)}
                                    onChange={(e) => setNomSaisi(e.target.value)}
                                    onKeyDown={(e) => {
                                        if (e.key === "Enter") void renommer(f);
                                        if (e.key === "Escape") setEdition(null);
                                    }}
                                    className="h-8 flex-1"
                                />
                                <Button size="sm" variant="ghost" onClick={() => setEdition(null)}>
                                    {t(T.annuler)}
                                </Button>
                                <Button size="sm" onClick={() => void renommer(f)}>
                                    {t(T.renommer)}
                                </Button>
                            </li>
                        ) : (
                            <li key={f.id} className={accueil ? "" : "group flex items-center gap-3 px-1 hover:bg-muted/40"}>
                                <Link
                                    href={adresses.fil(f.id)}
                                    className={`flex min-w-0 cursor-pointer items-center gap-3 hover:font-semibold ${accueil ? "px-1 py-3.5 hover:bg-muted/40" : "flex-1 py-3.5"}`}
                                >
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-sm font-medium">{f.titre}</span>
                                        <span className="flex items-center gap-3 text-xs font-normal text-muted-foreground">
                                            {accueil ? (
                                                <>
                                                    {nom(f)}
                                                    {nom(f) && " · "}
                                                    {quand(f.modifie_le, langue)}
                                                </>
                                            ) : (
                                                nom(f)
                                            )}
                                            {f.genre === "claude_code" && <MarqueClaudeCode par={f.auteur} />}
                                            {f.genre === "claude_code" && f.etat === "en_cours" && <EnDirect />}
                                        </span>
                                    </span>
                                    {f.changements > 0 && <Pastille n={f.changements} urgent />}
                                    {!accueil && <span className="text-xs font-normal text-muted-foreground">{quand(f.modifie_le, langue)}</span>}
                                </Link>
                                {!accueil && (
                                    <>
                                        <DropdownMenu>
                                            <DropdownMenuTrigger asChild>
                                                <Button
                                                    variant="ghost"
                                                    size="icon"
                                                    className="size-7 cursor-pointer opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100"
                                                    aria-label={t(T.plus)}
                                                >
                                                    <MoreHorizontal className="size-4" aria-hidden />
                                                </Button>
                                            </DropdownMenuTrigger>
                                            <DropdownMenuContent align="end">
                                                <DropdownMenuItem
                                                    className="cursor-pointer"
                                                    onSelect={() => {
                                                        setEdition(f.id);
                                                        setNomSaisi(f.titre);
                                                    }}
                                                >
                                                    <Pencil className="size-4" aria-hidden /> {t(T.renommer)}
                                                </DropdownMenuItem>
                                                <DropdownMenuItem className="cursor-pointer text-destructive focus:text-destructive" onSelect={() => setASupprimer(f)}>
                                                    <Trash2 className="size-4" aria-hidden /> {t(T.supprimer)}
                                                </DropdownMenuItem>
                                            </DropdownMenuContent>
                                        </DropdownMenu>
                                        <Link href={adresses.fil(f.id)} aria-label={t(T.ouvrir)} className="cursor-pointer">
                                            <ChevronRight className="size-4 text-muted-foreground" aria-hidden />
                                        </Link>
                                    </>
                                )}
                            </li>
                        ),
                    )}
                </ul>
            )}
            <Dialog centree open={aSupprimer !== null} onOpenChange={(ouverte) => !ouverte && setASupprimer(null)}>
                <DialogContent className="sm:max-w-md">
                    <DialogHeader>
                        <DialogTitle>{t(T.titreSuppression)}</DialogTitle>
                        <DialogDescription>
                            {langue === "fr"
                                ? `« ${aSupprimer?.titre ?? ""} » et son historique sont supprimés. Les changements déjà acceptés restent dans le brouillon de l'agent.`
                                : `"${aSupprimer?.titre ?? ""}" and its history are deleted. Changes already accepted stay in the agent's draft.`}
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setASupprimer(null)}>
                            {t(T.annuler)}
                        </Button>
                        <Button variant="destructive" onClick={() => aSupprimer && void supprimer(aSupprimer)}>
                            {t(T.supprimer)}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
