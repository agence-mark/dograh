"use client";

/**
 * [.mark] The section « After the call » of the run window (chantier l-agent-travaille, L4, A9, A10).
 *
 * Each step of the after-call (written in the client's database, summary, mail, each module)
 * with its status: waiting, running, done, failed (red), skipped; the attempts, what it did, and
 * « Retry » on a failed or skipped step. Read from `GET /workflow/{id}/runs/{run}/apres-appel`;
 * refreshed while a step is waiting or running. Shown only when the run's agent uses the
 * after-call: an agent that switched nothing on shows nothing new (X2).
 *
 * Chantier l-agent-collegue, L8: the sub-part « Mentions » -- the people of the team this call
 * concerns (person, source, certainty) and what the agent did for the team (transfers, requests
 * passed on, call-backs, appointments, verifications); and the record's verdict (L7, Q-2).
 */
import { ChevronDown } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
    getApresAppelDuRunApiV1WorkflowWorkflowIdRunsRunIdApresAppelGet,
    postRelancerEtapeApiV1WorkflowWorkflowIdRunsRunIdApresAppelEtapeRelancerPost,
} from "@/client/sdk.gen";
import type { ActionEquipe, ApresAppelDuRun, EtapeApresAppel, MentionDuRun } from "@/client/types.gen";
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
    "module:connecteurs": { en: "Module · software actions put aside", fr: "Module · actions mises de côté" },
    "module:sms": { en: "Module · SMS", fr: "Module · SMS" },
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

// Chantier l-agent-collegue, L8: the words of the sub-part « Mentions ».
export const SOURCES_MENTION: Record<string, Texte> = {
    transfert: { en: "transfer", fr: "transfert" },
    transmission: { en: "request passed on", fr: "demande transmise" },
    destinataire: { en: "mail recipient", fr: "destinataire du mail" },
    rendez_vous: { en: "appointment", fr: "rendez-vous" },
    nom_cite: { en: "name cited", fr: "nom cité" },
};
export const CERTITUDES: Record<string, Texte> = {
    certaine: { en: "certain", fr: "certaine" },
    detectee: { en: "detected", fr: "détectée" },
    a_confirmer: { en: "to confirm", fr: "à confirmer" },
};
export const ACTIONS_EQUIPE: Record<string, Texte> = {
    transfert: { en: "Transfer", fr: "Transfert" },
    transmission: { en: "Request passed on", fr: "Demande transmise" },
    rappel: { en: "Call-back to make", fr: "Rappel à faire" },
    rendez_vous: { en: "Appointment booked", fr: "Rendez-vous posé" },
    verification: { en: "Caller verification", fr: "Vérification de l'appelant" },
    dossier_lu: { en: "Record read", fr: "Dossier lu" },
};
export const PROBLEMES_FICHE: Record<string, Texte> = {
    telephone_invalide: { en: "invalid phone", fr: "téléphone invalide" },
    code_postal_inconnu: { en: "unknown postcode", fr: "code postal inconnu" },
    commune_code_postal_incoherents: { en: "town and postcode do not match", fr: "commune et code postal ne vont pas ensemble" },
    courriel_invalide: { en: "invalid e-mail", fr: "e-mail invalide" },
    courriel_domaine_douteux: { en: "doubtful e-mail domain", fr: "domaine de l'e-mail douteux" },
    date_invalide: { en: "unreadable date", fr: "date illisible" },
    date_improbable: { en: "improbable date", fr: "date improbable" },
    champ_vide: { en: "empty field", fr: "champ vide" },
};
const STATUTS_FICHE: Record<string, Texte> = {
    complete: { en: "complete", fr: "complète" },
    a_reprendre: { en: "to take up again", fr: "à reprendre" },
    non_controle: { en: "not checked", fr: "non contrôlée" },
};

const traduire = (table: Record<string, Texte>, cle: string, t: (x: Texte) => string) => (table[cle] ? t(table[cle]) : cle);

