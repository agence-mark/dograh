"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): the detail of a test. The conversation, and the REASON of each failure written under the
 * agent's reply at fault (B40). The judge's opinion is shown apart and blocks nothing (B43); a person can note it, which calibrates it.
 */
import { useState } from "react";

import { noterLeJugeApiV1BuilderTestsWorkflowIdJugeNotesPost } from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";

import { CRITERES, dateCourte, ORIGINES_DE_TEST, STATUTS_DE_TEST } from "./libelles";
import type { CritereResultat, EssaiResultat, Execution, TestComplet } from "./types";

/** The fault written on the agent's reply number `k` (from 0): the failed criteria that point at it. */
export const fautesDeLaReplique = (criteres: CritereResultat[], k: number) => criteres.filter((c) => !c.reussi && c.rang === k);

function Conversation({ essai }: { essai: EssaiResultat }) {
    const { t } = useLangue();
    let k = -1;
    return (
        <ol className="space-y-1 text-sm" data-testid="conversation-du-test">
            {essai.lignes.map(([role, texte], i) => {
                if (role === "agent") k += 1;
                const fautes = role === "agent" ? fautesDeLaReplique(essai.criteres, k) : [];
                return (
                    <li key={i} className={role === "agent" ? "rounded border p-2" : "p-2 text-muted-foreground"} data-faute={fautes.length > 0 || undefined}>
                        <span className="mr-2 text-xs font-medium">{role === "agent" ? t({ en: "Agent", fr: "Agent" }) : t({ en: "Caller", fr: "Appelant" })}</span>
                        {texte}
                        {fautes.map((f, j) => (
                            <p key={j} className="mt-1 rounded bg-red-50 p-1 text-xs text-red-900 dark:bg-red-950 dark:text-red-200" data-testid="raison-de-l-echec">
                                {f.raison ?? f.detail}
                            </p>
                        ))}
                    </li>
                );
            })}
        </ol>
    );
}

interface Props {
    workflowId: number;
    test: TestComplet;
    resultats: Execution[];
    onObligatoire: (valeur: boolean) => void;
    onSupprimer: () => void;
}

export function DetailDunTest({ workflowId, test, resultats, onObligatoire, onSupprimer }: Props) {
    const { t } = useLangue();
    const [rang, setRang] = useState(0);
    const [essaiChoisi, setEssaiChoisi] = useState(0);
    const [note, setNote] = useState<string | null>(null);
    const execution = resultats[rang];
    const essai = execution?.essais[Math.min(essaiChoisi, (execution?.essais.length ?? 1) - 1)];

    const noter = async (i: number, ok: boolean) => {
        if (!execution) return;
        await noterLeJugeApiV1BuilderTestsWorkflowIdJugeNotesPost({
            path: { workflow_id: workflowId },
            body: { identifiant: `${test.slug}:${execution.le}:${i}`, ok },
        });
        setNote(t({ en: "Noted: it calibrates the judge.", fr: "Noté : cela calibre le juge." }));
    };

    return (
        <section className="space-y-3 rounded border p-4" data-testid="detail-du-test">
            <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-lg font-semibold">{test.nom}</h2>
                <span className="rounded bg-muted px-2 py-0.5 text-xs">{test.origine ? t(ORIGINES_DE_TEST[test.origine] ?? { en: test.origine, fr: test.origine }) : ""}</span>
                <label className="ml-auto flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={test.obligatoire} onChange={(e) => onObligatoire(e.target.checked)} aria-label={t({ en: "Required", fr: "Obligatoire" })} />
                    {t({ en: "Required", fr: "Obligatoire" })}
                </label>
                <Button variant="ghost" size="sm" onClick={onSupprimer}>
                    {t({ en: "Delete", fr: "Supprimer" })}
                </Button>
            </div>
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
                {test.criteres.map((c, i) => (
                    <li key={i}>
                        {t(CRITERES[c.type]?.libelle ?? { en: c.type, fr: c.type })}
                        {c.texte ? ` « ${String(c.texte)} »` : ""}
                        {c.nom ? ` ${String(c.nom)}` : ""}
                        {c.attendue ? ` ${String(c.attendue)}` : ""}
                    </li>
                ))}
            </ul>
            {test.scenario && <p className="text-sm">{test.scenario.but}</p>}
            {test.replique && <p className="text-sm">« {test.replique} »</p>}
            {resultats.length === 0 && <p className="text-sm text-muted-foreground">{t({ en: "Never replayed.", fr: "Jamais rejoué." })}</p>}
            {resultats.length > 0 && execution && (
                <>
                    <div className="flex flex-wrap gap-2" role="tablist">
                        {resultats.map((e, i) => (
                            <button
                                key={e.le}
                                role="tab"
                                aria-selected={i === rang}
                                className={`rounded border px-2 py-1 text-xs ${i === rang ? "bg-muted font-medium" : ""}`}
                                onClick={() => {
                                    setRang(i);
                                    setEssaiChoisi(0);
                                }}
                            >
                                {dateCourte(e.le)} · {e.reussis}/{e.total} · v{e.version ?? "?"}
                            </button>
                        ))}
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {execution.essais.map((e, i) => (
                            <button key={e.numero} className={`rounded border px-2 py-1 text-xs ${i === essaiChoisi ? "bg-muted font-medium" : ""}`} onClick={() => setEssaiChoisi(i)}>
                                {t({ en: "Attempt", fr: "Essai" })} {e.numero} · {e.reussi ? "✓" : "✗"}
                            </button>
                        ))}
                    </div>
                    {essai?.erreur && (
                        <p className="rounded bg-amber-50 p-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200" data-testid="essai-en-erreur">
                            {t({ en: "This attempt could not be played:", fr: "Cet essai n'a pas pu être joué :" })} {essai.erreur}
                        </p>
                    )}
                    {essai && essai.lignes.length > 0 && <Conversation essai={essai} />}
                    {execution.juge && execution.juge.avis.length > 0 && (
                        <div className="space-y-1 rounded border border-dashed p-2 text-sm" data-testid="avis-du-juge">
                            <h3 className="font-medium">{t({ en: "The judge's opinion (blocks nothing)", fr: "L'avis du juge (ne bloque rien)" })}</h3>
                            {execution.juge.avis.map((a, i) => (
                                <div key={i} className="flex flex-wrap items-center gap-2">
                                    <span>{a.question}</span>
                                    <span className="font-medium">{a.ok === null ? t({ en: "no opinion", fr: "pas d'avis" }) : a.ok ? t({ en: "yes", fr: "oui" }) : t({ en: "no", fr: "non" })}</span>
                                    {a.serre && <span className="text-xs text-muted-foreground">({a.passes} {t({ en: "passes, close call", fr: "passes, serré" })})</span>}
                                    <span className="text-xs text-muted-foreground">{a.raison}</span>
                                    <Button variant="ghost" size="sm" onClick={() => void noter(i, true)}>
                                        {t({ en: "I agree", fr: "D'accord" })}
                                    </Button>
                                    <Button variant="ghost" size="sm" onClick={() => void noter(i, false)}>
                                        {t({ en: "I disagree", fr: "Pas d'accord" })}
                                    </Button>
                                </div>
                            ))}
                            {note && <p className="text-xs text-muted-foreground">{note}</p>}
                        </div>
                    )}
                </>
            )}
            {execution && <p className="text-xs text-muted-foreground">{t(STATUTS_DE_TEST[execution.statut].texte)}</p>}
        </section>
    );
}
