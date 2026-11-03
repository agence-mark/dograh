"use client";

/**
 * [.mark] U3 (E47): the Tests tab of an agent. « Tests of the agent » / « Past runs » (checkboxes, kind, required, last result,
 * changed), « Play all » (selection, required, whole suite, 1 to 10 attempts), « Add a test » (by hand, with the builder, from a reply
 * of a call, from the library), the window of a test (three kinds) and the window of a run (failed attempt, criterion, faulty reply,
 * the judge's opinion). Kept from before: what blocks the publication (the prompt check and the required tests), the replay of the
 * WHOLE suite (B38), the reason written on the faulty reply (B40), the diagnosis before any correction (B39), the history of the
 * corrections with the way back, and the export for the lab.
 */
import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet,
    executionsPasseesApiV1BuilderTestsWorkflowIdExecutionsGet,
    exporterLesTestsApiV1BuilderTestsWorkflowIdExportGet,
    historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet,
    lireLesTestsApiV1BuilderTestsWorkflowIdGet,
    lireUnTestApiV1BuilderTestsWorkflowIdSlugGet,
    rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost,
    ressourcesDeLAgentApiV1BuilderTestsWorkflowIdRessourcesGet,
    retourArriereApiV1BuilderTestsWorkflowIdCorrectionsCorrectionIdRetourPost,
    supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete,
} from "@/client";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { useLangue } from "@/components/mark/langue/langue";
import { Segmente } from "@/components/mark/studio/fenetre-onglets";
import { Liste } from "@/components/mark/studio/liste";
import { Info, Marque } from "@/components/mark/studio/marques";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { detailFromError } from "@/lib/apiError";

import { DepuisLaBibliotheque } from "./DepuisLaBibliotheque";
import { DetailDunTest } from "./DetailDunTest";
import { FenetreDeTest } from "./FenetreDeTest";
import { CAUSES, dateCourte, STATUTS_DE_TEST } from "./libelles";
import type {
    Correction,
    EtatDePublication,
    Execution,
    ExecutionPassee,
    RessourcesDeTest,
    ResultatDeSuite,
    ResumeDeTest,
    TestComplet,
} from "./types";

/** The tests grouped by folder, folders and tests in the order they come. */
export function parDossier(tests: ResumeDeTest[]): Array<[string, ResumeDeTest[]]> {
    const groupes = new Map<string, ResumeDeTest[]>();
    for (const t of tests) groupes.set(t.dossier || "", [...(groupes.get(t.dossier || "") ?? []), t]);
    return [...groupes.entries()];
}

