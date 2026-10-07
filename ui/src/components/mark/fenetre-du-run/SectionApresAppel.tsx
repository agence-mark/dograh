"use client";

/**
 * [.mark] The section « After the call » of the run window (chantier l-agent-travaille, L4, A9, A10).
 *
 * Each step of the after-call (written in the client's database, summary, mail, each module)
 * with its status: waiting, running, done, failed (red), skipped; the attempts, what it did, and
 * « Retry » on a failed or skipped step. Read from `GET /workflow/{id}/runs/{run}/apres-appel`;
 * refreshed while a step is waiting or running. Shown only when the run's agent uses the
 * after-call: an agent that switched nothing on shows nothing new (X2).
 */
import { ChevronDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    getApresAppelDuRunApiV1WorkflowWorkflowIdRunsRunIdApresAppelGet,
    postRelancerEtapeApiV1WorkflowWorkflowIdRunsRunIdApresAppelEtapeRelancerPost,
} from "@/client/sdk.gen";
import type { ApresAppelDuRun, EtapeApresAppel } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { detailFromError } from "@/lib/apiError";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";

const NOMS_DES_ETAPES: Record<string, Texte> = {
    ecriture: { en: "Written in the client's database", fr: "Écrit dans la base du client" },
    synthese: { en: "Summary", fr: "Synthèse" },
    mail: { en: "Mail of the request", fr: "Mail de la demande" },
    "module:webhook": { en: "Module · custom webhook", fr: "Module · webhook sur mesure" },
};

export const nomDeLEtape = (nom: string): Texte =>
    NOMS_DES_ETAPES[nom] ?? (nom.startsWith("module:") ? { en: `Module · ${nom.slice(7)}`, fr: `Module · ${nom.slice(7)}` } : { en: nom, fr: nom });

const STATUTS: Record<EtapeApresAppel["statut"], Texte> = {
    en_attente: { en: "waiting", fr: "en attente" },
    en_cours: { en: "running", fr: "en cours" },
    ok: { en: "done", fr: "fait" },
    echec: { en: "failed", fr: "en échec" },
    ignoree: { en: "skipped", fr: "sans objet" },
};

const INTERVALLE_MS = 3000;
const RELECTURES_MAX = 60;

