"use client";

/**
 * [.mark] The report of the simulated caller's series (chantier langwatch-et-fenetre-du-run, lot 3,
 * L18): the summary of a series (scenarios passed, criteria met, median latency and worst turn,
 * incidents, cost), the comparison of two series side by side, and the export (CSV, one line per
 * call). Each call links to its run window.
 */
import { Download } from "lucide-react";
import { useEffect, useState } from "react";

import { getRapportSerieApiV1AppelSimuleSeriesSerieIdGet, getSeriesSimuleesApiV1AppelSimuleSeriesGet } from "@/client";
import type { RapportSerie, SerieSimulee } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

type Resultat = {
    success?: boolean;
    passed_criteria?: string[];
    failed_criteria?: string[];
    worst_silence_secs?: number | null;
    median_silence_secs?: number | null;
    incidents?: number;
    /** Rating of each expected field of the record, computed by the code (`fiche_attendue`). */
    fiche?: Record<string, string>;
};

/** The four ratings of an expected field, best first. */
export const RANGS_FICHE: { rang: string; libelle: Texte }[] = [
    { rang: "juste_sur", libelle: { en: "right and sure", fr: "juste et sûr" } },
    { rang: "juste_a_confirmer", libelle: { en: "right, to confirm", fr: "juste, à confirmer" } },
    { rang: "vide", libelle: { en: "empty", fr: "vide" } },
    { rang: "faux", libelle: { en: "wrong", fr: "faux" } },
];

export const ETATS_SERIE: Record<NonNullable<SerieSimulee["etat"]>, Texte> = {
    en_cours: { en: "playing", fr: "en cours" },
    terminee: { en: "finished", fr: "terminée" },
    arretee_plafond: { en: "stopped at the cap", fr: "arrêtée au plafond" },
    arretee: { en: "stopped", fr: "arrêtée" },
    echec: { en: "failed", fr: "en échec" },
};

const mediane = (valeurs: number[]): number | null => {
    if (!valeurs.length) return null;
    const triees = [...valeurs].sort((a, b) => a - b);
    return triees[Math.floor((triees.length - 1) / 2)];
};

/** The summary of a series, computed from its calls' saved verdicts. */
export const bilanDeSerie = (rapport: RapportSerie) => {
    const resultats = rapport.appels
        .map((a) => a.resultat as Resultat | null | undefined)
        .filter((r): r is Resultat => Boolean(r));
    const criteresOk = resultats.reduce((n, r) => n + (r.passed_criteria?.length ?? 0), 0);
    const criteres = resultats.reduce(
        (n, r) => n + (r.passed_criteria?.length ?? 0) + (r.failed_criteria?.length ?? 0),
        0,
    );
    const pires = resultats.map((r) => r.worst_silence_secs).filter((v): v is number => typeof v === "number");
    return {
        joues: resultats.length,
        reussis: resultats.filter((r) => r.success).length,
        criteresOk,
        criteres,
        medianeLatence: mediane(
            resultats.map((r) => r.median_silence_secs).filter((v): v is number => typeof v === "number"),
        ),
        pireTour: pires.length ? Math.max(...pires) : null,
        incidents: resultats.reduce((n, r) => n + (r.incidents ?? 0), 0),
        fiche: Object.fromEntries(
            RANGS_FICHE.map(({ rang }) => [
                rang,
                resultats.reduce((n, r) => n + Object.values(r.fiche ?? {}).filter((v) => v === rang).length, 0),
            ]),
        ) as Record<string, number>,
        cout: rapport.serie.cout ?? 0,
        coutPartiel: Boolean(rapport.serie.cout_partiel),
        devise: rapport.serie.devise ?? "USD",
    };
};

const csv = (valeur: unknown) => `"${String(valeur ?? "").replaceAll('"', '""')}"`;

