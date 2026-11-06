"use client";

/**
 * [.mark] U3 sexies point 5 (E74) : l'activité d'un outil, calculée à la volée sur les appels des 30 derniers jours.
 * Exécutions, réussite, durée médiane, échecs, dernières exécutions paginées côté serveur (25), agents et étapes qui
 * l'utilisent. Rien n'est stocké ; un outil sans appel dit « Aucune exécution ».
 */
import { useEffect, useState } from "react";

import { statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet } from "@/client/sdk.gen";
import type { StatistiquesOutil } from "@/client/types.gen";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { useLangue } from "../langue/langue";
import { Section } from "../studio/fenetre-onglets";
import { Info } from "../studio/marques";
import { BarrePagination } from "../studio/pagination";
import { Cellule, Ligne, Tableau } from "../studio/tableau";

export function OngletActivite({ toolUuid }: { toolUuid: string }) {
    const { t } = useLangue();
    const [page, setPage] = useState(0);
    const [stats, setStats] = useState<StatistiquesOutil | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    useEffect(() => {
        let actif = true;
        void statistiquesDUnOutilApiV1ToolsToolUuidStatistiquesGet({ path: { tool_uuid: toolUuid }, query: { page } }).then((r) => {
            if (!actif) return;
            if (r.error || !r.data) return setErreur(echecAffiche(r.error, ECHECS.outilStatistiques));
            setErreur(null);
            setStats(r.data);
        });
        return () => {
            actif = false;
        };
    }, [toolUuid, page]);

    if (erreur) return <p className="text-sm text-destructive">{erreur}</p>;
    if (!stats) return <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>;
    if (stats.total_executions === 0) {
        return <p className="py-8 text-center text-sm text-muted-foreground">{t({ en: "No run", fr: "Aucune exécution" })}</p>;
    }
    const chiffre = (libelle: string, v: string) => (
        <div>
            <p className="text-xs text-muted-foreground">{libelle}</p>
            <p className="text-lg font-semibold tabular-nums">{v}</p>
        </div>
    );
    return (
        <div>
            <div className="flex flex-wrap gap-10 pb-2">
                {chiffre(t({ en: "Runs", fr: "Exécutions" }), String(stats.executions))}
                {chiffre(t({ en: "Success", fr: "Réussite" }), stats.reussite === null ? "–" : `${stats.reussite} %`)}
                {chiffre(t({ en: "Median duration", fr: "Durée médiane" }), stats.duree_mediane_ms === null ? "–" : `${stats.duree_mediane_ms} ms`)}
                {chiffre(t({ en: "Failures", fr: "Échecs" }), String(stats.echecs))}
                <Info>{t({ en: `Over the last ${stats.jours} days, computed on the calls.`, fr: `Sur les ${stats.jours} derniers jours, calculées à la volée sur les appels.` })}</Info>
            </div>
            <Section titre={t({ en: "Latest runs", fr: "Dernières exécutions" })}>
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Date", fr: "Date" }) },
                        { titre: t({ en: "Call", fr: "Appel" }) },
                        { titre: t({ en: "Step", fr: "Étape" }) },
                        { titre: t({ en: "Result", fr: "Résultat" }) },
                        { titre: t({ en: "Duration", fr: "Durée" }), droite: true },
                    ]}
                >
                    {stats.dernieres_executions.map((e) => (
                        <Ligne key={`${e.run_id}-${e.date}-${e.etape}-${e.duree_ms}`} href={`/workflow/${e.workflow_id}/run/${e.run_id}`}>
                            <Cellule principale>{e.date ? new Date(e.date).toLocaleString() : "–"}</Cellule>
                            <Cellule>#{e.run_id}</Cellule>
                            <Cellule>{e.etape ?? "–"}</Cellule>
                            <Cellule>{e.reussie ? t({ en: "Succeeded", fr: "Réussie" }) : t({ en: "Failed", fr: "En échec" })}</Cellule>
                            <Cellule droite>{e.duree_ms === null ? "–" : `${e.duree_ms} ms`}</Cellule>
                        </Ligne>
                    ))}
                </Tableau>
                <BarrePagination total={stats.total_executions} page={page} parPage={stats.par_page} changerPage={setPage} />
            </Section>
            <Section titre={t({ en: "Agents using it", fr: "Agents qui l'utilisent" })}>
                {stats.agents.length === 0 ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "No agent.", fr: "Aucun agent." })}</p>
                ) : (
                    <ul className="divide-y text-sm">
                        {stats.agents.map((a) => (
                            <li key={a.agent_id} className="py-2">
                                <span className="font-medium">{a.agent}</span>
                                <span className="text-muted-foreground"> · {a.etapes.join(", ")}</span>
                            </li>
                        ))}
                    </ul>
                )}
            </Section>
        </div>
    );
}
