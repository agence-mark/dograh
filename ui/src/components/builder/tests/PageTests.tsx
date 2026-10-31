"use client";

/**
 * [.mark] builder-agent-vocal (lot 6): the « Tests and corrections » page of an agent (`/workflow/<id>/tests`).
 *
 * One page for the whole loop: what blocks the publication (the prompt check and the required tests), the tests by folder with
 * their last run, the replay of the WHOLE suite (B38), the detail of a test with the reason written on the faulty reply (B40),
 * the diagnosis before any correction (B39), the history of the corrections with the way back, and the export for the lab.
 */
import { useCallback, useEffect, useState } from "react";

import {
    changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch,
    etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet,
    exporterLesTestsApiV1BuilderTestsWorkflowIdExportGet,
    historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet,
    lireLesTestsApiV1BuilderTestsWorkflowIdGet,
    lireUnTestApiV1BuilderTestsWorkflowIdSlugGet,
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost,
    retourArriereApiV1BuilderTestsWorkflowIdCorrectionsCorrectionIdRetourPost,
    supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete,
} from "@/client";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { DetailDunTest } from "./DetailDunTest";
import { CAUSES, dateCourte, STATUTS_DE_TEST } from "./libelles";
import { NouveauTest } from "./NouveauTest";
import type { Correction, EtatDePublication, Execution, ResultatDeSuite, ResumeDeTest, TestComplet } from "./types";

/** The tests grouped by folder, folders and tests in the order they come. */
export function parDossier(tests: ResumeDeTest[]): Array<[string, ResumeDeTest[]]> {
    const groupes = new Map<string, ResumeDeTest[]>();
    for (const t of tests) groupes.set(t.dossier || "", [...(groupes.get(t.dossier || "") ?? []), t]);
    return [...groupes.entries()];
}

