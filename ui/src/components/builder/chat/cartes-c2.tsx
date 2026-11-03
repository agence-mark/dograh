"use client";

/**
 * [.mark] builder partie 2, U5 (lot C2) : les cartes du fil qui s'ajoutent au plan et à la question : rapport de fin, annonce d'une
 * dépense, plan avant / après d'une correction, proposition sur un test. Le code dessine, le modèle ne fait que remplir.
 * Pas de cadre autour des cartes (convention de l'écran) : un titre, du texte, des boutons.
 */
import { Check, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { CarteDuFil } from "./evenements";

const T = {
    rapport: { en: "Report", fr: "Rapport de fin" },
    tests: { en: "Tests", fr: "Tests" },
    essayer: { en: "Sentences to try", fr: "Phrases à essayer" },
    ouverts: { en: "Open points", fr: "Points ouverts" },
    passes: { en: "passed", fr: "réussis" },
    depense: { en: "A cost to agree", fr: "Une dépense à accorder" },
    estime: { en: "Estimated", fr: "Estimé" },
    accorder: { en: "Agree", fr: "Accorder" },
    refuser: { en: "Refuse", fr: "Refuser" },
    accordee: { en: "Agreed", fr: "Accordée" },
    refusee: { en: "Refused", fr: "Refusée" },
    correction: { en: "Fix proposed", fr: "Correction proposée" },
    cause: { en: "Cause", fr: "Cause" },
    objet: { en: "Touched", fr: "Touché" },
    avant: { en: "Before", fr: "Avant" },
    apres: { en: "After", fr: "Après" },
    approuver: { en: "Approve", fr: "Approuver" },
    renvoyer: { en: "Send back", fr: "Renvoyer" },
    note: { en: "What should change?", fr: "Ce qui doit changer ?" },
    envoyer: { en: "Send", fr: "Envoyer" },
    approuvee: { en: "Approved: apply the plan, then add a test and replay the whole suite.", fr: "Approuvé : applique le plan, ajoute un test, puis rejoue toute la suite." },
    renvoyee: { en: "Sent back. ", fr: "Renvoyé. " },
    propose: { en: "Proposed to a person", fr: "Proposé à une personne" },
    suppression: { en: "Delete this test (from the Tests tab)", fr: "Supprimer ce test (depuis l'onglet Tests)" },
    criteres: { en: "New criteria (to apply from the Tests tab)", fr: "Nouveaux critères (à appliquer depuis l'onglet Tests)" },
    ouvrir: { en: "Open the Tests tab", fr: "Ouvrir l'onglet Tests" },
} satisfies Record<string, Texte>;

type Rapport = {
    resume: string;
    tests: { nom: string; ok: boolean; pourquoi?: string }[];
    phrases_a_essayer: string[];
    points_ouverts: string[];
    reussis: number;
};

export function CarteRapport({ carte }: { carte: CarteDuFil }) {
    const { t } = useLangue();
    const r = carte as unknown as Rapport;
    return (
        <section className="my-2 space-y-2 py-1" data-carte="rapport">
            <h4 className="text-sm font-semibold">{t(T.rapport)}</h4>
            <p className="text-sm whitespace-pre-wrap">{r.resume}</p>
            {r.tests.length > 0 && (
                <div>
                    <p className="text-sm font-semibold">
                        {t(T.tests)} : {r.reussis}/{r.tests.length} {t(T.passes)}
                    </p>
                    <ul className="space-y-1">
                        {r.tests.map((x, i) => (
                            <li key={i} className="flex items-start gap-2 text-sm" data-ok={x.ok}>
                                {x.ok ? <Check className="mt-0.5 size-4 text-(--etat-fait)" /> : <X className="mt-0.5 size-4 text-destructive" />}
                                <span>
                                    {x.nom}
                                    {!x.ok && x.pourquoi ? <span className="text-muted-foreground"> : {x.pourquoi}</span> : null}
                                </span>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {r.phrases_a_essayer.length > 0 && (
                <div>
                    <p className="text-sm font-semibold">{t(T.essayer)}</p>
                    <ul className="list-disc pl-5 text-sm">
                        {r.phrases_a_essayer.map((p, i) => (
                            <li key={i}>{p}</li>
                        ))}
                    </ul>
                </div>
            )}
            {r.points_ouverts.length > 0 && (
                <div>
                    <p className="text-sm font-semibold">{t(T.ouverts)}</p>
                    <ul className="list-disc pl-5 text-sm">
                        {r.points_ouverts.map((p, i) => (
                            <li key={i}>{p}</li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
}

/** L'annonce d'une dépense : le builder s'arrête, la personne accorde ou refuse. Une fois répondu, la carte garde la réponse. */
export function CarteDepense({ carte, repondre, active }: { carte: CarteDuFil; repondre: (accord: boolean) => void; active: boolean }) {
    const { t } = useLangue();
    const statut = String(carte.statut ?? "attente");
    return (
        <section className="my-2 py-1" data-carte="depense" data-statut={statut}>
            <h4 className="text-sm font-semibold">{t(T.depense)}</h4>
            <p className="text-sm">{String(carte.motif)}</p>
            <p className="mb-2 text-xs text-muted-foreground">
                {t(T.estime)} : ${Number(carte.montant_estime ?? 0).toFixed(2)}
            </p>
            {statut === "attente" ? (
                <div className="flex gap-2">
                    <Button size="sm" disabled={!active} onClick={() => repondre(true)}>
                        {t(T.accorder)}
                    </Button>
                    <Button size="sm" variant="outline" disabled={!active} onClick={() => repondre(false)}>
                        {t(T.refuser)}
                    </Button>
                </div>
            ) : (
                <p className="text-sm font-semibold">{statut === "accordee" ? t(T.accordee) : t(T.refusee)}</p>
            )}
        </section>
    );
}

/** Le plan avant / après d'une correction (temps 2) : approuver, ou renvoyer avec une note. Rien n'est appliqué avant. */
export function CarteCorrection({ carte, repondre, active }: { carte: CarteDuFil; repondre: (texte: string) => void; active: boolean }) {
    const { t } = useLangue();
    const [renvoi, setRenvoi] = useState(false);
    const [note, setNote] = useState("");
    return (
        <section className="my-2 space-y-2 py-1" data-carte="correction">
            <h4 className="text-sm font-semibold">{t(T.correction)}</h4>
            <p className="text-sm">
                <span className="font-semibold">{t(T.cause)} : </span>
                {String(carte.cause)}
            </p>
            {carte.replique ? <blockquote className="border-l-2 pl-3 text-sm text-muted-foreground">{String(carte.replique)}</blockquote> : null}
            <p className="text-sm">
                <span className="font-semibold">{t(T.objet)} : </span>
                {String(carte.objet)} · {String(carte.cible)}
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
                <div>
                    <p className="text-xs font-semibold">{t(T.avant)}</p>
                    <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap">{String(carte.avant)}</pre>
                </div>
                <div>
                    <p className="text-xs font-semibold">{t(T.apres)}</p>
                    <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap">{String(carte.apres)}</pre>
                </div>
            </div>
            <div className="flex flex-wrap gap-2">
                <Button size="sm" disabled={!active} onClick={() => repondre(t(T.approuvee))}>
                    {t(T.approuver)}
                </Button>
                <Button size="sm" variant="outline" disabled={!active} onClick={() => setRenvoi((v) => !v)}>
                    {t(T.renvoyer)}
                </Button>
            </div>
            {renvoi && active && (
                <div className="flex gap-2">
                    <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder={t(T.note)} />
                    <Button size="sm" disabled={!note.trim()} onClick={() => repondre(t(T.renvoyee) + note.trim())}>
                        {t(T.envoyer)}
                    </Button>
                </div>
            )}
        </section>
    );
}

/** Suppression d'un test, ou nouveaux critères : le builder propose seulement, une personne applique depuis l'onglet Tests. */
export function CartePropositionTest({ carte }: { carte: CarteDuFil }) {
    const { t } = useLangue();
    const test = (carte.test ?? {}) as { nom?: string; slug?: string };
    const nom = typeof carte.test === "string" ? carte.test : (test.nom ?? test.slug ?? "");
    return (
        <section className="my-2 py-1" data-carte="proposition-test" data-genre={String(carte.genre)}>
            <h4 className="text-sm font-semibold">{t(T.propose)}</h4>
            <p className="text-sm">
                {carte.genre === "suppression" ? t(T.suppression) : t(T.criteres)} : {nom}
            </p>
            {carte.genre === "criteres" && (
                <pre className="mt-1 max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs">{JSON.stringify(carte.criteres, null, 2)}</pre>
            )}
            <Link className="mt-1 inline-block cursor-pointer text-sm hover:font-semibold" href={`/agents/${String(carte.workflow_id)}/tests`}>
                {t(T.ouvrir)}
            </Link>
        </section>
    );
}
