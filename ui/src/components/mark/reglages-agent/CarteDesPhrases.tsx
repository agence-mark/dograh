"use client";

/**
 * [.mark] Chantier fiabilite-orchestration, lot 4 ter (F16, F24): the map of the sentences said by the code,
 * at the top of the theme Phrases. For each cause: when, where, the text in force, where it comes from (step,
 * agent, main agent, default), its delay, on or off (off: what happens instead), the link to its setting and
 * its last trigger in recent calls. Seen from the main agent: the whole group. The sentences written in the
 * graph (greeting, step changes, fixed endings) and on actions are shown read only, with a link.
 *
 * Read by `GET /api/v1/workflow/{id}/phrases/carte` (`api/services/phrases/carte.py`), which resolves the
 * rules exactly as the call does.
 */
import Link from "next/link";
import { useEffect, useState } from "react";

import { client } from "@/client/client.gen";
import { useAuth } from "@/lib/auth";

import { Intertitre } from "../ecran/Intertitre";
import { type Texte, useLangue } from "../langue/langue";

interface Dernier {
    run: number | null;
    moment: string | null;
    texte: string | null;
}

interface MotifDeLaCarte {
    motif: string;
    famille: string;
    libelle: Texte;
    quand: Texte;
    eteinte: Texte;
    a_un_delai: boolean;
    variantes: string[];
    delai_s: number | null;
    active: boolean;
    niveau: string | null;
    etapes: Array<{ etape: string; variantes: string[]; delai_s: number | null; active: boolean; dernier: Dernier | null }>;
    dernier: Dernier | null;
}

export interface Carte {
    agents: Array<{
        id: number;
        nom: string;
        est_principal: boolean;
        motifs: MotifDeLaCarte[];
        lecture: Array<{ nature: string; endroit: string; texte: string }>;
    }>;
    actions: Array<{ fichier: string; description: string }>;
}

const NIVEAUX: Record<string, Texte> = {
    etape: { en: "the step", fr: "l'étape" },
    agent: { en: "this agent", fr: "cet agent" },
    principal: { en: "the main agent", fr: "le principal" },
    defaut: { en: "default", fr: "défaut" },
};

const NATURES: Record<string, Texte> = {
    accueil: { en: "Greeting", fr: "Accueil" },
    porte: { en: "Step change", fr: "Porte" },
    fin_figee: { en: "Fixed ending", fr: "Fin figée" },
};

const TEXTES = {
    titre: { en: "Map", fr: "Carte" },
    description: {
        en: "What the code says by itself, where, with which text and from where; the last time it was said.",
        fr: "Ce que le code dit de lui-même, où, avec quel texte et d'où il vient ; la dernière fois qu'il l'a dit.",
    },
    chargement: { en: "Loading the map…", fr: "Chargement de la carte…" },
    erreur: { en: "The map could not be read.", fr: "La carte n'a pas pu être lue." },
    motif: { en: "Cause", fr: "Motif" },
    texte: { en: "Text in force", fr: "Texte en vigueur" },
    origine: { en: "From", fr: "D'où" },
    delai: { en: "Delay", fr: "Délai" },
    etat: { en: "State", fr: "État" },
    dernier: { en: "Last said", fr: "Dernière fois" },
    allumee: { en: "on", fr: "allumée" },
    eteinte: { en: "off", fr: "éteinte" },
    jamais: { en: "not in recent calls", fr: "pas dans les derniers appels" },
    reglage: { en: "Setting", fr: "Réglage" },
    etape: { en: "step", fr: "étape" },
    graphe: { en: "Written in the graph (read only)", fr: "Écrites dans le graphe (en lecture)" },
    ouvrirGraphe: { en: "Open the graph", fr: "Ouvrir le graphe" },
    actions: { en: "Said by an action when it runs (read only, set on the action)", fr: "Dites par une action quand elle s'exécute (en lecture, réglées sur l'action)" },
} satisfies Record<string, Texte>;

