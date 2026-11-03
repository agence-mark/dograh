"use client";

/**
 * [.mark] builder partie 2, U5 (E86) : la liste des conversations du builder, à la forme de la maquette (`app/labo/builder`) :
 * une ligne par chat (titre, puis l'agent et la marque « Claude Code · prénom » avec « En direct »), la pastille rouge des changements
 * à valider, « quand », la flèche. Liste nue, jamais dans un cadre. `variante="accueil"` : les trois lignes sous la saisie, sans flèche.
 * « Renommer » et « Supprimer » (menu ⋮ de la maquette) attendent leurs routes : `18-a-exposer-a-la-fin.md`.
 */
import { ChevronRight, MessageSquare, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { getWorkflowsSummaryApiV1WorkflowSummaryGet, listerLesFilsApiV1BuilderFilsGet, type VueFil } from "@/client";
import { type Langue, type Texte, useLangue } from "@/components/mark/langue/langue";
import { EnDirect, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Pastille } from "@/components/mark/studio/marques";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";

import { useAdressesDuBuilder } from "./adresses";

const T = {
    vide: { en: "No chat", fr: "Aucun chat" },
    rechercher: { en: "Search a chat", fr: "Rechercher un chat" },
    ouvrir: { en: "Open", fr: "Ouvrir" },
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

    useEffect(() => {
        if (authLoading || !user) return;
        // Les deux lectures partent ensemble ; le nom de l'agent est un plus, jamais bloquant.
        void Promise.all([
            listerLesFilsApiV1BuilderFilsGet({ query: workflowId ? { workflow_id: workflowId } : undefined }),
            getWorkflowsSummaryApiV1WorkflowSummaryGet(),
        ]).then(([f, a]) => {
            if (f.error || !f.data) return setErreur(true);
            setFils(f.data);
            if (Array.isArray(a.data)) setAgents(Object.fromEntries((a.data as { id: number; name: string }[]).map((x) => [x.id, x.name])));
        });
    }, [authLoading, user, workflowId]);

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
                    {vus.map((f) => (
                        <li key={f.id}>
                            <Link href={adresses.fil(f.id)} className="flex min-w-0 cursor-pointer items-center gap-3 px-1 py-3.5 hover:bg-muted/40 hover:font-semibold">
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
                                {!accueil && <ChevronRight className="size-4 text-muted-foreground" aria-label={t(T.ouvrir)} />}
                            </Link>
                        </li>
                    ))}
                </ul>
            )}
        </>
    );
}