function SousPartieMentions({ donnees }: { donnees: ApresAppelDuRun }) {
    const { t } = useLangue();
    const mentions: MentionDuRun[] = donnees.mentions ?? [];
    const actions: ActionEquipe[] = donnees.actions_equipe ?? [];
    if (!mentions.length && !actions.length && !donnees.mentions_illisibles) return null;
    return (
        <div className="space-y-2" data-testid="mentions-du-run">
            <p className="font-medium">{t({ en: "Mentions", fr: "Mentions" })}</p>
            {donnees.mentions_illisibles && (
                <p className="text-destructive" role="alert">
                    {t({ en: "The client's database could not be read for the mentions.", fr: "La base du client n'a pas pu être lue pour les mentions." })}
                </p>
            )}
            {mentions.length > 0 && (
                <ul className="space-y-1" data-testid="liste-mentions">
                    {mentions.map((m, i) => (
                        <li key={i} className="flex flex-wrap items-baseline gap-x-2 break-words" data-testid="mention" data-certitude={m.certitude}>
                            <span className="font-medium">{m.personne}</span>
                            <span className="text-muted-foreground">{traduire(SOURCES_MENTION, m.source, t)}</span>
                            <span
                                className={cn(
                                    "rounded px-1.5 py-0.5 text-xs",
                                    m.certitude === "certaine" ? "border border-(--signal-ok) text-(--signal-ok)" : "bg-muted text-muted-foreground",
                                )}
                            >
                                {traduire(CERTITUDES, m.certitude, t)}
                            </span>
                            {m.extrait && <span className="min-w-0 text-xs text-muted-foreground">« {m.extrait} »</span>}
                        </li>
                    ))}
                </ul>
            )}
            {actions.length > 0 && (
                <div data-testid="actions-equipe">
                    <p className="text-xs font-medium text-muted-foreground">{t({ en: "What the agent did for the team", fr: "Ce que l'agent a fait pour l'équipe" })}</p>
                    <ul className="space-y-1">
                        {actions.map((a, i) => (
                            <li key={i} className="break-words" data-testid="action-equipe" data-type={a.type}>
                                <span className="font-medium">{traduire(ACTIONS_EQUIPE, a.type, t)}</span>
                                {a.personne ? ` · ${a.personne}` : ""}
                                {a.detail ? <span className="text-muted-foreground"> · {a.detail}</span> : null}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function VerdictFiche({ donnees }: { donnees: ApresAppelDuRun }) {
    const { t } = useLangue();
    const q = donnees.qualite_fiche as { statut?: string; problemes?: Array<{ champ: string; code: string; detail?: string | null }> } | null | undefined;
    if (!q?.statut) return null;
    return (
        <div data-testid="qualite-fiche" data-statut={q.statut}>
            <p className="font-medium">
                {t({ en: "Record", fr: "Fiche" })} :{" "}
                <span className={cn(q.statut === "a_reprendre" && "text-destructive")}>{traduire(STATUTS_FICHE, q.statut, t)}</span>
            </p>
            {(q.problemes ?? []).length > 0 && (
                <ul className="text-muted-foreground">
                    {(q.problemes ?? []).map((p, i) => (
                        <li key={i} className="break-words">
                            {p.champ} : {traduire(PROBLEMES_FICHE, p.code, t)}
                            {p.detail ? ` (${p.detail})` : ""}
                        </li>
                    ))}
                </ul>
            )}
            <p className="text-xs text-muted-foreground">{t({ en: "Signalled, never corrected: the record stays as noted.", fr: "Signalé, jamais corrigé : la fiche reste telle que notée." })}</p>
        </div>
    );
}

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
    if (donnees?.essai && !donnees.actif)
        return (
            <p className="text-sm text-muted-foreground" data-testid="bloc-apres-appel-essai">
                {t({
                    en: "After the call: test call, after-call not run (the agent keeps test calls out; « Test calls go through the after-call » lets them in).",
                    fr: "Après l'appel : essai, après-appel non exécuté (l'agent tient les essais à l'écart ; « Les essais passent par l'après-appel » les laisse passer).",
                })}
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
                        <VerdictFiche donnees={donnees} />
                        <SousPartieMentions donnees={donnees} />
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
