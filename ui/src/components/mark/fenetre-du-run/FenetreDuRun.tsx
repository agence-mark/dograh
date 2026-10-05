"use client";

/**
 * [.mark] The run window (chantier langwatch-et-fenetre-du-run, lot 1).
 *
 * Shows, on a run's page, what the fork already records and nobody saw without the lab's tools:
 * latency turn by turn (wait for the end of the turn, each model pass and why, voice), providers
 * and consumption, the work of the reading modules, the record with the origin of each field, the
 * path, the timed conversation (a click plays the recording from that line) and the incidents.
 *
 * The numbers come from the server (`GET /workflow/{id}/runs/{run}/analyse`), computed with the
 * lab's own definition: the screen and the lab's tools give the same figures (decision L1).
 * A block the server could not compute says "unavailable"; data the run does not hold says
 * "not captured". Never an empty card (R1).
 */
import { ChevronDown } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet } from "@/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { detailFromError } from "@/lib/apiError";
import { getSignedUrl } from "@/lib/files";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import type {
    AnalyseDuRun,
    Bloc,
    Conversation,
    Fiche,
    Fournisseurs,
    Incidents,
    Latence,
    Modules,
    NatureDePasse,
    Parcours,
    Resume,
    Simulation,
    TourDeLatence,
} from "./types";

/** « 2026-10-01 » → « 01/10 ». */
const dateCourte = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

const secondes = (valeur: number | null | undefined) =>
    typeof valeur === "number" ? `${valeur.toFixed(2)} s` : "–";

const NATURES: Record<NatureDePasse, Texte> = {
    reply: { en: "reply", fr: "réponse" },
    note: { en: "after note-taking", fr: "après une prise de notes" },
    transition: { en: "after a transition", fr: "après une porte" },
    tool: { en: "after a tool", fr: "après un outil" },
    tool_or_transition: { en: "after a tool or a transition", fr: "après un outil ou une porte" },
};

const RAISONS: Record<string, Texte> = {
    greeting: { en: "greeting (not a reply)", fr: "accueil (pas une réponse)" },
    no_latency_detail: { en: "no latency detail recorded", fr: "aucun détail de latence enregistré" },
    no_model_call: { en: "no model call", fr: "aucun appel au modèle" },
    no_final_transcript: { en: "no final transcript", fr: "aucune transcription finale" },
    no_reply: { en: "the agent did not reply", fr: "l'agent n'a pas répondu" },
    unreadable_timestamps: { en: "unreadable timestamps", fr: "horodatages illisibles" },
};

const MODULES: Record<string, Texte> = {
    numbers: { en: "Numbers", fr: "Nombres" },
    spelling: { en: "Spelling", fr: "Épellation" },
    towns: { en: "Towns", fr: "Communes" },
    streets: { en: "Streets", fr: "Rues" },
    vocabulary: { en: "Business vocabulary", fr: "Lexique métier" },
};

const INCIDENTS: Record<string, Texte> = {
    model_rate_limited: { en: "Model refused: rate limit", fr: "Modèle refusé : quota" },
    pipeline_error: { en: "Pipeline error", fr: "Erreur du pipeline" },
    tool_never_finished: { en: "Tool never finished", fr: "Outil jamais terminé" },
    model_retried: { en: "Model request retried", fr: "Requête du modèle recommencée" },
    provider_disconnected: { en: "Provider disconnected during the call", fr: "Fournisseur déconnecté pendant l'appel" },
    provider_error: { en: "Provider connection error", fr: "Erreur de connexion d'un fournisseur" },
    silence_after_tool: { en: "Silence after a tool result", fr: "Silence après un résultat d'outil" },
    slow_turn: { en: "Slow turn", fr: "Tour lent" },
};

const MARQUES: Record<string, Texte> = {
    caller_interrupted: { en: "the caller interrupted the agent", fr: "l'appelant a coupé l'agent" },
    idle_reminder: { en: "silence reminder", fr: "relance d'inactivité" },
    idle_hang_up: { en: "hang-up after silence", fr: "raccrochage après silence" },
};

const BRIQUES: Record<string, Texte> = {
    transcription: { en: "Transcription", fr: "Transcription" },
    voice: { en: "Voice", fr: "Voix" },
};

const CANAUX: Record<string, Texte> = {
    browser: { en: "browser", fr: "navigateur" },
    keyboard: { en: "keyboard", fr: "clavier" },
    phone: { en: "phone", fr: "téléphone" },
    simulated: { en: "simulated caller", fr: "appelant simulé" },
};

