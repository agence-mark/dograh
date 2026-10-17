"use client";

/**
 * [.mark] Chantier agents-specialises, lot 13 : la carte « Agents de l'appel » de la page d'un appel.
 *
 * Quand un appel a traversé plusieurs agents (ou a été transféré vers un humain), la carte dit :
 * quels agents, le parcours « Agent › étape › étape », chaque passation (de, vers, pourquoi, partie ou
 * refusée et pourquoi) et chaque transfert vers un humain (cible, issue). Un appel d'un agent seul, sans
 * rien de tout cela, ne montre rien : sa page reste celle d'avant. La lecture est dans ``lire-trace.ts``
 * (elle accepte la liste de noms d'étapes d'aujourd'hui et les entrées ``{ agent, etape }`` du lot 7).
 */
import { useEffect, useMemo, useState } from "react";

import { getWorkflowsApiV1WorkflowFetchGet } from "@/client/sdk.gen";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import { type Texte, useLangue } from "../langue/langue";
import { type Contexte, lireLaTrace } from "./lire-trace";

const TEXTES = {
    titre: { en: "Agents of the call", fr: "Agents de l'appel" },
    agents: { en: "Agents", fr: "Agents" },
    parcours: { en: "Path", fr: "Parcours" },
    passations: { en: "Hand-overs", fr: "Passations" },
    de: { en: "From", fr: "De" },
    vers: { en: "To", fr: "Vers" },
    raison: { en: "Reason", fr: "Raison" },
    resultat: { en: "Result", fr: "Résultat" },
    transferts: { en: "Transfers to a person", fr: "Transferts vers un humain" },
    cible: { en: "Target", fr: "Cible" },
    quand: { en: "At", fr: "À" },
    inconnu: { en: "unknown", fr: "inconnu" },
    faite: { en: "done", fr: "faite" },
    refusee: { en: "refused", fr: "refusée" },
    travaux: { en: "Background work", fr: "Travail en arrière-plan" },
    demande: { en: "Request", fr: "Demande" },
    duree: { en: "Duration", fr: "Durée" },
    jetons: { en: "Tokens (in / out)", fr: "Jetons (entrée / sortie)" },
} satisfies Record<string, Texte>;

const MOTIFS_DE_REFUS: Record<string, Texte> = {
    soi_meme: { en: "the target is the agent itself", fr: "la cible est l'agent lui-même" },
    plafond: { en: "ceiling of hand-overs reached", fr: "plafond de passations atteint" },
    meme_agent: { en: "the agent that just handed back, for the same reason", fr: "l'agent qui vient de rendre la main, pour la même raison" },
};

const STATUTS_DE_TRAVAIL: Record<string, Texte> = {
    fait: { en: "done", fr: "fait" },
    vide: { en: "empty answer", fr: "réponse vide" },
    echec: { en: "failed", fr: "échec" },
    delai: { en: "timed out", fr: "délai dépassé" },
    annule: { en: "cancelled", fr: "annulé" },
    en_cours: { en: "running", fr: "en cours" },
};

const ISSUES_DE_TRANSFERT: Record<string, Texte> = {
    decroche: { en: "answered", fr: "décroché" },
    repondeur: { en: "answering machine", fr: "répondeur" },
    sans_reponse: { en: "no answer", fr: "sans réponse" },
    occupe: { en: "busy", fr: "occupé" },
    echec: { en: "failed", fr: "échec" },
};

