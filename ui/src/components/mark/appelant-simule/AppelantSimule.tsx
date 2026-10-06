"use client";

/**
 * [.mark] The « Simulated caller » tab of « Test Agent » (chantier langwatch-et-fenetre-du-run, lot 3,
 * L11, L13, L18, Q3).
 *
 * Pick scenarios of this agent, read the estimated cost and the cap, run them as a series (played
 * one by one by default), follow each call's state and verdict, stop the series. Each call is a
 * run marked « simulated », with its run window. The scenarios, the settings and the report are
 * modals (L18).
 *
 * A call's transcript and verdict appear when it ends: Dograh writes a run's events at the end of
 * the call, so they cannot be read during it.
 */
import { FileBarChart, ListChecks, Play, Settings, Square } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    arreterSerieSimuleeApiV1AppelSimuleSeriesSerieIdArreterPost,
    getRapportSerieApiV1AppelSimuleSeriesSerieIdGet,
    getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet,
    getScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosGet,
    getSeriesSimuleesApiV1AppelSimuleSeriesGet,
    lancerSerieSimuleeApiV1AppelSimuleAgentsWorkflowIdSeriesPost,
} from "@/client";
import type { RapportSerie, ReglagesAppelantSimule, ScenarioSimule, SerieSimulee } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";
import { DirectAppelSimule } from "./DirectAppelSimule";
import { ETATS_SERIE, ModaleRapportSeries } from "./ModaleRapportSeries";
import { ModaleReglagesAppelantSimule } from "./ModaleReglagesAppelantSimule";
import { ModaleScenarios } from "./ModaleScenarios";

export const TITRE_ONGLET: Texte = { en: "Simulated caller", fr: "Appelant simulé" };
const INTERVALLE_MS = 4000;

const ETATS_APPEL: Record<string, Texte> = {
    a_jouer: { en: "to play", fr: "à jouer" },
    en_cours: { en: "on the line", fr: "en ligne" },
    joue: { en: "played", fr: "joué" },
    echec: { en: "failed", fr: "en échec" },
};

/** Mean cost of this agent's simulated calls already played × calls; null before the first one
 * (the same estimate as the server's). */
export const estimation = (series: SerieSimulee[], nombre: number): number | null => {
    const couts = series.flatMap((s) => (s.appels ?? []).map((a) => a.cout)).filter((c): c is number => typeof c === "number");
    if (!couts.length) return null;
    return Math.round((couts.reduce((a, b) => a + b, 0) / couts.length) * nombre * 10000) / 10000;
};