function EtatDuBloc({ bloc }: { bloc: Bloc }) {
    const { t } = useLangue();
    if (bloc.status === "unavailable") {
        return (
            <p className="text-sm text-destructive" role="alert">
                {t({
                    en: "Unavailable: the server could not compute this block for this run.",
                    fr: "Indisponible : le serveur n'a pas pu calculer ce bloc pour ce run.",
                })}
            </p>
        );
    }
    return (
        <p className="text-sm text-muted-foreground">
            {t({ en: "Not captured for this run.", fr: "Non capté pour ce run." })}
        </p>
    );
}

function Section({
    titre,
    resume,
    bloc,
    ouverte = false,
    testId,
    children,
}: {
    titre: Texte;
    resume?: ReactNode;
    bloc: Bloc;
    ouverte?: boolean;
    testId: string;
    children: ReactNode;
}) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(ouverte);
    return (
        <Card className="border-border" data-testid={testId}>
            <Collapsible open={ouvert} onOpenChange={setOuvert}>
                <CardHeader className="pb-3">
                    <CollapsibleTrigger className="flex w-full items-center justify-between gap-4 text-left">
                        <CardTitle className="text-lg">{t(titre)}</CardTitle>
                        <span className="flex items-center gap-3 text-sm text-muted-foreground">
                            {bloc.status === "ok" ? resume : null}
                            <ChevronDown className={cn("h-4 w-4 transition-transform", ouvert && "rotate-180")} />
                        </span>
                    </CollapsibleTrigger>
                </CardHeader>
                <CollapsibleContent>
                    <CardContent>{bloc.status === "ok" ? children : <EtatDuBloc bloc={bloc} />}</CardContent>
                </CollapsibleContent>
            </Collapsible>
        </Card>
    );
}

function BlocResume({ resume, incidents }: { resume: Resume; incidents: Incidents }) {
    const { t } = useLangue();
    if (resume.status !== "ok") return <EtatDuBloc bloc={resume} />;
    const nombre = resume.incident_count ?? 0;
    return (
        <div className="space-y-2 text-sm" data-testid="fenetre-resume">
            <p>
                {t({ en: "Channel", fr: "Canal" })} : {t(CANAUX[resume.channel ?? "phone"] ?? CANAUX.phone)} ·{" "}
                {t({ en: "Duration", fr: "Durée" })} : {secondes(resume.duration_secs)} ·{" "}
                {t({ en: "Agent version", fr: "Version de l'agent" })} : <code>{resume.definition_id ?? "–"}</code> ·{" "}
                {t({ en: "Outcome", fr: "Issue" })} : <code>{resume.disposition ?? "–"}</code>
            </p>
            <p className="text-muted-foreground" data-testid="fenetre-version">
                {resume.version && resume.version.status !== "not_captured" ? (
                    <>
                        {t({ en: "Code", fr: "Code" })} : <code>{resume.version.app_version ?? "–"}</code> ·{" "}
                        {t({ en: "deployed commit", fr: "commit déployé" })} :{" "}
                        <code>{resume.version.commit ? resume.version.commit.slice(0, 8) : "–"}</code> ·{" "}
                        {t({ en: "agent version", fr: "version de l'agent" })} :{" "}
                        <code>{resume.version.version_number ?? "–"}</code> (<code>{resume.version.definition_status ?? "–"}</code>)
                    </>
                ) : (
                    t({
                        en: "Code version: not captured (run older than this capture).",
                        fr: "Version du code : non captée (run antérieur à cette capture).",
                    })
                )}
            </p>
            <p data-testid="fenetre-cout">
                {resume.cost?.status === "ok" ? (
                    <>
                        {t({ en: "Estimated cost", fr: "Coût estimé" })} :{" "}
                        <strong>
                            {resume.cost.total?.toFixed(4)} {resume.cost.currency}
                        </strong>{" "}
                        {t({
                            en: `at the rate of ${(resume.cost.rate_dates ?? []).map(dateCourte).join(", ")}`,
                            fr: `au tarif du ${(resume.cost.rate_dates ?? []).map(dateCourte).join(", ")}`,
                        })}
                        {resume.cost.partial
                            ? ` · ${t({
                                  en: `partial: no price for ${(resume.cost.unpriced ?? []).map((u) => u.model).join(", ")}`,
                                  fr: `partiel : pas de prix pour ${(resume.cost.unpriced ?? []).map((u) => u.model).join(", ")}`,
                              })}`
                            : ""}
                    </>
                ) : (
                    <span className="text-muted-foreground">
                        {t({
                            en: "Estimated cost: not captured (no price table in the organization settings, or no consumption recorded).",
                            fr: "Coût estimé : non capté (pas de table des prix dans les paramètres de l'organisation, ou aucune consommation enregistrée).",
                        })}
                    </span>
                )}
            </p>
            {nombre > 0 && incidents.status === "ok" && (
                <p className="font-medium text-destructive" role="alert">
                    {t({
                        en: `${nombre} incident(s) on this call: see Incidents.`,
                        fr: `${nombre} incident(s) sur cet appel : voir Incidents.`,
                    })}
                </p>
            )}
        </div>
    );
}