export const exportCsv = (rapport: RapportSerie): string => {
    const lignes = [
        ["series", "scenario", "run", "state", "passed", "criteria_met", "criteria_failed", "worst_turn_s", "median_s", "incidents", "record", "cost"],
        ...rapport.appels.map((a) => {
            const r = (a.resultat ?? {}) as Resultat;
            return [
                rapport.serie.id,
                a.scenario_nom,
                a.run_id,
                a.etat,
                a.reussi,
                (r.passed_criteria ?? []).join(" | "),
                (r.failed_criteria ?? []).join(" | "),
                r.worst_silence_secs,
                r.median_silence_secs,
                r.incidents,
                Object.entries(r.fiche ?? {})
                    .map(([champ, rang]) => `${champ}:${rang}`)
                    .join(" | "),
                a.cout,
            ];
        }),
    ];
    return lignes.map((l) => l.map(csv).join(",")).join("\n");
};

const telecharger = (nom: string, contenu: string) => {
    const url = URL.createObjectURL(new Blob([contenu], { type: "text/csv;charset=utf-8" }));
    const lien = document.createElement("a");
    lien.href = url;
    lien.download = nom;
    lien.click();
    URL.revokeObjectURL(url);
};

const secondes = (v: number | null) => (v === null ? "—" : `${v.toFixed(2)} s`);

function ColonneRapport({ rapport, workflowId }: { rapport: RapportSerie; workflowId: number }) {
    const { t } = useLangue();
    const b = bilanDeSerie(rapport);
    const etat = rapport.serie.etat ?? "en_cours";
    return (
        <div className="space-y-2 text-sm" data-testid="rapport-serie">
            <p className="font-medium">
                {new Date(rapport.serie.lancee_le).toLocaleString()} · {t(ETATS_SERIE[etat])}
            </p>
            <ul className="space-y-1 text-muted-foreground" data-testid="bilan-serie">
                <li>
                    {t({
                        en: `Scenarios passed: ${b.reussis} / ${b.joues}`,
                        fr: `Scénarios réussis : ${b.reussis} / ${b.joues}`,
                    })}
                </li>
                <li>
                    {t({ en: `Criteria met: ${b.criteresOk} / ${b.criteres}`, fr: `Critères tenus : ${b.criteresOk} / ${b.criteres}` })}
                </li>
                <li>
                    {t({
                        en: `Median latency ${secondes(b.medianeLatence)} · worst turn ${secondes(b.pireTour)}`,
                        fr: `Latence médiane ${secondes(b.medianeLatence)} · pire tour ${secondes(b.pireTour)}`,
                    })}
                </li>
                <li>{t({ en: `Incidents: ${b.incidents}`, fr: `Incidents : ${b.incidents}` })}</li>
                {RANGS_FICHE.some(({ rang }) => b.fiche[rang] > 0) ? (
                    <li data-testid="bilan-fiche">
                        {t({ en: "Expected record: ", fr: "Fiche attendue : " })}
                        {RANGS_FICHE.map(({ rang, libelle }) => `${b.fiche[rang]} ${t(libelle)}`).join(" · ")}
                    </li>
                ) : null}
                <li>
                    {t({
                        en: `Cost ${b.cout} ${b.devise}${b.coutPartiel ? " (partial)" : ""} · cap ${rapport.serie.plafond}`,
                        fr: `Coût ${b.cout} ${b.devise}${b.coutPartiel ? " (partiel)" : ""} · plafond ${rapport.serie.plafond}`,
                    })}
                </li>
                {rapport.serie.raison ? <li>{rapport.serie.raison}</li> : null}
            </ul>
            <ul className="space-y-1">
                {rapport.appels.map((a, i) => (
                    <li key={`${a.scenario_id}-${i}`} className="flex items-center gap-2">
                        <span>{a.reussi === true ? "✓" : a.reussi === false ? "✗" : "·"}</span>
                        <span className="flex-1 truncate">{a.scenario_nom}</span>
                        {a.run_id ? (
                            <a
                                className="text-xs underline"
                                href={`/workflow/${workflowId}/run/${a.run_id}`}
                                target="_blank"
                                rel="noreferrer"
                            >
                                {t({ en: `run ${a.run_id}`, fr: `run ${a.run_id}` })}
                            </a>
                        ) : null}
                    </li>
                ))}
            </ul>
            <Button
                variant="outline"
                size="sm"
                onClick={() => telecharger(`series-${rapport.serie.id}.csv`, exportCsv(rapport))}
            >
                <Download className="mr-1 h-4 w-4" />
                {t({ en: "Export (CSV)", fr: "Exporter (CSV)" })}
            </Button>
        </div>
    );
}

