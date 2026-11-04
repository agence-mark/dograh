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
import { ChevronDown, Timer } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet } from "@/client";
import { Card, CardContent } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { useAuth } from "@/lib/auth";
import { getSignedUrl } from "@/lib/files";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";
import { SectionApresAppel } from "./SectionApresAppel";
import type {
    AnalyseDuRun,
    Bloc,
    Chronometre,
    Conversation,
    EtapesDuTour,
    Fiche,
    Fournisseurs,
    Incidents,
    Latence,
    Modules,
    NatureDePasse,
    Parcours,
    ReseauEtConnexions,
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
    outage_fallback: { en: "Outage: call handed over or call-back promised", fr: "Panne : appel renvoyé ou rappel promis" },
    model_timeout: { en: "Model too slow to answer", fr: "Modèle trop lent à répondre" },
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
        <section className="border-b border-border last:border-0" data-testid={testId}>
            <Collapsible open={ouvert} onOpenChange={setOuvert}>
                <CollapsibleTrigger className="flex w-full cursor-pointer items-center justify-between gap-4 py-3 text-left">
                    <h3 className="text-base font-semibold">{t(titre)}</h3>
                    <span className="flex items-center gap-3 text-sm text-muted-foreground">
                        {bloc.status === "ok" ? resume : null}
                        <ChevronDown className={cn("h-4 w-4 transition-transform", ouvert && "rotate-180")} />
                    </span>
                </CollapsibleTrigger>
                <CollapsibleContent>
                    <div className="pb-4">{bloc.status === "ok" ? children : <EtatDuBloc bloc={bloc} />}</div>
                </CollapsibleContent>
            </Collapsible>
        </section>
    );
}

/** Une ligne « libellé · valeur » de la maquette : tableau nu, trait fin entre les lignes, jamais de cadre. */
export function LigneNue({ libelle, children, testId, etroit }: { libelle: ReactNode; children: ReactNode; testId?: string; etroit?: boolean }) {
    return (
        <div className="flex gap-4 py-2.5 text-sm" data-testid={testId}>
            <span className={cn("shrink-0 text-muted-foreground", etroit ? "w-28" : "w-44")}>{libelle}</span>
            <span className="min-w-0 flex-1">{children}</span>
        </div>
    );
}