export function PageTests({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [tests, setTests] = useState<ResumeDeTest[] | null>(null);
    const [publication, setPublication] = useState<EtatDePublication | null>(null);
    const [corrections, setCorrections] = useState<Correction[]>([]);
    const [suite, setSuite] = useState<ResultatDeSuite | null>(null);
    const [choisi, setChoisi] = useState<string | null>(null);
    const [detail, setDetail] = useState<{ test: TestComplet; resultats: Execution[] } | null>(null);
    const [creation, setCreation] = useState(false);
    const [enCours, setEnCours] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const [a, b, c] = await Promise.all([
            lireLesTestsApiV1BuilderTestsWorkflowIdGet({ path: { workflow_id: workflowId } }),
            etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet({ path: { workflow_id: workflowId } }),
            historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet({ path: { workflow_id: workflowId } }),
        ]);
        if (a.error) {
            setErreur(detailFromError(a.error, "The tests could not be read"));
            return;
        }
        setErreur(null);
        setTests((a.data as { tests: ResumeDeTest[] }).tests);
        if (!b.error) setPublication(b.data as EtatDePublication);
        if (!c.error) setCorrections((c.data as { corrections: Correction[] }).corrections);
    }, [workflowId]);

    useEffect(() => {
        void charger();
    }, [charger]);

    useEffect(() => {
        if (!choisi) {
            setDetail(null);
            return;
        }
        void lireUnTestApiV1BuilderTestsWorkflowIdSlugGet({ path: { workflow_id: workflowId, slug: choisi } }).then((r) => {
            if (r.error) setErreur(detailFromError(r.error, "The test could not be read"));
            else setDetail(r.data as { test: TestComplet; resultats: Execution[] });
        });
    }, [choisi, workflowId, tests]);

    const rejouer = async () => {
        setEnCours(true);
        setMessage(null);
        const r = await rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost({ path: { workflow_id: workflowId }, body: { repetitions: 3 } });
        setEnCours(false);
        if (r.error) {
            setErreur(detailFromError(r.error, "The suite could not be replayed"));
            return;
        }
        setSuite(r.data as ResultatDeSuite);
        await charger();
    };

    const exporter = async () => {
        const r = await exporterLesTestsApiV1BuilderTestsWorkflowIdExportGet({ path: { workflow_id: workflowId } });
        if (r.error) {
            setErreur(detailFromError(r.error, "The export failed"));
            return;
        }
        const lien = document.createElement("a");
        lien.href = URL.createObjectURL(new Blob([JSON.stringify(r.data, null, 2)], { type: "application/json" }));
        lien.download = `tests-agent-${workflowId}.json`;
        lien.click();
        URL.revokeObjectURL(lien.href);
    };

    const changerObligatoire = async (slug: string, obligatoire: boolean) => {
        const r = await changerUnTestApiV1BuilderTestsWorkflowIdSlugPatch({ path: { workflow_id: workflowId, slug }, body: { obligatoire } });
        if (r.error) setErreur(detailFromError(r.error, "The test was not changed"));
        else await charger();
    };

    const supprimer = async (slug: string) => {
        const r = await supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete({ path: { workflow_id: workflowId, slug } });
        if (r.error) setErreur(detailFromError(r.error, "The test was not deleted"));
        else {
            setChoisi(null);
            await charger();
        }
    };

    const revenir = async (id: string) => {
        const r = await retourArriereApiV1BuilderTestsWorkflowIdCorrectionsCorrectionIdRetourPost({ path: { workflow_id: workflowId, correction_id: id } });
        if (r.error) {
            setErreur(detailFromError(r.error, "The rollback failed"));
            return;
        }
        setMessage((r.data as { message?: string }).message ?? null);
        await charger();
    };

    return (
        <div className="space-y-5" data-testid="page-tests">
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {publication?.brouillon && <BandeauDePublication etat={publication} />}
            <div className="flex flex-wrap items-center gap-2">
                <Button disabled={enCours || (tests?.length ?? 0) === 0} onClick={() => void rejouer()}>
                    {enCours ? t({ en: "Replaying…", fr: "Rejeu en cours…" }) : t({ en: "Replay the whole suite", fr: "Rejouer toute la suite" })}
                </Button>
                <Button variant="outline" onClick={() => setCreation((c) => !c)}>
                    {t({ en: "New test", fr: "Nouveau test" })}
                </Button>
                <Button variant="outline" disabled={(tests?.length ?? 0) === 0} onClick={() => void exporter()}>
                    {t({ en: "Export for the lab", fr: "Exporter pour le labo" })}
                </Button>
            </div>
            {message && <p className="text-sm text-muted-foreground">{message}</p>}
            {creation && (
                <NouveauTest
                    workflowId={workflowId}
                    onFermer={() => setCreation(false)}
                    onCree={(slug) => {
                        setCreation(false);
                        setChoisi(slug || null);
                        void charger();
                    }}
                />
            )}
            {suite && <ResultatDeLaSuite suite={suite} />}
            {tests !== null && tests.length === 0 && (
                <p className="rounded border p-4 text-sm text-muted-foreground" data-testid="aucun-test">
                    {t({
                        en: "No test yet. Create one from a reply of a call (button on the call page, or from « To triage »), by hand, or ask the builder to write them from the client sheet.",
                        fr: "Aucun test. Créez-en un depuis une réplique d'un appel (bouton sur la page de l'appel, ou depuis « À trier »), à la main, ou demandez au builder de les écrire depuis la fiche du client.",
                    })}
                </p>
            )}
            {tests && parDossier(tests).map(([dossier, lignes]) => (
                <section key={dossier} className="space-y-1" data-testid="dossier-de-tests">
                    <h2 className="text-sm font-semibold text-muted-foreground">{dossier || t({ en: "No folder", fr: "Sans dossier" })}</h2>
                    <ul className="space-y-1">
                        {lignes.map((l) => (
                            <li key={l.slug}>
                                <button
                                    className={`flex w-full flex-wrap items-center gap-2 rounded border p-2 text-left text-sm ${choisi === l.slug ? "bg-muted" : ""}`}
                                    onClick={() => setChoisi(l.slug)}
                                >
                                    <span className="font-medium">{l.nom}</span>
                                    {l.obligatoire && <span className="rounded bg-red-100 px-1.5 text-xs text-red-900 dark:bg-red-950 dark:text-red-200">{t({ en: "required", fr: "obligatoire" })}</span>}
                                    <span className="text-xs text-muted-foreground">{l.genre === "conversation" ? t({ en: "conversation", fr: "conversation" }) : t({ en: "reply", fr: "réplique" })}</span>
                                    <span className="ml-auto text-xs">
                                        {l.derniere ? (
                                            <>
                                                <span className={`rounded px-1.5 py-0.5 ${STATUTS_DE_TEST[l.derniere.statut].classe}`}>
                                                    {l.derniere.reussis}/{l.derniere.total}
                                                </span>{" "}
                                                v{l.derniere.version ?? "?"} · {dateCourte(l.derniere.le)}
                                            </>
                                        ) : (
                                            t({ en: "never replayed", fr: "jamais rejoué" })
                                        )}
                                    </span>
                                </button>
                            </li>
                        ))}
                    </ul>
                </section>
            ))}
            {detail && (
                <DetailDunTest
                    workflowId={workflowId}
                    test={detail.test}
                    resultats={detail.resultats}
                    onObligatoire={(v) => void changerObligatoire(detail.test.slug, v)}
                    onSupprimer={() => void supprimer(detail.test.slug)}
                />
            )}
            <HistoriqueDesCorrections corrections={corrections} onRevenir={(id) => void revenir(id)} />
        </div>
    );
}