function BarreDuTour({ tour, echelle }: { tour: TourDeLatence; echelle: number }) {
    const { t } = useLangue();
    const morceaux: { secs: number; classe: string; titre: Texte }[] = [];
    if (tour.end_of_turn_wait_secs)
        morceaux.push({
            secs: tour.end_of_turn_wait_secs,
            classe: "bg-muted-foreground/30",
            titre: { en: "wait for the end of the turn", fr: "attente de fin de tour" },
        });
    for (const passe of tour.passes) {
        if (!passe.secs) continue;
        morceaux.push({
            secs: passe.secs,
            classe: passe.after === "reply" ? "bg-foreground" : "bg-foreground/50",
            titre: NATURES[passe.after] ?? NATURES.tool,
        });
    }
    if (tour.voice_secs)
        morceaux.push({ secs: tour.voice_secs, classe: "bg-muted-foreground/60", titre: { en: "voice", fr: "voix" } });
    return (
        <div className="flex h-3 w-full overflow-hidden rounded-sm bg-muted">
            {morceaux.map((m, i) => (
                <div
                    key={i}
                    className={cn("h-full border-r border-background", m.classe)}
                    style={{ width: `${Math.max(1, (m.secs / echelle) * 100)}%` }}
                    title={`${t(m.titre)} : ${secondes(m.secs)}`}
                />
            ))}
        </div>
    );
}

function BlocLatence({ latence }: { latence: Latence }) {
    const { t } = useLangue();
    const tours = latence.turns ?? [];
    const echelle = Math.max(
        1,
        ...tours.map(
            (x) =>
                (x.end_of_turn_wait_secs ?? 0) +
                x.passes.reduce((s, p) => s + (p.secs ?? 0), 0) +
                (x.voice_secs ?? 0),
        ),
    );
    const stats = latence.stats;
    return (
        <div className="space-y-3 text-sm">
            {stats && (
                <p>
                    {t({
                        en: `Median silence ${secondes(stats.median_silence_secs)} · worst ${secondes(stats.worst_silence_secs)} (turn ${stats.worst_turn ?? "–"}) · ${stats.share_under_threshold == null ? "–" : Math.round(stats.share_under_threshold * 100)} % of turns under ${stats.threshold_secs} s · median passes ${stats.median_passes ?? "–"} · ${stats.measured_turns} of ${stats.total_turns} turns measured`,
                        fr: `Silence médian ${secondes(stats.median_silence_secs)} · pire ${secondes(stats.worst_silence_secs)} (tour ${stats.worst_turn ?? "–"}) · ${stats.share_under_threshold == null ? "–" : Math.round(stats.share_under_threshold * 100)} % des tours sous ${stats.threshold_secs} s · passes médianes ${stats.median_passes ?? "–"} · ${stats.measured_turns} tours mesurés sur ${stats.total_turns}`,
                    })}
                </p>
            )}
            <p data-testid="silence-entendu">
                {!latence.perceived || latence.perceived.status === "not_captured"
                    ? t({
                          en: "Silence actually heard: not captured (no separate tracks, or run older than this capture).",
                          fr: "Silence réellement entendu : non capté (pas de pistes séparées, ou run antérieur à cette capture).",
                      })
                    : latence.perceived.status === "unavailable"
                      ? t({
                            en: "Silence actually heard: unavailable (the tracks could not be analysed).",
                            fr: "Silence réellement entendu : indisponible (les pistes n'ont pas pu être analysées).",
                        })
                      : t({
                            en: `Silence actually heard (end of the caller's voice → first sound of the agent): median ${secondes(latence.perceived.median_secs)} · worst ${secondes(latence.perceived.worst_secs)} · ${latence.perceived.count ?? 0} replies`,
                            fr: `Silence réellement entendu (fin de la voix de l'appelant → premier son de l'agent) : médiane ${secondes(latence.perceived.median_secs)} · pire ${secondes(latence.perceived.worst_secs)} · ${latence.perceived.count ?? 0} réponses`,
                        })}
            </p>
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "Silence = end of the caller's words → first text of the agent. Bar: wait for the end of the turn, then each model pass (black = the reply), then the voice.",
                    fr: "Silence = fin des mots de l'appelant → premier texte de l'agent. Barre : attente de fin de tour, puis chaque passe du modèle (noir = la réponse), puis la voix.",
                })}
            </p>
            <ul className="space-y-2">
                {tours.map((tour, i) => (
                    <li
                        key={i}
                        data-testid="tour-de-latence"
                        className={cn("grid grid-cols-[5rem_1fr_6rem] items-center gap-3", tour.slow && "font-medium")}
                    >
                        <span className="truncate" title={tour.step}>
                            {t({ en: "Turn", fr: "Tour" })} {tour.turn ?? "?"}
                        </span>
                        {tour.measured ? (
                            <BarreDuTour tour={tour} echelle={echelle} />
                        ) : (
                            <span className="text-muted-foreground">
                                {t({ en: "not measured", fr: "non mesuré" })} :{" "}
                                {t(RAISONS[tour.not_measured_reason ?? ""] ?? { en: "unknown", fr: "inconnu" })}
                            </span>
                        )}
                        <span className={cn("text-right", tour.slow && "text-destructive")}>
                            {tour.measured ? secondes(tour.silence_secs) : ""}
                        </span>
                    </li>
                ))}
            </ul>
        </div>
    );
}