export function SectionApresAppel({ workflowId, runId }: { workflowId: number; runId: number }) {
    const { t } = useLangue();
    const [donnees, setDonnees] = useState<ApresAppelDuRun | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [ouvert, setOuvert] = useState(true);
    const [relance, setRelance] = useState<string | null>(null);
    const relectures = useRef(0);

    const lire = useCallback(async () => {
        const reponse = await getApresAppelDuRunApiV1WorkflowWorkflowIdRunsRunIdApresAppelGet({
            path: { workflow_id: workflowId, run_id: runId },
        });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "After-call unreadable"));
            return null;
        }
        setErreur(null);
        setDonnees(reponse.data);
        return reponse.data;
    }, [workflowId, runId]);

    useEffect(() => {
        let arret = false;
        let minuterie: ReturnType<typeof setTimeout> | undefined;
        const boucle = async () => {
            const lu = await lire();
            if (arret || !lu) return;
            const enAttente = (lu.etapes ?? []).some((e) => e.statut === "en_attente" || e.statut === "en_cours");
            if (enAttente && relectures.current < RELECTURES_MAX) {
                relectures.current += 1;
                minuterie = setTimeout(() => void boucle(), INTERVALLE_MS);
            }
        };
        void boucle();
        return () => {
            arret = true;
            if (minuterie) clearTimeout(minuterie);
        };
    }, [lire, relance]);

    const relancer = async (etape: string) => {
        const reponse = await postRelancerEtapeApiV1WorkflowWorkflowIdRunsRunIdApresAppelEtapeRelancerPost({
            path: { workflow_id: workflowId, run_id: runId, etape },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "Retry refused"));
            return;
        }
        if (reponse.data) setDonnees(reponse.data);
        relectures.current = 0;
        setRelance(`${etape}-${Date.now()}`);
    };

    if (erreur && !donnees)
        return (
            <p className="text-sm text-destructive" role="alert" data-testid="bloc-apres-appel-erreur">
                {t({ en: "After the call unavailable", fr: "Après l'appel indisponible" })} : {erreur}
            </p>
        );
    if (!donnees || !donnees.actif) return null;

    const echecs = (donnees.etapes ?? []).filter((e) => e.statut === "echec").length;
    const faites = (donnees.etapes ?? []).filter((e) => e.statut === "ok").length;

    return (
        <Card className="border-border" data-testid="bloc-apres-appel">
            <Collapsible open={ouvert} onOpenChange={setOuvert}>
                <CardHeader className="pb-3">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 text-left">
                        <CardTitle className="text-lg">{t({ en: "After the call", fr: "Après l'appel" })}</CardTitle>
                        <span className="flex items-center gap-3 text-sm text-muted-foreground">
                            <span className={cn(echecs > 0 && "font-medium text-destructive")}>
                                {echecs > 0
                                    ? t({ en: `${echecs} failed`, fr: `${echecs} en échec` })
                                    : `${faites}/${(donnees.etapes ?? []).length}`}
                            </span>
                            <ChevronDown className={cn("h-4 w-4 transition-transform", ouvert && "rotate-180")} />
                        </span>
                    </CollapsibleTrigger>
                </CardHeader>
                <CollapsibleContent>
                    <CardContent className="space-y-3 text-sm">
                        {erreur && (
                            <p className="text-destructive" role="alert">
                                {erreur}
                            </p>
                        )}
                        <ul className="space-y-2">
                            {(donnees.etapes ?? []).map((etape) => (
                                <li
                                    key={etape.nom}
                                    data-testid="etape-apres-appel"
                                    data-statut={etape.statut}
                                    className={cn(
                                        "flex flex-wrap items-start justify-between gap-2 rounded border p-2",
                                        etape.statut === "echec" ? "border-destructive/60 bg-destructive/5" : "border-border",
                                    )}
                                >
                                    <div className="min-w-0 flex-1 space-y-0.5">
                                        <div className="flex flex-wrap items-center gap-2">
                                            <span className="font-medium">{t(nomDeLEtape(etape.nom))}</span>
                                            <span
                                                className={cn(
                                                    "rounded px-1.5 py-0.5 text-xs",
                                                    etape.statut === "ok" && "border border-(--signal-ok) text-(--signal-ok)",
                                                    etape.statut === "echec" && "bg-destructive/15 font-medium text-destructive",
                                                    (etape.statut === "en_attente" || etape.statut === "en_cours" || etape.statut === "ignoree") &&
                                                        "bg-muted text-muted-foreground",
                                                )}
                                            >
                                                {t(STATUTS[etape.statut])}
                                                {etape.statut === "echec" && !etape.definitive
                                                    ? ` · ${t({ en: "will retry", fr: "nouvelle tentative prévue" })}`
                                                    : ""}
                                            </span>
                                            {(etape.tentatives ?? 0) > 1 && (
                                                <span className="text-xs text-muted-foreground">
                                                    {t({ en: `${etape.tentatives} attempts`, fr: `${etape.tentatives} tentatives` })}
                                                </span>
                                            )}
                                        </div>
                                        {etape.detail && <p className="break-words text-muted-foreground">{etape.detail}</p>}
                                        {etape.le && (
                                            <p className="text-xs text-muted-foreground">{new Date(etape.le).toLocaleString()}</p>
                                        )}
                                    </div>
                                    {(etape.statut === "echec" || etape.statut === "ignoree") && (
                                        <Button size="sm" variant="outline" onClick={() => void relancer(etape.nom)} data-testid={`relancer-${etape.nom}`}>
                                            {t({ en: "Retry", fr: "Relancer" })}
                                        </Button>
                                    )}
                                </li>
                            ))}
                        </ul>
                        {donnees.synthese && (
                            <div data-testid="synthese-du-run">
                                <p className="font-medium">{t({ en: "Summary", fr: "Synthèse" })}</p>
                                <p className="text-muted-foreground">{donnees.synthese}</p>
                            </div>
                        )}
                        {(donnees.appel_id || donnees.demande_id) && (
                            <p className="text-xs text-muted-foreground">
                                {t({ en: "In the client's database", fr: "Dans la base du client" })} :{" "}
                                {donnees.appel_id ? `${t({ en: "call", fr: "appel" })} ${donnees.appel_id}` : ""}
                                {donnees.demande_id ? ` · ${t({ en: "request", fr: "demande" })} ${donnees.demande_id}` : ""}
                                {donnees.autre_demande_ouverte_id
                                    ? ` · ${t({
                                          en: `another open request from the same number: ${donnees.autre_demande_ouverte_id}`,
                                          fr: `autre demande ouverte du même numéro : ${donnees.autre_demande_ouverte_id}`,
                                      })}`
                                    : ""}
                            </p>
                        )}
                    </CardContent>
                </CollapsibleContent>
            </Collapsible>
        </Card>
    );
}
