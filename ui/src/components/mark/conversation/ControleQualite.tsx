"use client";

/**
 * [.mark] Correctif écran point 7 : l'onglet « Contrôle qualité » d'un appel, en clair (plus de JSON). Lit `annotations.juge`
 * (`api/services/juge/`) : la note, un verdict par critère (réussi, raté, non vérifiable) avec la réplique en cause et sa citation, les
 * étiquettes (critères non réussis) et le rangement dans « À améliorer » (tout critère non réussi d'un vrai appel y entre, `boucle/ingestion.py`).
 * Un appel que le juge n'a pas noté le dit en une phrase ; le JSON reste derrière « Copier ».
 */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { WORKFLOW_RUN_MODES } from "@/constants/workflowRunModes";
import { copyTextToClipboard } from "@/lib/clipboard";

import { LigneNue } from "../fenetre-du-run/FenetreDuRun";
import { type Texte, useLangue } from "../langue/langue";
import { notifier } from "../notifications";
import { libelleEtatDuJuge } from "../reglages-agent/etat-du-juge";

type Verdict = { critere: string; verdict: string; replique: number | null; preuve: string; confiance: number | null };

const VERDICTS: Record<string, Texte> = {
    reussi: { en: "passed", fr: "réussi" },
    rate: { en: "failed", fr: "raté" },
    non_verifiable: { en: "not verifiable", fr: "non vérifiable" },
};

/** Les verdicts lisibles d'une annotation ; ce qui n'a pas la forme attendue est écarté, jamais rendu tel quel. */
export const lireLesVerdicts = (juge: unknown): Verdict[] => {
    const brut = (juge as { verdicts?: unknown } | null | undefined)?.verdicts;
    if (!Array.isArray(brut)) return [];
    return brut
        .filter((v): v is Record<string, unknown> => !!v && typeof v === "object" && typeof (v as Record<string, unknown>).critere === "string")
        .map((v) => ({
            critere: String(v.critere),
            verdict: typeof v.verdict === "string" ? v.verdict : "non_verifiable",
            replique: typeof v.replique === "number" ? v.replique : null,
            preuve: typeof v.preuve === "string" ? v.preuve : "",
            confiance: typeof v.confiance === "number" ? v.confiance : null,
        }));
};

/** Un essai (navigateur, clavier, appelant simulé) n'est jamais estJuge : le juge ne tourne que sur les vrais appels. */
export const estUnEssai = (mode: string | null | undefined) =>
    mode === WORKFLOW_RUN_MODES.SMALL_WEBRTC ||
    mode === WORKFLOW_RUN_MODES.WEBRTC ||
    mode === WORKFLOW_RUN_MODES.TEXTCHAT ||
    mode === WORKFLOW_RUN_MODES.SIMULATED;