function BlocFournisseurs({ fournisseurs }: { fournisseurs: Fournisseurs }) {
    const { t } = useLangue();
    const ligne = (titre: Texte, brique?: { provider?: string; model?: string }, conso?: string) => (
        <tr className="border-b border-border last:border-0">
            <td className="py-1 pr-4 font-medium">{t(titre)}</td>
            <td className="py-1 pr-4">
                <code>{brique?.provider ?? "–"}</code> · <code>{brique?.model ?? "–"}</code>
            </td>
            <td className="py-1 text-muted-foreground">{conso}</td>
        </tr>
    );
    const somme = (lignes: object[] | undefined, cle: string) =>
        (lignes ?? []).reduce((s: number, l) => {
            const valeur = (l as Record<string, unknown>)[cle];
            return s + (typeof valeur === "number" ? valeur : 0);
        }, 0);
    const modele = fournisseurs.model;
    return (
        <div className="space-y-2 text-sm">
            <table className="w-full">
                <tbody>
                    {ligne(
                        { en: "Transcription", fr: "Transcription" },
                        fournisseurs.transcription,
                        t({
                            en: `${Math.round(somme(fournisseurs.transcription?.usage, "seconds"))} s transcribed`,
                            fr: `${Math.round(somme(fournisseurs.transcription?.usage, "seconds"))} s transcrites`,
                        }),
                    )}
                    {ligne(
                        { en: "Model", fr: "Modèle" },
                        modele,
                        t({
                            en: `${somme(modele?.usage, "prompt_tokens")} tokens in (${somme(modele?.usage, "cached_tokens")} cached), ${somme(modele?.usage, "completion_tokens")} out`,
                            fr: `${somme(modele?.usage, "prompt_tokens")} jetons en entrée (${somme(modele?.usage, "cached_tokens")} en cache), ${somme(modele?.usage, "completion_tokens")} en sortie`,
                        }),
                    )}
                    {ligne(
                        { en: "Voice", fr: "Voix" },
                        fournisseurs.voice,
                        t({
                            en: `${somme(fournisseurs.voice?.usage, "characters")} characters spoken`,
                            fr: `${somme(fournisseurs.voice?.usage, "characters")} caractères dits`,
                        }),
                    )}
                </tbody>
            </table>
            <p data-testid="requetes-du-modele">
                {!fournisseurs.model_requests || fournisseurs.model_requests.status === "not_captured"
                    ? t({
                          en: "Model refusals and retries: not captured (run older than this capture).",
                          fr: "Refus et nouvelles tentatives du modèle : non captés (run antérieur à cette capture).",
                      })
                    : t({
                          en: `Model refusals: ${fournisseurs.model_requests.refused ?? 0} · silent retries: ${fournisseurs.model_requests.retries ?? 0} · time lost: ${secondes(fournisseurs.model_requests.lost_secs)}`,
                          fr: `Refus du modèle : ${fournisseurs.model_requests.refused ?? 0} · nouvelles tentatives silencieuses : ${fournisseurs.model_requests.retries ?? 0} · temps perdu : ${secondes(fournisseurs.model_requests.lost_secs)}`,
                      })}
            </p>
            <p data-testid="connexions-des-fournisseurs">
                {!fournisseurs.connections || fournisseurs.connections.status === "not_captured"
                    ? t({
                          en: "Provider disconnections: not captured (run older than this capture).",
                          fr: "Coupures des fournisseurs : non captées (run antérieur à cette capture).",
                      })
                    : Object.entries(fournisseurs.connections)
                          .filter(([cle]) => cle !== "status")
                          .map(([brique, v]) => {
                              const c = v as { disconnections: number; errors: number };
                              return `${t(BRIQUES[brique] ?? { en: brique, fr: brique })} : ${t({
                                  en: `${c.disconnections} disconnection(s), ${c.errors} error(s)`,
                                  fr: `${c.disconnections} coupure(s), ${c.errors} erreur(s)`,
                              })}`;
                          })
                          .join(" · ") || t({ en: "No provider disconnection.", fr: "Aucune coupure de fournisseur." })}
            </p>
            <p className="text-muted-foreground">
                {t({ en: "Note-taking mode", fr: "Mode de prise de notes" })} :{" "}
                <code>{modele?.note_taking_mode ?? "–"}</code>
                {modele?.transitions_in_reply ? (
                    <> · {t({ en: "transitions in the reply", fr: "portes dans la réponse" })}</>
                ) : null}
            </p>
        </div>
    );
}