export function AppelantSimule({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [scenarios, setScenarios] = useState<ScenarioSimule[] | null>(null);
    const [reglages, setReglages] = useState<ReglagesAppelantSimule | null>(null);
    const [series, setSeries] = useState<SerieSimulee[]>([]);
    const [choisis, setChoisis] = useState<Set<string>>(new Set());
    const [rapport, setRapport] = useState<RapportSerie | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [modale, setModale] = useState<"scenarios" | "reglages" | "rapport" | null>(null);
    const suivie = useRef<string | null>(null);

    const charger = useCallback(async () => {
        const [s, r, l] = await Promise.all([
            getScenariosSimulesApiV1AppelSimuleAgentsWorkflowIdScenariosGet({ path: { workflow_id: workflowId } }),
            getReglagesAppelantSimuleApiV1AppelSimuleReglagesGet(),
            getSeriesSimuleesApiV1AppelSimuleSeriesGet({ query: { workflow_id: workflowId } }),
        ]);
        const faute = s.error ?? r.error ?? l.error;
        if (faute) {
            setErreur(detailFromError(faute, "Simulated caller unavailable"));
            return;
        }
        setScenarios((s.data as ScenarioSimule[]) ?? []);
        setReglages(r.data as ReglagesAppelantSimule);
        const liste = (l.data as SerieSimulee[]) ?? [];
        setSeries(liste);
        if (liste[0]) suivie.current = liste[0].id;
    }, [workflowId]);

    useEffect(() => {
        void charger();
    }, [charger]);

    const lireRapport = useCallback(async () => {
        if (!suivie.current) return;
        const reponse = await getRapportSerieApiV1AppelSimuleSeriesSerieIdGet({ path: { serie_id: suivie.current } });
        if (!reponse.error) setRapport(reponse.data as RapportSerie);
    }, []);

    useEffect(() => {
        void lireRapport();
    }, [series, lireRapport]);

    const enJeu = rapport?.serie.etat === "en_cours";
    const appelSuivi =
        rapport?.appels.find((a) => a.etat === "en_cours" && a.run_id) ??
        [...(rapport?.appels ?? [])].reverse().find((a) => a.run_id);
    useEffect(() => {
        if (!enJeu) return;
        const minuteur = setInterval(() => void lireRapport(), INTERVALLE_MS);
        return () => clearInterval(minuteur);
    }, [enJeu, lireRapport]);

    const basculer = (id: string) =>
        setChoisis((avant) => {
            const apres = new Set(avant);
            if (apres.has(id)) apres.delete(id);
            else apres.add(id);
            return apres;
        });

    const lancer = async () => {
        setEnCours(true);
        setErreur(null);
        const reponse = await lancerSerieSimuleeApiV1AppelSimuleAgentsWorkflowIdSeriesPost({
            path: { workflow_id: workflowId },
            body: { scenario_ids: [...choisis] },
        });
        setEnCours(false);
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Series not started"));
            return;
        }
        suivie.current = (reponse.data as SerieSimulee).id;
        setChoisis(new Set());
        await charger();
    };

    const arreter = async () => {
        if (!rapport) return;
        const reponse = await arreterSerieSimuleeApiV1AppelSimuleSeriesSerieIdArreterPost({
            path: { serie_id: rapport.serie.id },
        });
        if (reponse.error) setErreur(detailFromError(reponse.error, "Series not stopped"));
        else await lireRapport();
    };

    const estime = estimation(series, choisis.size);
    const trop = reglages ? choisis.size > (reglages.taille_max_serie ?? 10) : false;

    return (
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto" data-testid="appelant-simule">
            <div className="flex flex-wrap gap-2">
                <Button variant="outline" size="sm" onClick={() => setModale("scenarios")}>
                    <ListChecks className="mr-1 h-4 w-4" />
                    {t({ en: "Scenarios…", fr: "Scénarios…" })}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setModale("reglages")}>
                    <Settings className="mr-1 h-4 w-4" />
                    {t({ en: "Settings…", fr: "Réglages…" })}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setModale("rapport")}>
                    <FileBarChart className="mr-1 h-4 w-4" />
                    {t({ en: "Report…", fr: "Rapport…" })}
                </Button>
            </div>
            {erreur && (
                <p className="text-sm text-destructive" role="alert">
                    {erreur}
                </p>
            )}
            {scenarios === null ? (
                !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
            ) : scenarios.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                    {t({
                        en: "No scenario for this agent yet: write one in « Scenarios… ».",
                        fr: "Aucun scénario pour cet agent : écrivez-en un dans « Scénarios… ».",
                    })}
                </p>
            ) : (
                <div className="space-y-2">
                    <ul className="space-y-1" data-testid="choix-scenarios">
                        {scenarios.map((s) => (
                            <li key={s.id}>
                                <label className="flex items-center gap-2 text-sm">
                                    <input type="checkbox" checked={choisis.has(s.id)} onChange={() => basculer(s.id)} />
                                    {s.nom}
                                </label>
                            </li>
                        ))}
                    </ul>
                    <p className="text-xs text-muted-foreground" data-testid="estimation">
                        {estime === null
                            ? t({
                                  en: `Estimated cost: unknown until the first call · cap ${reglages?.plafond ?? 5}`,
                                  fr: `Coût estimé : inconnu avant le premier appel · plafond ${reglages?.plafond ?? 5}`,
                              })
                            : t({
                                  en: `Estimated cost ≈ ${estime} · cap ${reglages?.plafond ?? 5} (the series stops before exceeding it)`,
                                  fr: `Coût estimé ≈ ${estime} · plafond ${reglages?.plafond ?? 5} (la série s'arrête avant de le dépasser)`,
                              })}
                    </p>
                    {trop && (
                        <p className="text-xs text-destructive">
                            {t({
                                en: `A series is ${reglages?.taille_max_serie} calls at most.`,
                                fr: `Une série fait ${reglages?.taille_max_serie} appels au plus.`,
                            })}
                        </p>
                    )}
                    <Button size="sm" onClick={() => void lancer()} disabled={enCours || enJeu || choisis.size === 0 || trop}>
                        <Play className="mr-1 h-4 w-4" />
                        {t({ en: `Run ${choisis.size} call(s)`, fr: `Lancer ${choisis.size} appel(s)` })}
                    </Button>
                </div>
            )}
            {rapport ? (
                <div className="space-y-2 rounded border border-border p-3 text-sm" data-testid="serie-suivie">
                    <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">
                            {t({ en: "Last series", fr: "Dernière série" })} · {t(ETATS_SERIE[rapport.serie.etat ?? "en_cours"])}
                        </span>
                        {enJeu ? (
                            <Button variant="outline" size="sm" onClick={() => void arreter()}>
                                <Square className="mr-1 h-4 w-4" />
                                {t({ en: "Stop", fr: "Arrêter" })}
                            </Button>
                        ) : null}
                    </div>
                    <ul className="space-y-1">
                        {rapport.appels.map((a, i) => (
                            <li key={`${a.scenario_id}-${i}`} className="flex items-center gap-2" data-testid="appel-suivi">
                                <span>{a.reussi === true ? "✓" : a.reussi === false ? "✗" : "·"}</span>
                                <span className="flex-1 truncate">{a.scenario_nom}</span>
                                <span className="text-xs text-muted-foreground">{t(ETATS_APPEL[a.etat] ?? ETATS_APPEL.a_jouer)}</span>
                                {a.run_id ? (
                                    <a
                                        className="text-xs underline"
                                        href={`/workflow/${workflowId}/run/${a.run_id}`}
                                        target="_blank"
                                        rel="noreferrer"
                                    >
                                        {t({ en: "run window", fr: "fenêtre du run" })}
                                    </a>
                                ) : null}
                            </li>
                        ))}
                    </ul>
                    <p className="text-xs text-muted-foreground">
                        {t({
                            en: `Cost so far ${rapport.serie.cout ?? 0} ${rapport.serie.devise ?? "USD"}${rapport.serie.cout_partiel ? " (partial)" : ""}. The call on the line is followed live below; its saved transcript and verdict are in its run window when it ends.`,
                            fr: `Coût à ce stade ${rapport.serie.cout ?? 0} ${rapport.serie.devise ?? "USD"}${rapport.serie.cout_partiel ? " (partiel)" : ""}. L'appel en ligne se suit en direct ci-dessous ; sa transcription enregistrée et son verdict sont dans sa fenêtre du run à la fin de l'appel.`,
                        })}
                    </p>
                    {/* [.mark] The call on the line, or else the last one played (direct-et-passe-muette, lot A). */}
                    {appelSuivi?.run_id ? <DirectAppelSimule key={appelSuivi.run_id} runId={appelSuivi.run_id} workflowId={workflowId} /> : null}
                    {rapport.serie.raison ? <p className="text-xs text-muted-foreground">{rapport.serie.raison}</p> : null}
                </div>
            ) : null}
            <ModaleScenarios
                workflowId={workflowId}
                ouverte={modale === "scenarios"}
                onFermer={(enregistre) => {
                    setModale(null);
                    if (enregistre) void charger();
                }}
            />
            <ModaleReglagesAppelantSimule
                ouverte={modale === "reglages"}
                onFermer={() => {
                    setModale(null);
                    void charger();
                }}
            />
            <ModaleRapportSeries workflowId={workflowId} ouverte={modale === "rapport"} onFermer={() => setModale(null)} />
        </div>
    );
}

/** The tab's title, in the screen's language (used by Dograh's tester panel). */
export function TitreOngletAppelantSimule() {
    const { t } = useLangue();
    return <>{t(TITRE_ONGLET)}</>;
}