export function ControleQualite({
    titre,
    annotations,
    mode,
    note,
}: {
    titre: string;
    annotations: Record<string, unknown> | null;
    mode: string | null | undefined;
    note: number | null;
}) {
    const { t, langue } = useLangue();
    const [copie, setCopie] = useState(false);
    const juge = (annotations?.juge ?? null) as Record<string, unknown> | null;
    const verdicts = lireLesVerdicts(juge);
    const etat = libelleEtatDuJuge(juge?.etat);
    const noteJuge = note ?? (typeof juge?.note === "number" ? juge.note : null);
    const dite = (n: number) => (langue === "fr" ? String(n).replace(".", ",") : String(n));
    const nonReussis = verdicts.filter((v) => v.verdict !== "reussi");
    const estJuge = !etat && juge !== null && (verdicts.length > 0 || noteJuge !== null);

    const copier = async () => {
        try {
            await copyTextToClipboard(JSON.stringify(annotations ?? {}, null, 2));
            setCopie(true);
            setTimeout(() => setCopie(false), 2000);
        } catch {
            notifier.echec({ fr: "Copie impossible.", en: "Could not copy." });
        }
    };

    return (
        <section data-testid="controle-qualite">
            <div className="flex min-h-9 items-center justify-between pb-1">
                <p className="text-base font-semibold">{titre}</p>
                {annotations && Object.keys(annotations).length > 0 && (
                    <Button variant="ghost" size="sm" onClick={copier} className="cursor-pointer gap-2" data-testid="copier-json-qualite">
                        {copie ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        {copie ? t({ en: "Copied", fr: "Copié" }) : t({ en: "Copy as JSON", fr: "Copier le JSON" })}
                    </Button>
                )}
            </div>
            {!estJuge ? (
                <p className="py-3 text-sm text-muted-foreground" data-testid="appel-non-juge">
                    {etat
                        ? t(etat)
                        : estUnEssai(mode)
                          ? t({
                                en: "Call not judged: the judge only reads real calls, not tests made in the browser or on the keyboard.",
                                fr: "Appel non estJuge : le juge ne lit que les vrais appels, pas les essais faits au navigateur ou au clavier.",
                            })
                          : t({
                                en: "Call not judged: no verdict was recorded for it.",
                                fr: "Appel non estJuge : aucun verdict n'a été enregistré pour lui.",
                            })}
                </p>
            ) : (
                <div className="divide-y divide-border">
                    <LigneNue libelle={t({ en: "Judge", fr: "Juge" })} testId="qualite-note">
                        {noteJuge !== null ? (
                            <strong>{dite(noteJuge)} / 5</strong>
                        ) : (
                            <span className="text-muted-foreground">{t({ en: "no mark", fr: "pas de note" })}</span>
                        )}
                        {typeof juge?.modele === "string" && <span className="text-muted-foreground"> · {juge.modele}</span>}
                    </LigneNue>
                    {verdicts.length === 0 && (
                        <LigneNue libelle={t({ en: "Detail", fr: "Détail" })}>
                            <span className="text-muted-foreground">
                                {t({ en: "The verdict by criterion was not kept.", fr: "Le verdict critère par critère n'a pas été gardé." })}
                            </span>
                        </LigneNue>
                    )}
                    {verdicts.map((v, i) => (
                        <LigneNue key={i} libelle={v.critere} testId="qualite-verdict">
                            <span className={v.verdict === "rate" ? "font-medium text-destructive" : "font-medium"}>
                                {t(VERDICTS[v.verdict] ?? VERDICTS.non_verifiable)}
                            </span>
                            {v.replique !== null && (
                                <span className="text-muted-foreground"> · {t({ en: `line ${v.replique}`, fr: `réplique n° ${v.replique}` })}</span>
                            )}
                            {v.preuve && <span className="mt-0.5 block text-muted-foreground">« {v.preuve} »</span>}
                        </LigneNue>
                    ))}
                    {verdicts.length > 0 && (
                        <>
                            <LigneNue libelle={t({ en: "Labels", fr: "Étiquettes" })} testId="qualite-etiquettes">
                                {nonReussis.length === 0 ? (
                                    <span className="text-muted-foreground">{t({ en: "none", fr: "aucune" })}</span>
                                ) : (
                                    <span className="flex flex-wrap gap-1.5">
                                        {nonReussis.map((v, i) => (
                                            <span key={i} className="rounded-full border px-2 py-0.5 text-xs">
                                                {v.critere}
                                            </span>
                                        ))}
                                    </span>
                                )}
                            </LigneNue>
                            <LigneNue libelle={t({ en: "Sent to « To improve »", fr: "Envoyé dans « À améliorer »" })} testId="qualite-a-ameliorer">
                                {nonReussis.length === 0
                                    ? t({ en: "no", fr: "non" })
                                    : t({
                                          en: `yes, ${nonReussis.length} criteria`,
                                          fr: `oui, ${nonReussis.length} critère${nonReussis.length > 1 ? "s" : ""}`,
                                      })}
                            </LigneNue>
                        </>
                    )}
                </div>
            )}
        </section>
    );
}