export const TraceDesAgents = ({ contexte }: { contexte: Contexte }) => {
    const { t } = useLangue();
    const [noms, setNoms] = useState<Map<number, string>>(new Map());
    const aBesoinDesNoms = useMemo(() => lireLaTrace(contexte) !== null, [contexte]);

    // Les identifiants d'agents de la trace se lisent par leurs noms (la liste d'agents de l'organisation).
    useEffect(() => {
        if (!aBesoinDesNoms) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await getWorkflowsApiV1WorkflowFetchGet({ query: { status: "active,archived" } });
                if (annule || !Array.isArray(reponse.data)) return;
                setNoms(new Map(reponse.data.map((a) => [a.id, a.name])));
            } catch {
                // Sans les noms : « #12 », la trace reste lisible.
            }
        })();
        return () => {
            annule = true;
        };
    }, [aBesoinDesNoms]);

    const trace = useMemo(() => lireLaTrace(contexte, noms), [contexte, noms]);
    if (!trace) return null;

    return (
        <Card className="border-border" data-carte="agents-de-l-appel">
            <CardHeader className="pb-3">
                <CardTitle className="text-lg">{t(TEXTES.titre)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
                {trace.agents.length > 0 && (
                    <div className="space-y-1" data-bloc="agents">
                        <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.agents)}</p>
                        <p className="flex flex-wrap gap-1.5">
                            {trace.agents.map((agent) => (
                                <span key={agent} className="rounded-md border bg-muted/40 px-2 py-0.5 text-xs" data-agent-de-l-appel={agent}>
                                    {agent}
                                </span>
                            ))}
                        </p>
                    </div>
                )}

                {(trace.parcoursEcrit.length > 0 || trace.parcours.length > 0) && (
                    <div className="space-y-1" data-bloc="parcours">
                        <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.parcours)}</p>
                        <ul className="space-y-0.5">
                            {trace.parcoursEcrit.length > 0
                                ? trace.parcoursEcrit.map((ligne, i) => (
                                      <li key={i} data-ligne-de-parcours>
                                          {ligne}
                                      </li>
                                  ))
                                : trace.parcours.map((segment, i) => (
                                      <li key={i} data-ligne-de-parcours>
                                          {[segment.agent ?? t(TEXTES.inconnu), ...segment.etapes].join(" › ")}
                                      </li>
                                  ))}
                        </ul>
                    </div>
                )}

                {trace.passations.length > 0 && (
                    <div className="space-y-1" data-bloc="passations">
                        <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.passations)}</p>
                        <table className="w-full">
                            <thead className="text-left text-muted-foreground">
                                <tr>
                                    <th className="py-1 pr-3">{t(TEXTES.de)}</th>
                                    <th className="py-1 pr-3">{t(TEXTES.vers)}</th>
                                    <th className="py-1 pr-3">{t(TEXTES.raison)}</th>
                                    <th className="py-1">{t(TEXTES.resultat)}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trace.passations.map((p, i) => (
                                    <tr key={i} className="border-t border-border" data-passation={p.refusee ? "refusee" : "faite"}>
                                        <td className="py-1 pr-3">{p.de ?? t(TEXTES.inconnu)}</td>
                                        <td className="py-1 pr-3">{p.vers ?? t(TEXTES.inconnu)}</td>
                                        <td className="py-1 pr-3">{p.raison ?? "–"}</td>
                                        <td className="py-1">
                                            {p.refusee
                                                ? `${t(TEXTES.refusee)}${p.motifRefus ? ` (${MOTIFS_DE_REFUS[p.motifRefus] ? t(MOTIFS_DE_REFUS[p.motifRefus]) : p.motifRefus})` : ""}`
                                                : `${t(TEXTES.faite)}${p.issue && p.issue !== "completed" ? ` (${p.issue})` : ""}`}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {trace.transferts.length > 0 && (
                    <div className="space-y-1" data-bloc="transferts-humains">
                        <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.transferts)}</p>
                        <table className="w-full">
                            <thead className="text-left text-muted-foreground">
                                <tr>
                                    <th className="py-1 pr-3">{t(TEXTES.quand)}</th>
                                    <th className="py-1 pr-3">{t(TEXTES.cible)}</th>
                                    <th className="py-1">{t(TEXTES.resultat)}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trace.transferts.map((tr, i) => (
                                    <tr key={i} className="border-t border-border" data-transfert-humain={tr.issue ?? ""}>
                                        <td className="py-1 pr-3">{tr.le ?? "–"}</td>
                                        <td className="py-1 pr-3">{tr.cible ?? "–"}</td>
                                        <td className="py-1">
                                            {tr.issue ? (ISSUES_DE_TRANSFERT[tr.issue] ? t(ISSUES_DE_TRANSFERT[tr.issue]) : tr.issue) : "–"}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {trace.travaux.length > 0 && (
                    <div className="space-y-1" data-bloc="travaux-de-fond">
                        <p className="text-xs font-medium text-muted-foreground">{t(TEXTES.travaux)}</p>
                        <table className="w-full">
                            <thead className="text-left text-muted-foreground">
                                <tr>
                                    <th className="py-1 pr-3">{t(TEXTES.demande)}</th>
                                    <th className="py-1 pr-3">{t(TEXTES.duree)}</th>
                                    <th className="py-1 pr-3">{t(TEXTES.jetons)}</th>
                                    <th className="py-1">{t(TEXTES.resultat)}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {trace.travaux.map((w, i) => (
                                    <tr key={i} className="border-t border-border" data-travail-de-fond={w.statut ?? ""}>
                                        <td className="py-1 pr-3">{w.demande ?? "–"}</td>
                                        <td className="py-1 pr-3">{w.dureeMs === null ? "–" : `${(w.dureeMs / 1000).toFixed(1)} s`}</td>
                                        <td className="py-1 pr-3">{w.jetonsEntree ?? "–"} / {w.jetonsSortie ?? "–"}</td>
                                        <td className="py-1">
                                            {w.statut ? (STATUTS_DE_TRAVAIL[w.statut] ? t(STATUTS_DE_TRAVAIL[w.statut]) : w.statut) : "–"}
                                            {w.resultat ? ` : ${w.resultat}` : ""}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