function BlocModules({ modules }: { modules: Modules }) {
    const { t } = useLangue();
    const elements = modules.items ?? [];
    if (!elements.length)
        return (
            <p className="text-sm text-muted-foreground">
                {t({ en: "The modules ran and read nothing.", fr: "Les modules ont tourné et n'ont rien lu." })}
            </p>
        );
    return (
        <table className="w-full text-sm">
            <thead className="text-left text-muted-foreground">
                <tr>
                    <th className="py-1 pr-3">{t({ en: "Module", fr: "Module" })}</th>
                    <th className="py-1 pr-3">{t({ en: "Caller turn", fr: "Tour de l'appelant" })}</th>
                    <th className="py-1 pr-3">{t({ en: "Heard", fr: "Entendu" })}</th>
                    <th className="py-1 pr-3">{t({ en: "Read as", fr: "Lu comme" })}</th>
                    <th className="py-1">{t({ en: "Status", fr: "Statut" })}</th>
                </tr>
            </thead>
            <tbody>
                {elements.map((e, i) => (
                    <tr key={i} className="border-t border-border" data-testid="element-de-module">
                        <td className="py-1 pr-3">{t(MODULES[e.module] ?? { en: e.module, fr: e.module })}</td>
                        <td className="py-1 pr-3">{e.caller_turn ?? "–"}</td>
                        <td className="py-1 pr-3">{e.heard ?? "–"}</td>
                        <td className="py-1 pr-3">
                            {e.result ?? (e.proposals.length ? e.proposals.join(" / ") : "–")}
                        </td>
                        <td className="py-1">
                            <code>{e.status ?? e.kind ?? "–"}</code>
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

const texteDeValeur = (valeur: unknown) =>
    valeur == null || valeur === "" ? "–" : typeof valeur === "string" ? valeur : JSON.stringify(valeur);

function BlocFiche({ fiche }: { fiche: Fiche }) {
    const { t } = useLangue();
    const champs = fiche.fields ?? [];
    return (
        <div className="space-y-3 text-sm">
            <table className="w-full">
                <thead className="text-left text-muted-foreground">
                    <tr>
                        <th className="py-1 pr-3">{t({ en: "Field", fr: "Champ" })}</th>
                        <th className="py-1 pr-3">{t({ en: "Value", fr: "Valeur" })}</th>
                        <th className="py-1 pr-3">{t({ en: "Origin", fr: "Provenance" })}</th>
                        <th className="py-1">{t({ en: "Caller turn", fr: "Tour de l'appelant" })}</th>
                    </tr>
                </thead>
                <tbody>
                    {champs.map((c) => (
                        <tr key={c.name} className="border-t border-border" data-testid="champ-de-fiche">
                            <td className="py-1 pr-3">
                                <code>{c.name}</code>
                            </td>
                            <td className={cn("py-1 pr-3", c.empty && "text-muted-foreground")}>
                                {c.empty ? t({ en: "empty", fr: "vide" }) : texteDeValeur(c.value)}
                            </td>
                            <td className="py-1 pr-3">
                                <code>{c.source ?? "–"}</code>
                                {c.sure === false ? ` · ${t({ en: "to confirm", fr: "à confirmer" })}` : ""}
                            </td>
                            <td className="py-1">{c.written_at_caller_turn ?? "–"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {(fiche.refusals ?? []).length > 0 && (
                <p className="text-muted-foreground">
                    {t({ en: "Refused writes", fr: "Écritures refusées" })} :{" "}
                    {(fiche.refusals ?? []).map((r, i) => (
                        <code key={i} className="mr-2">
                            {r.field} ({r.reason ?? r.status})
                        </code>
                    ))}
                </p>
            )}
        </div>
    );
}

function BlocParcours({ parcours }: { parcours: Parcours }) {
    const { t } = useLangue();
    return (
        <div className="space-y-3 text-sm">
            <p>
                {(parcours.steps ?? []).map((etape, i) => (
                    <span key={i}>
                        {i > 0 ? " → " : ""}
                        <code>{etape}</code>
                    </span>
                ))}
            </p>
            <table className="w-full">
                <thead className="text-left text-muted-foreground">
                    <tr>
                        <th className="py-1 pr-3">{t({ en: "Turn", fr: "Tour" })}</th>
                        <th className="py-1 pr-3">{t({ en: "Tool", fr: "Outil" })}</th>
                        <th className="py-1 pr-3">{t({ en: "Kind", fr: "Nature" })}</th>
                        <th className="py-1">{t({ en: "Duration", fr: "Durée" })}</th>
                    </tr>
                </thead>
                <tbody>
                    {(parcours.tools ?? []).map((o, i) => (
                        <tr key={i} className="border-t border-border" data-testid="outil-du-parcours">
                            <td className="py-1 pr-3">{o.turn ?? "–"}</td>
                            <td className="py-1 pr-3">
                                <code>{o.name}</code>
                            </td>
                            <td className="py-1 pr-3">{t(NATURES[o.kind] ?? NATURES.tool)}</td>
                            <td className="py-1">
                                {o.finished ? secondes(o.duration_secs) : t({ en: "never finished", fr: "jamais terminé" })}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

function BlocConversation({ conversation, recordingKey }: { conversation: Conversation; recordingKey?: string | null }) {
    const { t } = useLangue();
    const audio = useRef<HTMLAudioElement>(null);
    const [adresse, setAdresse] = useState<string | null>(null);
    const ecouter = async (debut: number | null) => {
        if (!recordingKey || debut == null) return;
        let source = adresse;
        if (!source) {
            source = await getSignedUrl(recordingKey, true);
            setAdresse(source);
        }
        const lecteur = audio.current;
        if (!lecteur || !source) return;
        if (lecteur.src !== source) lecteur.src = source;
        lecteur.currentTime = Math.max(0, debut);
        await lecteur.play().catch(() => undefined);
    };
    return (
        <div className="space-y-2 text-sm">
            <p className="text-xs text-muted-foreground">
                {recordingKey
                    ? t({
                          en: "Click a line to play the recording from there (approximate: the clock starts at the first event of the run).",
                          fr: "Cliquez une ligne pour écouter l'enregistrement à partir de là (approximatif : l'horloge part du premier événement du run).",
                      })
                    : t({ en: "No recording for this run.", fr: "Aucun enregistrement pour ce run." })}
            </p>
            {(conversation.marks ?? []).length > 0 && (
                <ul className="space-y-1" data-testid="marques-de-conversation">
                    {(conversation.marks ?? []).map((m, i) => (
                        <li key={i} className="text-muted-foreground">
                            {m.at_secs == null ? "–" : `${m.at_secs.toFixed(1)} s`} · {t({ en: "Turn", fr: "Tour" })}{" "}
                            {m.turn ?? "?"} · {t(MARQUES[m.kind] ?? { en: m.kind, fr: m.kind })}
                        </li>
                    ))}
                </ul>
            )}
            <audio ref={audio} controls={Boolean(adresse)} className={cn("w-full", !adresse && "hidden")} />
            <ul className="space-y-1">
                {(conversation.lines ?? []).map((ligne, i) => (
                    <li key={i}>
                        <button
                            type="button"
                            data-testid="ligne-de-conversation"
                            className="grid w-full grid-cols-[4rem_5rem_1fr] gap-2 rounded px-1 text-left hover:bg-muted"
                            onClick={() => ecouter(ligne.start_secs)}
                        >
                            <span className="text-muted-foreground">
                                {ligne.start_secs == null ? "–" : `${ligne.start_secs.toFixed(1)} s`}
                            </span>
                            <span className="font-medium">
                                {ligne.speaker === "caller"
                                    ? t({ en: "Caller", fr: "Appelant" })
                                    : t({ en: "Agent", fr: "Agent" })}
                            </span>
                            <span>{ligne.text}</span>
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    );
}

type DetailSilence = {
    secs: number;
    broken_by: "agent" | "caller";
    model_pass_after_tool: boolean | null;
    threshold_secs: number;
};

const texteDuSilence = (d: DetailSilence, t: (texte: Texte) => string) => {
    const qui =
        d.broken_by === "caller"
            ? t({ en: "the caller had to speak again", fr: "l'appelant a dû reparler" })
            : t({ en: "the agent replied late", fr: "l'agent a répondu en retard" });
    const passe =
        d.model_pass_after_tool === false
            ? t({
                  en: "no model pass after the tool (signature of Pipecat issue 5960)",
                  fr: "aucune passe du modèle après l'outil (signature du ticket Pipecat 5960)",
              })
            : d.model_pass_after_tool === true
              ? t({ en: "a model pass produced nothing spoken", fr: "une passe du modèle n'a rien fait dire" })
              : "";
    return [`${secondes(d.secs)} > ${d.threshold_secs} s`, qui, passe].filter(Boolean).join(" · ");
};

function BlocIncidents({ incidents }: { incidents: Incidents }) {
    const { t } = useLangue();
    const elements = incidents.items ?? [];
    if (!elements.length)
        return <p className="text-sm text-muted-foreground">{t({ en: "No incident.", fr: "Aucun incident." })}</p>;
    return (
        <ul className="space-y-1 text-sm">
            {elements.map((e, i) => (
                <li key={i} data-testid="incident" className={cn(e.fatal && "font-medium text-destructive")}>
                    {t({ en: "Turn", fr: "Tour" })} {e.turn ?? "?"} · {t(INCIDENTS[e.kind] ?? { en: e.kind, fr: e.kind })}
                    {e.kind === "silence_after_tool" && e.detail && typeof e.detail === "object" ? (
                        <> · {texteDuSilence(e.detail as DetailSilence, t)}</>
                    ) : e.detail != null ? (
                        <>
                            {" "}
                            · <code>{typeof e.detail === "number" ? secondes(e.detail) : String(e.detail)}</code>
                        </>
                    ) : null}
                </li>
            ))}
        </ul>
    );
}

function BlocSimulation({ simulation }: { simulation: Simulation }) {
    const { t } = useLangue();
    const r = simulation.resultat;
    if (!r)
        return (
            <p className="text-sm text-muted-foreground">
                {t({
                    en: "The simulated call is not finished, or its verdict was not saved.",
                    fr: "L'appel simulé n'est pas fini, ou son verdict n'a pas été rangé.",
                })}
            </p>
        );
    return (
        <div className="space-y-3 text-sm" data-testid="simulation">
            <p>
                {t({ en: "Scenario", fr: "Scénario" })} : <strong>{simulation.scenario_nom}</strong>
            </p>
            {r.error ? (
                <p className="text-destructive" role="alert">
                    {t({ en: "The simulator failed", fr: "Le simulateur a échoué" })} : {r.error}
                </p>
            ) : null}
            {r.reasoning ? (
                <p className="text-muted-foreground">
                    {t({ en: "Judge", fr: "Juge" })} : {r.reasoning}
                </p>
            ) : null}
            <ul className="space-y-1" data-testid="criteres">
                {r.passed_criteria.map((c) => (
                    <li key={`ok-${c}`}>✓ {c}</li>
                ))}
                {r.failed_criteria.map((c) => (
                    <li key={`ko-${c}`} className="text-destructive">
                        ✗ {c}
                    </li>
                ))}
            </ul>
            <p className="text-muted-foreground">
                {t({
                    en: `Worst turn ${secondes(r.worst_silence_secs)} · median ${secondes(r.median_silence_secs)} · ${r.incidents} incident(s)`,
                    fr: `Pire tour ${secondes(r.worst_silence_secs)} · médiane ${secondes(r.median_silence_secs)} · ${r.incidents} incident(s)`,
                })}
            </p>
            <p className="text-muted-foreground">
                {t({
                    en: `Cost: agent ${r.agent_cost ?? "unpriced"}${r.agent_cost_partial ? " (partial)" : ""} + simulator ${r.caller_cost} (its model calls unpriced)`,
                    fr: `Coût : agent ${r.agent_cost ?? "sans prix"}${r.agent_cost_partial ? " (partiel)" : ""} + simulateur ${r.caller_cost} (ses appels au modèle sans prix)`,
                })}
            </p>
        </div>
    );
}

export function FenetreDuRun({
    workflowId,
    runId,
    recordingKey,
}: {
    workflowId: number;
    runId: number;
    recordingKey?: string | null;
}) {
    const { t } = useLangue();
    const [analyse, setAnalyse] = useState<AnalyseDuRun | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    useEffect(() => {
        let annule = false;
        (async () => {
            try {
                const reponse = await getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet({
                    path: { workflow_id: workflowId, run_id: runId },
                });
                if (annule) return;
                if (reponse.error) {
                    setErreur(detailFromError(reponse.error, "Analysis failed"));
                    return;
                }
                setAnalyse(reponse.data as unknown as AnalyseDuRun);
            } catch (e) {
                if (!annule) setErreur(detailFromError(e, "Analysis failed"));
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId, runId]);

    if (erreur)
        return (
            <Card className="border-border" data-testid="fenetre-du-run">
                <CardContent className="pt-6 text-sm text-destructive" role="alert">
                    {t({ en: "Run analysis unavailable", fr: "Analyse du run indisponible" })} : {erreur}
                </CardContent>
            </Card>
        );
    if (!analyse)
        return (
            <p className="text-sm text-muted-foreground" data-testid="fenetre-du-run-chargement">
                {t({ en: "Loading the run analysis…", fr: "Chargement de l'analyse du run…" })}
            </p>
        );

    const stats = analyse.latency.stats;
    return (
        <div className="space-y-4" data-testid="fenetre-du-run">
            {analyse.simulation ? (
                <Section
                    titre={{ en: "Simulation", fr: "Simulation" }}
                    bloc={{ status: "ok" }}
                    ouverte
                    testId="bloc-simulation"
                    resume={
                        analyse.simulation.resultat
                            ? analyse.simulation.resultat.success
                                ? t({ en: "passed", fr: "réussi" })
                                : t({ en: "failed", fr: "échoué" })
                            : null
                    }
                >
                    <BlocSimulation simulation={analyse.simulation} />
                </Section>
            ) : null}
            <Section titre={{ en: "Summary", fr: "Résumé" }} bloc={analyse.summary} ouverte testId="bloc-summary">
                <BlocResume resume={analyse.summary} incidents={analyse.incidents} />
            </Section>
            <Section
                titre={{ en: "Latency, turn by turn", fr: "Latence, tour par tour" }}
                bloc={analyse.latency}
                ouverte
                testId="bloc-latency"
                resume={
                    stats
                        ? t({
                              en: `median ${secondes(stats.median_silence_secs)}`,
                              fr: `médiane ${secondes(stats.median_silence_secs)}`,
                          })
                        : null
                }
            >
                <BlocLatence latence={analyse.latency} />
            </Section>
            <Section titre={{ en: "Providers", fr: "Fournisseurs" }} bloc={analyse.providers} testId="bloc-providers">
                <BlocFournisseurs fournisseurs={analyse.providers} />
            </Section>
            <Section
                titre={{ en: "Reading modules", fr: "Modules de lecture" }}
                bloc={analyse.reading_modules}
                testId="bloc-reading-modules"
                resume={`${analyse.reading_modules.items?.length ?? 0}`}
            >
                <BlocModules modules={analyse.reading_modules} />
            </Section>
            <Section titre={{ en: "Record", fr: "Fiche" }} bloc={analyse.record} testId="bloc-record">
                <BlocFiche fiche={analyse.record} />
            </Section>
            <Section titre={{ en: "Path", fr: "Parcours" }} bloc={analyse.path} testId="bloc-path">
                <BlocParcours parcours={analyse.path} />
            </Section>
            <Section titre={{ en: "Conversation", fr: "Conversation" }} bloc={analyse.conversation} testId="bloc-conversation">
                <BlocConversation conversation={analyse.conversation} recordingKey={recordingKey} />
            </Section>
            <Section
                titre={{ en: "Incidents", fr: "Incidents" }}
                bloc={analyse.incidents}
                testId="bloc-incidents"
                resume={`${analyse.incidents.items?.length ?? 0}`}
            >
                <BlocIncidents incidents={analyse.incidents} />
            </Section>
        </div>
    );
}