function BandeauDePublication({ etat }: { etat: EtatDePublication }) {
    const { t } = useLangue();
    const bloque = etat.bloque;
    return (
        <section
            className={`space-y-1 rounded border p-3 text-sm ${bloque ? "border-red-300 bg-red-50 dark:bg-red-950" : "border-emerald-300 bg-emerald-50 dark:bg-emerald-950"}`}
            data-testid="bandeau-publication"
        >
            <h2 className="font-semibold">
                {bloque ? t({ en: "Publication blocked", fr: "Publication bloquée" }) : t({ en: "Nothing blocks the publication", fr: "Rien ne bloque la publication" })}
                <span className="ml-2 text-xs font-normal text-muted-foreground">
                    {t({ en: "draft", fr: "brouillon" })} v{etat.version}
                </span>
            </h2>
            {etat.controle?.bloquants.map((b, i) => (
                <p key={i}>
                    {t({ en: "Prompt check", fr: "Contrôle du prompt" })} · {b.etape ? `${b.etape} · ` : ""}
                    {b.message}
                    {b.extrait ? ` (${b.extrait})` : ""}
                </p>
            ))}
            {etat.tests_obligatoires.map((o) => (
                <p key={o.slug}>
                    {t({ en: "Required test", fr: "Test obligatoire" })} · {o.nom} : {o.raison}
                </p>
            ))}
            {etat.controle?.avertissements.map((a, i) => (
                <p key={i} className="text-muted-foreground">
                    {t({ en: "Warning", fr: "Avertissement" })} · {a.message}
                </p>
            ))}
        </section>
    );
}

function ResultatDeLaSuite({ suite }: { suite: ResultatDeSuite }) {
    const { t } = useLangue();
    if (suite.disponible === false) return <p className="rounded border p-3 text-sm">{suite.message}</p>;
    return (
        <section className="space-y-2 rounded border p-3 text-sm" data-testid="resultat-de-la-suite">
            <h2 className="font-semibold">
                {suite.ok
                    ? t({ en: "The whole suite passes", fr: "Toute la suite passe" })
                    : suite.refus
                      ? t({ en: "Refused: a required test fails", fr: "Refusé : un test obligatoire échoue" })
                      : t({ en: "The suite does not pass", fr: "La suite ne passe pas" })}
            </h2>
            {suite.partiel && <p className="text-muted-foreground">{suite.message}</p>}
            {suite.echecs.map((e, i) => (
                <div key={i} className="space-y-0.5 rounded bg-muted p-2" data-testid="echec-de-la-suite">
                    <p className="font-medium">
                        {e.nom} {e.obligatoire ? `(${t({ en: "required", fr: "obligatoire" })})` : ""}
                    </p>
                    {e.replique && <p>« {e.replique} »</p>}
                    <p className="text-red-900 dark:text-red-200">{e.raison}</p>
                    <p className="text-xs text-muted-foreground" data-testid="diagnostic">
                        {t({ en: "Diagnosis", fr: "Diagnostic" })} : {t(CAUSES[e.diagnostic.cause])} — {e.diagnostic.raison}{" "}
                        {t({ en: "Nothing is changed without your agreement.", fr: "Rien n'est changé sans votre accord." })}
                    </p>
                </div>
            ))}
        </section>
    );
}

function HistoriqueDesCorrections({ corrections, onRevenir }: { corrections: Correction[]; onRevenir: (id: string) => void }) {
    const { t } = useLangue();
    if (corrections.length === 0) return null;
    return (
        <section className="space-y-1" data-testid="historique-des-corrections">
            <h2 className="text-sm font-semibold text-muted-foreground">{t({ en: "History of the corrections", fr: "Historique des corrections" })}</h2>
            <ul className="space-y-1">
                {corrections.map((c) => (
                    <li key={c.id} className="flex flex-wrap items-center gap-2 rounded border p-2 text-sm">
                        <span className="text-xs">{dateCourte(c.le)}</span>
                        <span className="text-xs text-muted-foreground">v{c.version ?? "?"}</span>
                        <span className={`rounded px-1.5 text-xs ${c.vert ? STATUTS_DE_TEST.ok.classe : STATUTS_DE_TEST.echec.classe}`}>
                            {c.vert ? t({ en: "suite green", fr: "suite verte" }) : t({ en: "not green", fr: "pas verte" })}
                        </span>
                        <span>{c.resume}</span>
                        <Button className="ml-auto" variant="outline" size="sm" disabled={!c.retour_possible} onClick={() => onRevenir(c.id)}>
                            {t({ en: "Go back to this version", fr: "Revenir à cette version" })}
                        </Button>
                    </li>
                ))}
            </ul>
        </section>
    );
}