/** Le résumé de l'appel, nu (sans carte) : ce que l'en-tête ne dit pas déjà. Les précisions vont dans un « ! ». */
function BlocResume({ resume, incidents }: { resume: Resume; incidents: Incidents }) {
    const { t } = useLangue();
    if (resume.status !== "ok") return <EtatDuBloc bloc={resume} />;
    const nombre = resume.incident_count ?? 0;
    const versionLue = resume.version && resume.version.status !== "not_captured" ? resume.version : null;
    return (
        <div className="divide-y divide-border" data-testid="fenetre-resume">
            <LigneNue etroit libelle={t({ en: "Code", fr: "Code" })} testId="fenetre-version">
                {versionLue ? (
                    <>
                        <code>{versionLue.app_version ?? "–"}</code> · {t({ en: "deployed commit", fr: "commit déployé" })} :{" "}
                        <code>{versionLue.commit ? versionLue.commit.slice(0, 8) : "–"}</code> ·{" "}
                        {t({ en: "agent version", fr: "version de l'agent" })} : <code>{versionLue.version_number ?? "–"}</code> (
                        <code>{versionLue.definition_status ?? "–"}</code>)
                    </>
                ) : (
                    <span className="inline-flex items-center gap-2 text-muted-foreground">
                        –
                        <Info>
                            {t({
                                en: "Code version not captured: the run is older than this capture.",
                                fr: "Version du code non captée : l'appel est antérieur à cette capture.",
                            })}
                        </Info>
                    </span>
                )}
            </LigneNue>
            <LigneNue etroit libelle={t({ en: "Estimated cost", fr: "Coût estimé" })} testId="fenetre-cout">
                {resume.cost?.status === "ok" ? (
                    <>
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
                    <span className="inline-flex items-center gap-2 text-muted-foreground">
                        {t({ en: "not captured", fr: "non capté" })}
                        <Info>
                            {t({
                                en: "No price table in the organization settings, or no consumption recorded.",
                                fr: "Pas de table des prix dans les paramètres de l'organisation, ou aucune consommation enregistrée.",
                            })}
                        </Info>
                    </span>
                )}
            </LigneNue>
            {nombre > 0 && incidents.status === "ok" && (
                <LigneNue etroit libelle={t({ en: "Incidents", fr: "Incidents" })}>
                    <span className="font-medium text-destructive" role="alert">
                        {t({
                            en: `${nombre} incident(s) on this call: see Incidents.`,
                            fr: `${nombre} incident(s) sur cet appel : voir Incidents.`,
                        })}
                    </span>
                </LigneNue>
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

const ETAPES: { cle: keyof EtapesDuTour; titre: Texte }[] = [
    { cle: "turn_closed", titre: { en: "turn closed", fr: "fin de tour" } },
    { cle: "request_sent", titre: { en: "request sent", fr: "requête partie" } },
    { cle: "first_model_word", titre: { en: "first model word", fr: "premier mot du modèle" } },
    { cle: "first_sentence", titre: { en: "first sentence", fr: "première phrase" } },
    { cle: "sent_to_voice", titre: { en: "sent to the voice", fr: "envoi à la voix" } },
    { cle: "first_sound", titre: { en: "first sound", fr: "premier son" } },
];

/** One row per turn: the seconds from the caller's last word to each stage, and M2 (first sound). */
function BlocChronometre({ chrono }: { chrono: Chronometre }) {
    const { t } = useLangue();
    const controles = chrono.controls;
    return (
        <div className="space-y-3 text-sm">
            <p data-testid="chrono-controles">
                {t({
                    en: `Medians: first text (M1) ${secondes(controles?.m1_median_secs)} · first sound out of the voice (M2) ${secondes(controles?.m2_median_secs)} · heard on the recording ${secondes(controles?.heard_median_secs)}. What M2 does not see yet (audio output to the caller's ear): ${secondes(controles?.heard_minus_m2_secs)}.`,
                    fr: `Médianes : premier texte (M1) ${secondes(controles?.m1_median_secs)} · premier son sorti de la voix (M2) ${secondes(controles?.m2_median_secs)} · entendu sur l'enregistrement ${secondes(controles?.heard_median_secs)}. Ce que M2 ne voit pas encore (sortie audio jusqu'à l'oreille) : ${secondes(controles?.heard_minus_m2_secs)}.`,
                })}
            </p>
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "Seconds from the caller's last word (Soniox) to each stage of the reply.",
                    fr: "Secondes depuis le dernier mot de l'appelant (Soniox) jusqu'à chaque étape de la réponse.",
                })}
            </p>
            <div className="overflow-x-auto">
                <table className="w-full text-xs">
                    <thead>
                        <tr className="border-b border-border text-left text-muted-foreground">
                            <th className="py-1 pr-3 font-medium">{t({ en: "Turn", fr: "Tour" })}</th>
                            {ETAPES.map((e) => (
                                <th key={e.cle} className="py-1 pr-3 font-medium">
                                    {t(e.titre)}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {(chrono.turns ?? []).map((tour, i) => (
                            <tr key={i} data-testid="tour-chronometre" className="border-b border-border last:border-0">
                                <td className="py-1 pr-3" title={tour.step}>
                                    {tour.turn ?? "?"}
                                </td>
                                {tour.measured ? (
                                    ETAPES.map((e) => (
                                        <td key={e.cle} className={cn("py-1 pr-3", e.cle === "first_sound" && "font-medium")}>
                                            {secondes(tour.stages[e.cle])}
                                        </td>
                                    ))
                                ) : (
                                    <td colSpan={ETAPES.length} className="py-1 text-muted-foreground">
                                        {t({ en: "not measured", fr: "non mesuré" })} :{" "}
                                        {t(RAISONS[tour.not_measured_reason ?? ""] ?? { en: "unknown", fr: "inconnu" })}
                                    </td>
                                )}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

const entier = (valeur: number | null | undefined) => (typeof valeur === "number" ? `${valeur}` : "–");
const millisecondes = (valeur: number | null | undefined) =>
    typeof valeur === "number" ? `${valeur.toFixed(1)} ms` : "–";

/** Provider connections (model reused or opened, transcription, voice) and the audio link quality. */
function BlocReseau({ reseau }: { reseau: ReseauEtConnexions }) {
    const { t } = useLangue();
    const liaison = reseau.link;
    const bilan = liaison && liaison.status === "ok" ? liaison : null;
    return (
        <div className="space-y-2 text-sm">
            <ul data-testid="reseau-connexions" className="space-y-1">
                {Object.entries(reseau.providers ?? {}).map(([brique, c]) => (
                    <li key={brique}>
                        {t(BRIQUES[brique] ?? { en: brique, fr: brique })} :{" "}
                        {t({
                            en: `${c.connected} connection(s), first one after ${secondes(c.first_connect_secs)} · ${c.disconnected} disconnection(s) · ${c.errors} error(s)`,
                            fr: `${c.connected} connexion(s), la première après ${secondes(c.first_connect_secs)} · ${c.disconnected} coupure(s) · ${c.errors} erreur(s)`,
                        })}
                    </li>
                ))}
                <li>
                    {t({ en: "Model", fr: "Modèle" })} :{" "}
                    {reseau.model
                        ? t({
                              en: `${reseau.model.opened} connection(s) opened, ${reseau.model.reused} reused (${reseau.model.items
                                  .map((x) => `${x.agent ?? "?"}: ${x.event === "opened" ? "opened" : "reused"}`)
                                  .join(", ")})`,
                              fr: `${reseau.model.opened} connexion(s) ouverte(s), ${reseau.model.reused} reprise(s) (${reseau.model.items
                                  .map((x) => `${x.agent ?? "?"} : ${x.event === "opened" ? "ouverte" : "reprise"}`)
                                  .join(", ")})`,
                          })
                        : t({ en: "not captured", fr: "non capté" })}
                </li>
            </ul>
            <p data-testid="reseau-liaison">
                {bilan
                    ? t({
                          en: `Audio link (${bilan.samples ?? 0} samples): caller's voice, ${entier(bilan.last?.inbound?.packets_lost)} packets lost, jitter ${millisecondes(bilan.last?.inbound?.jitter_ms)} · agent's voice as the browser saw it, ${entier(bilan.last?.outbound?.packets_lost)} packets lost, jitter ${millisecondes(bilan.last?.outbound?.jitter_ms)} · worst round trip ${millisecondes(bilan.worst?.round_trip_ms)}`,
                          fr: `Liaison audio (${bilan.samples ?? 0} relevés) : voix de l'appelant, ${entier(bilan.last?.inbound?.packets_lost)} paquets perdus, gigue ${millisecondes(bilan.last?.inbound?.jitter_ms)} · voix de l'agent vue par le navigateur, ${entier(bilan.last?.outbound?.packets_lost)} paquets perdus, gigue ${millisecondes(bilan.last?.outbound?.jitter_ms)} · pire aller-retour ${millisecondes(bilan.worst?.round_trip_ms)}`,
                      })
                    : t({
                          en: "Audio link: not captured (phone call, or run older than this capture).",
                          fr: "Liaison audio : non captée (appel téléphonique, ou run antérieur à cette capture).",
                      })}
            </p>
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
                        <code>{typeof etape === "string" ? etape : [etape.agent, etape.etape].filter((p) => p != null && p !== "").join(" › ")}</code>
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

/** Les lignes d'une conversation, à la forme de la maquette : qui · étape, la latence à droite, le texte dessous. */
function BlocConversation({
    conversation,
    recordingKey,
    latence,
    choisi,
    onChoisir,
    incidents,
}: {
    conversation: Conversation;
    recordingKey?: string | null;
    latence?: Latence;
    choisi?: number | null;
    onChoisir?: (tour: number | null) => void;
    incidents?: Incidents;
}) {
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
    const lignes = conversation.lines ?? [];
    const tourDeLatence = (tour: number | null) => (tour == null ? undefined : latence?.turns?.find((x) => x.turn === tour));
    const faute = (tour: number | null) =>
        tour != null && (incidents?.items ?? []).some((i) => i.turn === tour && i.fatal);
    return (
        <div className="text-sm">
            {(conversation.marks ?? []).length > 0 && (
                <ul className="space-y-1 pb-3" data-testid="marques-de-conversation">
                    {(conversation.marks ?? []).map((m, i) => (
                        <li key={i} className="text-muted-foreground">
                            {m.at_secs == null ? "–" : `${m.at_secs.toFixed(1)} s`} · {t({ en: "Turn", fr: "Tour" })}{" "}
                            {m.turn ?? "?"} · {t(MARQUES[m.kind] ?? { en: m.kind, fr: m.kind })}
                        </li>
                    ))}
                </ul>
            )}
            <audio ref={audio} controls={Boolean(adresse)} className={cn("mb-3 w-full", !adresse && "hidden")} />
            <ul className="divide-y divide-border">
                {lignes.map((ligne, i) => {
                    const tour = tourDeLatence(ligne.turn);
                    const lente = Boolean(tour?.slow);
                    const choisie = choisi != null && ligne.turn === choisi;
                    return (
                        <li key={i}>
                            <button
                                type="button"
                                data-testid="ligne-de-conversation"
                                aria-pressed={choisie}
                                title={
                                    recordingKey
                                        ? t({
                                              en: "Select the turn, play the recording from here",
                                              fr: "Choisir ce tour, écouter l'enregistrement à partir d'ici",
                                          })
                                        : undefined
                                }
                                className={cn(
                                    "w-full cursor-pointer px-3 py-3 text-left hover:bg-muted/40",
                                    choisie && "bg-(--acc-soft) hover:bg-(--acc-soft)",
                                    faute(ligne.turn) && "border-l-2 border-destructive",
                                )}
                                onClick={() => {
                                    onChoisir?.(ligne.turn);
                                    void ecouter(ligne.start_secs);
                                }}
                            >
                                <span className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                                    <span
                                        className={cn(
                                            "font-medium",
                                            ligne.speaker === "agent" ? "text-(--acc-text)" : "text-foreground",
                                        )}
                                    >
                                        {ligne.speaker === "caller"
                                            ? t({ en: "Caller", fr: "Appelant" })
                                            : t({ en: "Agent", fr: "Agent" })}
                                    </span>
                                    {tour?.step && <span>· {tour.step}</span>}
                                    {ligne.start_secs != null && (
                                        <span className="tabular-nums">· {ligne.start_secs.toFixed(1)} s</span>
                                    )}
                                    {ligne.speaker === "agent" && tour?.measured && tour.silence_secs != null && (
                                        <span
                                            className={cn(
                                                "ml-auto flex items-center gap-1 tabular-nums",
                                                lente && "text-(--marque-danger-texte)",
                                            )}
                                        >
                                            <Timer className="size-3" /> {tour.silence_secs.toFixed(2)} s
                                        </span>
                                    )}
                                </span>
                                <span className="block text-sm text-foreground">{ligne.text}</span>
                            </button>
                        </li>
                    );
                })}
            </ul>
        </div>
    );
}

const ETAPES_DU_TOUR: { cle: keyof EtapesDuTour; titre: Texte }[] = [
    { cle: "turn_closed", titre: { en: "End-of-turn wait", fr: "Attente de fin de tour" } },
    { cle: "request_sent", titre: { en: "Request sent", fr: "Requête partie" } },
    { cle: "first_model_word", titre: { en: "First model word", fr: "Premier mot du modèle" } },
    { cle: "first_sentence", titre: { en: "First sentence", fr: "Première phrase" } },
    { cle: "sent_to_voice", titre: { en: "Sent to the voice", fr: "Envoi à la voix" } },
    { cle: "first_sound", titre: { en: "First sound", fr: "Premier son" } },
];

/** La durée de chaque étape d'un tour : l'écart entre deux jalons du chronomètre (les jalons sont comptés depuis le dernier mot de l'appelant). */
export function etapesDuTour(jalons: EtapesDuTour): { cle: keyof EtapesDuTour; secs: number | null }[] {
    let precedent = 0;
    return ETAPES_DU_TOUR.map(({ cle }) => {
        const valeur = jalons[cle];
        if (typeof valeur !== "number") return { cle, secs: null };
        const secs = Math.max(0, valeur - precedent);
        precedent = valeur;
        return { cle, secs };
    });
}

/** Un bloc de la colonne de droite : cadre léger de la maquette, titre, lignes. */
function BlocDeColonne({ titre, children, testId }: { titre: ReactNode; children: ReactNode; testId: string }) {
    return (
        <div className="space-y-2 rounded-xl border border-border bg-card p-4 text-sm" data-testid={testId}>
            <p className="font-medium">{titre}</p>
            {children}
        </div>
    );
}

type TourDeChrono = NonNullable<Chronometre["turns"]>[number];

function BlocDuTour({ chrono }: { chrono: TourDeChrono }) {
    const { t } = useLangue();
    const etapes = etapesDuTour(chrono.stages);
    const plafond = Math.max(0.5, ...etapes.map((e) => e.secs ?? 0));
    return (
        <BlocDeColonne titre={t({ en: "This turn, step by step", fr: "Ce tour, étape par étape" })} testId="colonne-tour">
            {chrono.measured ? (
                etapes.map((e) => (
                    <div key={e.cle} className="flex items-center gap-2">
                        <span className="flex-1 text-muted-foreground">
                            {t(ETAPES_DU_TOUR.find((x) => x.cle === e.cle)!.titre)}
                        </span>
                        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
                            <div
                                className="h-full bg-(--acc)"
                                style={{ width: `${Math.min(100, ((e.secs ?? 0) / plafond) * 100)}%` }}
                            />
                        </div>
                        <span className="w-14 text-right tabular-nums">{e.secs == null ? "–" : secondes(e.secs)}</span>
                    </div>
                ))
            ) : (
                <p className="text-muted-foreground">
                    {t({ en: "not measured", fr: "non mesuré" })} :{" "}
                    {t(RAISONS[chrono.not_measured_reason ?? ""] ?? { en: "unknown", fr: "inconnu" })}
                </p>
            )}
        </BlocDeColonne>
    );
}

function BlocFicheDeColonne({ fiche }: { fiche: Fiche }) {
    const { t } = useLangue();
    const champs = (fiche.fields ?? []).filter((c) => !c.empty);
    if (fiche.status !== "ok" || champs.length === 0) return null;
    return (
        <BlocDeColonne titre={t({ en: "Call record", fr: "Fiche de l'appel" })} testId="colonne-fiche">
            {champs.map((c) => (
                <div key={c.name} className="flex items-center gap-2">
                    <span className="w-24 shrink-0 truncate text-muted-foreground" title={c.name}>
                        {c.name}
                    </span>
                    <span className="min-w-0 flex-1 break-words">{texteDeValeur(c.value)}</span>
                    <span className="text-xs text-(--marque-succes-texte)">
                        {c.sure === false ? t({ en: "To confirm", fr: "À confirmer" }) : (c.source ?? "")}
                    </span>
                </div>
            ))}
        </BlocDeColonne>
    );
}

/**
 * [.mark] V1b : l'onglet Transcription de la page d'une conversation, à la forme de la maquette : la transcription à
 * gauche, à droite « Ce tour, étape par étape » (le tour choisi dans la transcription), la fiche de l'appel et
 * l'après-appel.
 */
export function VueTranscription({
    workflowId,
    runId,
    recordingKey,
    lue,
    avant,
}: {
    workflowId: number;
    runId: number;
    recordingKey?: string | null;
    lue: { analyse: AnalyseDuRun | null; erreur: string | null };
    /** Ce que la page met au-dessus de la transcription (créer un test, téléchargements). */
    avant?: ReactNode;
}) {
    const { t } = useLangue();
    const { analyse, erreur } = lue;
    const [choisi, setChoisi] = useState<number | null | undefined>(undefined);
    if (erreur)
        return (
            <p className="text-sm text-destructive" role="alert" data-testid="fenetre-du-run">
                {t({ en: "Run analysis unavailable", fr: "Analyse du run indisponible" })} : {erreur}
            </p>
        );
    if (!analyse)
        return (
            <p className="text-sm text-muted-foreground" data-testid="fenetre-du-run-chargement">
                {t({ en: "Loading the run analysis…", fr: "Chargement de l'analyse du run…" })}
            </p>
        );
    // Par défaut : le tour le plus lent (là où l'on regarde en premier), sinon le premier tour mesuré.
    const tours = analyse.latency.turns ?? [];
    const parDefaut = tours.find((x) => x.slow)?.turn ?? tours.find((x) => x.measured)?.turn ?? null;
    const tourChoisi = choisi === undefined ? parDefaut : choisi;
    const chrono = tourChoisi == null ? undefined : analyse.chrono?.turns?.find((x) => x.turn === tourChoisi);
    return (
        <div className="grid gap-10 lg:grid-cols-[1fr_360px]" data-testid="vue-transcription">
            <div className="min-w-0 space-y-4">
                {avant}
                <p className="text-base font-semibold">{t({ en: "Transcript", fr: "Transcription" })}</p>
                {analyse.conversation.status === "ok" ? (
                    <BlocConversation
                        conversation={analyse.conversation}
                        recordingKey={recordingKey}
                        latence={analyse.latency}
                        choisi={tourChoisi}
                        onChoisir={setChoisi}
                        incidents={analyse.incidents}
                    />
                ) : (
                    <EtatDuBloc bloc={analyse.conversation} />
                )}
            </div>
            <div className="space-y-4" data-testid="colonne-de-droite">
                <section data-testid="bloc-summary">
                    <p className="pb-1 font-medium">{t({ en: "Summary", fr: "Résumé" })}</p>
                    <BlocResume resume={analyse.summary} incidents={analyse.incidents} />
                </section>
                {chrono && <BlocDuTour chrono={chrono} />}
                <BlocFicheDeColonne fiche={analyse.record} />
                <SectionApresAppel workflowId={workflowId} runId={runId} />
            </div>
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

/** Les blocs de la fenêtre du run, nommés pour que la page d'une conversation les range dans ses onglets (U3). */
export type BlocDuRun =
    | "simulation"
    | "resume"
    | "apres-appel"
    | "latence"
    | "chrono"
    | "reseau"
    | "fournisseurs"
    | "modules"
    | "fiche"
    | "parcours"
    | "conversation"
    | "incidents";

/** L'analyse du run (`GET /workflow/{id}/runs/{run}/analyse`), lue une fois : plusieurs onglets la partagent. */
export function useAnalyseDuRun(workflowId: number, runId: number, actif = true) {
    const [analyse, setAnalyse] = useState<AnalyseDuRun | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    // K2b : la lecture attend que l'authentification soit prête (sinon la requête part sans jeton : « Authorization header required »).
    const { loading: authEnCours, user } = useAuth();
    const pret = !authEnCours && !!user;

    useEffect(() => {
        if (!actif || !pret) return;
        let annule = false;
        (async () => {
            try {
                const reponse = await getWorkflowRunAnalyseApiV1WorkflowWorkflowIdRunsRunIdAnalyseGet({
                    path: { workflow_id: workflowId, run_id: runId },
                });
                if (annule) return;
                if (reponse.error) {
                    setErreur(echecAffiche(reponse.error));
                    return;
                }
                setAnalyse(reponse.data as unknown as AnalyseDuRun);
            } catch (e) {
                if (!annule) setErreur(echecAffiche(e));
            }
        })();
        return () => {
            annule = true;
        };
    }, [workflowId, runId, actif, pret]);

    return { analyse, erreur };
}

export function FenetreDuRun({
    workflowId,
    runId,
    recordingKey,
    blocs,
    lue,
}: {
    workflowId: number;
    runId: number;
    recordingKey?: string | null;
    /** Seulement ces blocs (U3 : un onglet de la conversation). Absent = tous, comme avant. */
    blocs?: BlocDuRun[];
    /** L'analyse déjà lue par la page (évite une seconde lecture quand plusieurs onglets montrent des blocs). */
    lue?: { analyse: AnalyseDuRun | null; erreur: string | null };
}) {
    const { t } = useLangue();
    const propre = useAnalyseDuRun(workflowId, runId, !lue);
    const { analyse, erreur } = lue ?? propre;
    const voir = (bloc: BlocDuRun) => !blocs || blocs.includes(bloc);

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
            {voir("simulation") && analyse.simulation ? (
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
            {voir("resume") && (
                <Section titre={{ en: "Summary", fr: "Résumé" }} bloc={analyse.summary} ouverte testId="bloc-summary">
                    <BlocResume resume={analyse.summary} incidents={analyse.incidents} />
                </Section>
            )}
            {/* [.mark] l-agent-travaille, L4 (A9): shown only when the agent uses the after-call. */}
            {voir("apres-appel") && <SectionApresAppel workflowId={workflowId} runId={runId} />}
            {voir("latence") && (
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
            )}
            {voir("chrono") && (
                <Section
                    titre={{ en: "Turn stopwatch", fr: "Chronomètre par tour" }}
                    bloc={analyse.chrono ?? { status: "not_captured" }}
                    testId="bloc-chrono"
                    resume={t({
                        en: `M2 median ${secondes(analyse.chrono?.controls?.m2_median_secs)}`,
                        fr: `M2 médiane ${secondes(analyse.chrono?.controls?.m2_median_secs)}`,
                    })}
                >
                    {analyse.chrono && <BlocChronometre chrono={analyse.chrono} />}
                </Section>
            )}
            {voir("reseau") && (
                <Section
                    titre={{ en: "Connections and network", fr: "Connexions et réseau" }}
                    bloc={analyse.network ?? { status: "not_captured" }}
                    testId="bloc-network"
                >
                    {analyse.network && <BlocReseau reseau={analyse.network} />}
                </Section>
            )}
            {voir("fournisseurs") && (
                <Section titre={{ en: "Providers", fr: "Fournisseurs" }} bloc={analyse.providers} testId="bloc-providers">
                    <BlocFournisseurs fournisseurs={analyse.providers} />
                </Section>
            )}
            {voir("modules") && (
                <Section
                    titre={{ en: "Reading modules", fr: "Modules de lecture" }}
                    bloc={analyse.reading_modules}
                    testId="bloc-reading-modules"
                    resume={`${analyse.reading_modules.items?.length ?? 0}`}
                >
                    <BlocModules modules={analyse.reading_modules} />
                </Section>
            )}
            {voir("fiche") && (
                <Section titre={{ en: "Record", fr: "Fiche" }} bloc={analyse.record} testId="bloc-record">
                    <BlocFiche fiche={analyse.record} />
                </Section>
            )}
            {voir("parcours") && (
                <Section titre={{ en: "Path", fr: "Parcours" }} bloc={analyse.path} testId="bloc-path">
                    <BlocParcours parcours={analyse.path} />
                </Section>
            )}
            {voir("conversation") && (
                <Section titre={{ en: "Conversation", fr: "Conversation" }} bloc={analyse.conversation} testId="bloc-conversation">
                    <BlocConversation conversation={analyse.conversation} recordingKey={recordingKey} latence={analyse.latency} incidents={analyse.incidents} />
                </Section>
            )}
            {voir("incidents") && (
                <Section
                    titre={{ en: "Incidents", fr: "Incidents" }}
                    bloc={analyse.incidents}
                    testId="bloc-incidents"
                    resume={`${analyse.incidents.items?.length ?? 0}`}
                >
                    <BlocIncidents incidents={analyse.incidents} />
                </Section>
            )}
        </div>
    );
}