export function PageTests({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const [tests, setTests] = useState<ResumeDeTest[] | null>(null);
    const [passees, setPassees] = useState<ExecutionPassee[]>([]);
    const [ressources, setRessources] = useState<RessourcesDeTest | null>(null);
    const [publication, setPublication] = useState<EtatDePublication | null>(null);
    const [corrections, setCorrections] = useState<Correction[]>([]);
    const [suite, setSuite] = useState<ResultatDeSuite | null>(null);
    const [vue, setVue] = useState<"tests" | "passees">("tests");
    const [coches, setCoches] = useState<string[]>([]);
    const [essais, setEssais] = useState("3");
    const [fenetre, setFenetre] = useState<null | "nouveau" | "bibliotheque">(null);
    const [edition, setEdition] = useState<TestComplet | null>(null);
    const [execution, setExecution] = useState<{ test: TestComplet; resultats: Execution[] } | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [message, setMessage] = useState<string | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);

    const libelleTests = t({ en: "Tests of the agent", fr: "Tests de l'agent" });
    const libellePassees = t({ en: "Past runs", fr: "Exécutions passées" });

    const charger = useCallback(async () => {
        const [a, b, c, d, e] = await Promise.all([
            lireLesTestsApiV1BuilderTestsWorkflowIdGet({ path: { workflow_id: workflowId } }),
            etatDeLaPublicationApiV1BuilderTestsWorkflowIdPublicationGet({ path: { workflow_id: workflowId } }),
            historiqueDesCorrectionsApiV1BuilderTestsWorkflowIdCorrectionsGet({ path: { workflow_id: workflowId } }),
            executionsPasseesApiV1BuilderTestsWorkflowIdExecutionsGet({ path: { workflow_id: workflowId } }),
            ressourcesDeLAgentApiV1BuilderTestsWorkflowIdRessourcesGet({ path: { workflow_id: workflowId } }),
        ]);
        if (a.error) {
            setErreur(detailFromError(a.error, "The tests could not be read"));
            return;
        }
        setErreur(null);
        const lus = (a.data as { tests: ResumeDeTest[] }).tests;
        setTests(lus);
        setCoches((avant) => avant.filter((s) => lus.some((l) => l.slug === s)));
        if (!b.error) setPublication(b.data as EtatDePublication);
        if (!c.error) setCorrections((c.data as { corrections: Correction[] }).corrections);
        if (!d.error) setPassees((d.data as { executions: ExecutionPassee[] }).executions);
        if (!e.error) setRessources(e.data as RessourcesDeTest);
    }, [workflowId]);

    useEffect(() => {
        void charger();
    }, [charger]);

    const lire = async (slug: string) => {
        const r = await lireUnTestApiV1BuilderTestsWorkflowIdSlugGet({ path: { workflow_id: workflowId, slug } });
        if (r.error) {
            setErreur(detailFromError(r.error, "The test could not be read"));
            return null;
        }
        return r.data as { test: TestComplet; resultats: Execution[] };
    };
    const ouvrirLeTest = async (slug: string) => {
        const d = await lire(slug);
        if (d) setEdition(d.test);
    };
    const ouvrirLExecution = async (slug: string) => {
        const d = await lire(slug);
        if (d) setExecution(d);
    };

    const jouer = async (slugs: string[] | undefined) => {
        setEnCours(true);
        setMessage(null);
        const r = await rejouerLaSuiteApiV1BuilderTestsWorkflowIdRejouerPost({
            path: { workflow_id: workflowId },
            body: { repetitions: Number(essais) || 3, ...(slugs ? { tests: slugs } : {}) },
        });
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

    const supprimer = async (slug: string) => {
        const r = await supprimerUnTestApiV1BuilderTestsWorkflowIdSlugDelete({ path: { workflow_id: workflowId, slug } });
        if (r.error) setErreur(detailFromError(r.error, "The test was not deleted"));
        else {
            setEdition(null);
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

    const obligatoires = (tests ?? []).filter((x) => x.obligatoire).map((x) => x.slug);
    const aucun = (tests?.length ?? 0) === 0;
    const bascule = (slug: string) => setCoches((c) => (c.includes(slug) ? c.filter((x) => x !== slug) : [...c, slug]));

    return (
        <div className="mx-auto w-full max-w-5xl space-y-5 px-6 py-6" data-testid="page-tests">
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {publication?.brouillon && <BandeauDePublication etat={publication} />}
            <div className="flex flex-wrap items-center gap-2">
                <Segmente
                    valeur={vue === "tests" ? libelleTests : libellePassees}
                    options={[libelleTests, libellePassees]}
                    changer={(o) => setVue(o === libelleTests ? "tests" : "passees")}
                />
                <div className="ml-auto flex flex-wrap items-center gap-2">
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button disabled={enCours || aucun}>
                                {enCours ? t({ en: "Replaying…", fr: "Rejeu en cours…" }) : t({ en: "Play all", fr: "Tout jouer" })}
                                <ChevronDown className="size-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem disabled={coches.length === 0} onSelect={() => void jouer(coches)}>
                                {t({ en: "The selection", fr: "La sélection" })} ({coches.length})
                            </DropdownMenuItem>
                            <DropdownMenuItem disabled={obligatoires.length === 0} onSelect={() => void jouer(obligatoires)}>
                                {t({ en: "The required tests", fr: "Les tests obligatoires" })} ({obligatoires.length})
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => void jouer(undefined)}>{t({ en: "The whole suite", fr: "Toute la suite" })}</DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                    <span className="flex items-center gap-1 text-sm text-muted-foreground">
                        {t({ en: "Attempts", fr: "Essais" })}
                        <Liste className="w-16" valeur={essais} changer={setEssais} options={Array.from({ length: 10 }, (_, i) => String(i + 1))} />
                        <Info>
                            {t({
                                en: "Each test is played this many times (1 to 10). Only a whole-suite replay can verify the agent.",
                                fr: "Chaque test est joué ce nombre de fois (1 à 10). Seul le rejeu de toute la suite peut vérifier l'agent.",
                            })}
                        </Info>
                    </span>
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="outline">
                                {t({ en: "Add a test", fr: "Ajouter un test" })}
                                <ChevronDown className="size-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onSelect={() => setFenetre("nouveau")}>{t({ en: "By hand", fr: "À la main" })}</DropdownMenuItem>
                            <DropdownMenuItem asChild>
                                <Link href={adresseOnglet(workflowId, "parcours")}>{t({ en: "With the builder", fr: "Par le builder" })}</Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem asChild>
                                <Link href={adresseOnglet(workflowId, "appels")}>{t({ en: "From a reply of a call", fr: "Depuis une réplique d'un appel" })}</Link>
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => setFenetre("bibliotheque")}>{t({ en: "From the library", fr: "Depuis la bibliothèque" })}</DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                    <Button variant="outline" disabled={aucun} onClick={() => void exporter()}>
                        {t({ en: "Export for the lab", fr: "Exporter pour le labo" })}
                    </Button>
                </div>
            </div>
            {message && <p className="text-sm text-muted-foreground">{message}</p>}
            {suite && <ResultatDeLaSuite suite={suite} />}
            {tests !== null && aucun && (
                <p className="py-4 text-sm text-muted-foreground" data-testid="aucun-test">
                    {t({
                        en: "No test yet. Create one from a reply of a call (button on the call page, or from « To triage »), by hand, from the library, or ask the builder to write them from the client sheet.",
                        fr: "Aucun test. Créez-en un depuis une réplique d'un appel (bouton sur la page de l'appel, ou depuis « À trier »), à la main, depuis la bibliothèque, ou demandez au builder de les écrire depuis la fiche du client.",
                    })}
                </p>
            )}
            {tests && !aucun && vue === "tests" && (
                <Tableau
                    colonnes={[
                        { titre: "", largeur: "w-8" },
                        { titre: t({ en: "Test", fr: "Test" }) },
                        { titre: t({ en: "Kind", fr: "Sorte" }) },
                        { titre: t({ en: "Required", fr: "Obligatoire" }) },
                        { titre: t({ en: "Last result", fr: "Dernier résultat" }) },
                        { titre: t({ en: "Changed", fr: "Modifié" }) },
                    ]}
                >
                    {parDossier(tests).flatMap(([dossier, lignes]) => [
                        dossier ? (
                            <tr key={`d-${dossier}`} data-testid="dossier-de-tests">
                                <td colSpan={6} className="pt-4 pb-1 text-xs font-medium tracking-wider text-muted-foreground uppercase">
                                    {dossier}
                                </td>
                            </tr>
                        ) : null,
                        ...lignes.map((l) => (
                            <Ligne key={l.slug} onClick={() => void ouvrirLeTest(l.slug)}>
                                <td className="py-3" onClick={(e) => e.stopPropagation()}>
                                    <Checkbox checked={coches.includes(l.slug)} onCheckedChange={() => bascule(l.slug)} aria-label={`${t({ en: "Select", fr: "Cocher" })} ${l.nom}`} />
                                </td>
                                <Cellule principale sous={l.description || undefined}>
                                    {l.nom}
                                </Cellule>
                                <Cellule>{l.genre === "conversation" ? t({ en: "conversation", fr: "conversation" }) : t({ en: "reply", fr: "réplique" })}</Cellule>
                                <Cellule>{l.obligatoire ? <Marque ton="danger">{t({ en: "required", fr: "obligatoire" })}</Marque> : ""}</Cellule>
                                <Cellule>
                                    {l.derniere ? (
                                        <button
                                            type="button"
                                            className="cursor-pointer hover:font-medium"
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                void ouvrirLExecution(l.slug);
                                            }}
                                        >
                                            <span className={`rounded px-1.5 py-0.5 ${STATUTS_DE_TEST[l.derniere.statut].classe}`}>
                                                {l.derniere.reussis}/{l.derniere.total}
                                            </span>{" "}
                                            v{l.derniere.version ?? "?"} · {dateCourte(l.derniere.le)}
                                        </button>
                                    ) : (
                                        t({ en: "never replayed", fr: "jamais rejoué" })
                                    )}
                                </Cellule>
                                <Cellule>{dateCourte(l.modifie_le)}</Cellule>
                            </Ligne>
                        )),
                    ])}
                </Tableau>
            )}
            {tests && !aucun && vue === "passees" && (
                <div data-testid="executions-passees">
                    {passees.length === 0 ? (
                        <p className="py-4 text-sm text-muted-foreground">{t({ en: "No test has been replayed yet.", fr: "Aucun test n'a encore été rejoué." })}</p>
                    ) : (
                        <Tableau
                            colonnes={[
                                { titre: t({ en: "Test", fr: "Test" }) },
                                { titre: t({ en: "Result", fr: "Résultat" }) },
                                { titre: t({ en: "Version", fr: "Version" }) },
                                { titre: t({ en: "Date", fr: "Date" }) },
                            ]}
                        >
                            {passees.map((p) => (
                                <Ligne key={`${p.test}-${p.le}`} onClick={() => void ouvrirLExecution(p.test)}>
                                    <Cellule principale>{p.nom}</Cellule>
                                    <Cellule>
                                        <span className={`rounded px-1.5 py-0.5 ${STATUTS_DE_TEST[p.statut].classe}`}>
                                            {p.reussis}/{p.total}
                                        </span>
                                    </Cellule>
                                    <Cellule>v{p.version ?? "?"}</Cellule>
                                    <Cellule>{dateCourte(p.le)}</Cellule>
                                </Ligne>
                            ))}
                        </Tableau>
                    )}
                </div>
            )}
            <HistoriqueDesCorrections corrections={corrections} onRevenir={(id) => void revenir(id)} />
            {fenetre === "nouveau" && (
                <FenetreDeTest
                    workflowId={workflowId}
                    ressources={ressources}
                    onFermer={() => setFenetre(null)}
                    onFait={() => {
                        setFenetre(null);
                        void charger();
                    }}
                />
            )}
            {fenetre === "bibliotheque" && (
                <DepuisLaBibliotheque
                    workflowId={workflowId}
                    ressources={ressources}
                    onFermer={() => setFenetre(null)}
                    onCopie={(slug) => {
                        setFenetre(null);
                        void charger().then(() => ouvrirLeTest(slug));
                    }}
                />
            )}
            {edition && (
                <FenetreDeTest
                    key={edition.slug}
                    workflowId={workflowId}
                    test={edition}
                    ressources={ressources}
                    onFermer={() => setEdition(null)}
                    onSupprimer={() => void supprimer(edition.slug)}
                    onFait={() => {
                        setEdition(null);
                        void charger();
                    }}
                />
            )}
            {execution && (
                <Dialog open onOpenChange={(o) => !o && setExecution(null)}>
                    <DialogContent
                        onOpenAutoFocus={(e) => e.preventDefault()}
                        className="flex max-h-[86vh] flex-col gap-0 overflow-hidden p-0 sm:max-w-4xl"
                        data-testid="fenetre-d-execution"
                    >
                        <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                            <DialogTitle className="text-lg">{t({ en: "Run of a test", fr: "Exécution d'un test" })}</DialogTitle>
                        </div>
                        <div className="min-h-0 flex-1 overflow-auto bg-background px-6 py-4">
                            <DetailDunTest workflowId={workflowId} test={execution.test} resultats={execution.resultats} />
                        </div>
                    </DialogContent>
                </Dialog>
            )}
        </div>
    );
}

function BandeauDePublication({ etat }: { etat: EtatDePublication }) {
    const { t } = useLangue();
    const bloque = etat.bloque;
    return (
        <section
            className={`space-y-1 rounded border p-3 text-sm ${bloque ? "border-(--signal-danger)/40 bg-(--signal-danger)/10" : "border-(--signal-ok)/40 bg-(--signal-ok)/10"}`}
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
                    <p className="text-(--signal-danger)">{e.raison}</p>
                    <p className="text-xs text-muted-foreground" data-testid="diagnostic">
                        {t({ en: "Diagnosis", fr: "Diagnostic" })} : {t(CAUSES[e.diagnostic.cause])} - {e.diagnostic.raison}{" "}
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
                    <li key={c.id} className="flex flex-wrap items-center gap-2 border-b py-2 text-sm">
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