export function ModaleRapportSeries({
    workflowId,
    ouverte,
    onFermer,
}: {
    workflowId: number;
    ouverte: boolean;
    onFermer: () => void;
}) {
    const { t } = useLangue();
    const [series, setSeries] = useState<SerieSimulee[] | null>(null);
    const [choix, setChoix] = useState<[string, string]>(["", ""]);
    const [rapports, setRapports] = useState<Record<string, RapportSerie>>({});
    const [erreur, setErreur] = useState<string | null>(null);

    useEffect(() => {
        if (!ouverte) return;
        let annule = false;
        setErreur(null);
        setSeries(null);
        (async () => {
            const reponse = await getSeriesSimuleesApiV1AppelSimuleSeriesGet({ query: { workflow_id: workflowId } });
            if (annule) return;
            if (reponse.error) {
                setErreur(detailFromError(reponse.error, "Series unreadable"));
                return;
            }
            const liste = (reponse.data as SerieSimulee[]) ?? [];
            setSeries(liste);
            setChoix([liste[0]?.id ?? "", ""]);
        })();
        return () => {
            annule = true;
        };
    }, [ouverte, workflowId]);

    useEffect(() => {
        const manquants = choix.filter((id) => id && !rapports[id]);
        if (!manquants.length) return;
        let annule = false;
        (async () => {
            for (const id of manquants) {
                const reponse = await getRapportSerieApiV1AppelSimuleSeriesSerieIdGet({ path: { serie_id: id } });
                if (annule) return;
                if (reponse.error) {
                    setErreur(detailFromError(reponse.error, "Series report unreadable"));
                    return;
                }
                setRapports((avant) => ({ ...avant, [id]: reponse.data as RapportSerie }));
            }
        })();
        return () => {
            annule = true;
        };
    }, [choix, rapports]);

    const libelle = (s: SerieSimulee) =>
        `${new Date(s.lancee_le).toLocaleString()} · ${s.appels?.length ?? 0} · ${t(ETATS_SERIE[s.etat ?? "en_cours"])}`;

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer())}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-5xl" data-testid="modale-rapport-series">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Series report", fr: "Rapport des séries" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Pick a series to read its summary; pick a second one to compare them side by side.",
                            fr: "Choisissez une série pour lire son bilan ; une seconde pour les comparer côte à côte.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert">
                        {erreur}
                    </p>
                )}
                {series === null && !erreur ? (
                    <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : series && series.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                        {t({ en: "No series played yet for this agent.", fr: "Aucune série jouée pour cet agent." })}
                    </p>
                ) : series ? (
                    <div className="space-y-4">
                        <div className="grid gap-2 sm:grid-cols-2">
                            {([0, 1] as const).map((k) => (
                                <select
                                    key={k}
                                    className="rounded border border-border bg-background px-2 py-1 text-sm"
                                    value={choix[k]}
                                    onChange={(e) =>
                                        setChoix((avant) => (k === 0 ? [e.target.value, avant[1]] : [avant[0], e.target.value]))
                                    }
                                    aria-label={
                                        k === 0
                                            ? t({ en: "Series", fr: "Série" })
                                            : t({ en: "Compare with", fr: "Comparer avec" })
                                    }
                                >
                                    <option value="">
                                        {k === 0
                                            ? t({ en: "— a series —", fr: "— une série —" })
                                            : t({ en: "— compare with (optional) —", fr: "— comparer avec (facultatif) —" })}
                                    </option>
                                    {series.map((s) => (
                                        <option key={s.id} value={s.id}>
                                            {libelle(s)}
                                        </option>
                                    ))}
                                </select>
                            ))}
                        </div>
                        <div className="grid gap-6 sm:grid-cols-2">
                            {choix.map((id, k) =>
                                id && rapports[id] ? (
                                    <ColonneRapport key={`${k}-${id}`} rapport={rapports[id]} workflowId={workflowId} />
                                ) : (
                                    <div key={`${k}-vide`} />
                                ),
                            )}
                        </div>
                    </div>
                ) : null}
            </DialogContent>
        </Dialog>
    );
}