export const CarteDesPhrases = ({ workflowId }: { workflowId: number }) => {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [carte, setCarte] = useState<Carte | null>(null);
    const [erreur, setErreur] = useState(false);

    useEffect(() => {
        if (loading || !user) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await client.get<{ 200: Carte }, unknown, false>({
                    url: "/api/v1/workflow/{workflow_id}/phrases/carte",
                    path: { workflow_id: workflowId },
                });
                if (annule) return;
                if (reponse.error || !reponse.data) setErreur(true);
                else setCarte(reponse.data as Carte);
            } catch {
                if (!annule) setErreur(true);
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId, loading, user]);

    const dernier = (d: Dernier | null, agentId: number) =>
        d && d.run != null ? (
            <Link href={`/workflow/${agentId}/run/${d.run}`} className="underline">
                {d.moment ? d.moment.slice(0, 16) : `#${d.run}`}
            </Link>
        ) : (
            <span className="text-muted-foreground">{t(TEXTES.jamais)}</span>
        );

    return (
        <Intertitre id="phrases-carte" titre={TEXTES.titre} description={TEXTES.description}>
            {!carte && !erreur && <p className="text-xs text-muted-foreground">{t(TEXTES.chargement)}</p>}
            {erreur && <p className="text-xs text-destructive" data-note="carte-illisible">{t(TEXTES.erreur)}</p>}
            {carte?.agents.map((agent) => (
                <div key={agent.id} className="space-y-2" data-carte-agent={agent.id}>
                    {carte.agents.length > 1 && (
                        <p className="text-sm font-medium">
                            <Link href={`/workflow/${agent.id}/settings`} className="underline">
                                {agent.nom}
                            </Link>
                        </p>
                    )}
                    <div className="overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead className="text-left text-muted-foreground">
                                <tr>
                                    <th className="py-1 pr-2">{t(TEXTES.motif)}</th>
                                    <th className="py-1 pr-2">{t(TEXTES.texte)}</th>
                                    <th className="py-1 pr-2">{t(TEXTES.origine)}</th>
                                    <th className="py-1 pr-2">{t(TEXTES.delai)}</th>
                                    <th className="py-1 pr-2">{t(TEXTES.etat)}</th>
                                    <th className="py-1">{t(TEXTES.dernier)}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {agent.motifs.flatMap((m) => [
                                    <tr key={m.motif} className="border-t align-top" data-carte-motif={m.motif}>
                                        <td className="py-1 pr-2" title={t(m.quand)}>
                                            {agent.id === workflowId ? (
                                                <a href={`#phrases-${m.famille}`} className="underline">
                                                    {t(m.libelle)}
                                                </a>
                                            ) : (
                                                <Link href={`/workflow/${agent.id}/settings`} className="underline">
                                                    {t(m.libelle)}
                                                </Link>
                                            )}
                                            <div className="text-muted-foreground">{t(m.quand)}</div>
                                        </td>
                                        <td className="py-1 pr-2">{m.variantes.length ? m.variantes.map((v) => `« ${v} »`).join(" / ") : "–"}</td>
                                        <td className="py-1 pr-2">{m.niveau ? t(NIVEAUX[m.niveau] ?? { en: m.niveau, fr: m.niveau }) : "–"}</td>
                                        <td className="py-1 pr-2">{m.a_un_delai && m.delai_s != null ? `${m.delai_s} s` : "–"}</td>
                                        <td className="py-1 pr-2">
                                            {m.active ? t(TEXTES.allumee) : (
                                                <span title={t(m.eteinte)}>
                                                    {t(TEXTES.eteinte)}
                                                    <span className="block text-muted-foreground">{t(m.eteinte)}</span>
                                                </span>
                                            )}
                                        </td>
                                        <td className="py-1">{dernier(m.dernier, agent.id)}</td>
                                    </tr>,
                                    ...m.etapes.map((e) => (
                                        <tr key={`${m.motif}-${e.etape}`} className="align-top text-muted-foreground" data-carte-etape={`${m.motif}-${e.etape}`}>
                                            <td className="py-1 pl-4 pr-2">{`${t(TEXTES.etape)} : ${e.etape}`}</td>
                                            <td className="py-1 pr-2">{e.variantes.map((v) => `« ${v} »`).join(" / ") || "–"}</td>
                                            <td className="py-1 pr-2">{t(NIVEAUX.etape)}</td>
                                            <td className="py-1 pr-2">{m.a_un_delai && e.delai_s != null ? `${e.delai_s} s` : "–"}</td>
                                            <td className="py-1 pr-2">{e.active ? t(TEXTES.allumee) : t(TEXTES.eteinte)}</td>
                                            <td className="py-1">{dernier(e.dernier, agent.id)}</td>
                                        </tr>
                                    )),
                                ])}
                            </tbody>
                        </table>
                    </div>
                    {agent.lecture.length > 0 && (
                        <div className="space-y-1" data-carte-lecture={agent.id}>
                            <p className="text-xs font-medium text-muted-foreground">
                                {t(TEXTES.graphe)} ·{" "}
                                <Link href={`/workflow/${agent.id}`} className="underline">
                                    {t(TEXTES.ouvrirGraphe)}
                                </Link>
                            </p>
                            <ul className="space-y-0.5 text-xs">
                                {agent.lecture.map((ligne, i) => (
                                    <li key={i}>
                                        {t(NATURES[ligne.nature] ?? { en: ligne.nature, fr: ligne.nature })} · {ligne.endroit} : « {ligne.texte} »
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                </div>
            ))}
            {carte && carte.actions.length > 0 && (
                <div className="space-y-1" data-carte-actions>
                    <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.actions)}</p>
                    <ul className="list-disc space-y-0.5 pl-5 text-xs">
                        {carte.actions.map((a, i) => (
                            <li key={i}>{a.description}</li>
                        ))}
                    </ul>
                </div>
            )}
        </Intertitre>
    );
};
