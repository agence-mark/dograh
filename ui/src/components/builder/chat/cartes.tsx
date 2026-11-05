"use client";

/** [.mark] builder partie 2, U5 : les cartes du fil (plan en cases, question avec réponse proposée) et la ligne d'une action. */
import { Check, ChevronRight, Circle, Loader2, X } from "lucide-react";
import { useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Info } from "@/components/mark/studio/marques";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

import type { EtapeDuPlan, LigneDuFil } from "./evenements";
import { BoutonAnnuler, type JournalDeLaLigne } from "./journal-du-builder";

const T = {
    plan: { en: "Plan", fr: "Plan" },
    planInfo: { en: "The builder keeps this card up to date at every step it completes.", fr: "Le builder tient cette carte à jour à chaque étape franchie." },
    sur: { en: "of", fr: "sur" },
    question: { en: "A question", fr: "Une question" },
    proposee: { en: "Proposed answer", fr: "Réponse proposée" },
    accepter: { en: "Use this answer", fr: "Prendre cette réponse" },
    autre: { en: "Other", fr: "Autre" },
    passer: { en: "Skip", fr: "Passer" },
    envoyer: { en: "Send", fr: "Envoyer" },
    saisie: { en: "Your answer...", fr: "Votre réponse..." },
    passee: { en: "Skipped: choose for me and say what you chose.", fr: "Passée : choisis pour moi et dis-moi ce que tu as choisi." },
    arguments: { en: "Arguments", fr: "Arguments" },
    resultat: { en: "Result", fr: "Résultat" },
} satisfies Record<string, Texte>;

export function CarteDuPlan({ etapes }: { etapes: EtapeDuPlan[] }) {
    const { t } = useLangue();
    const faites = etapes.filter((e) => e.etat === "fait").length;
    // Forme de la maquette : une carte arrondie, « Plan (!) », « 4 sur 7 », la barre, une ligne par étape.
    return (
        <section className="my-2 space-y-2.5 rounded-xl border bg-card px-4 py-3" data-carte="plan">
            <div className="flex items-center">
                <h4 className="flex flex-1 items-center gap-1.5 text-sm font-medium">
                    {t(T.plan)}
                    <Info>{t(T.planInfo)}</Info>
                </h4>
                <span className="text-xs tabular-nums text-muted-foreground">
                    {faites} {t(T.sur)} {etapes.length}
                </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={etapes.length} aria-valuenow={faites}>
                <div className="h-full rounded-full bg-(--acc)" style={{ width: `${etapes.length ? (faites / etapes.length) * 100 : 0}%` }} />
            </div>
            <ul className="space-y-1.5">
                {etapes.map((e, i) => (
                    <li key={i} className="flex items-center gap-2 text-sm" data-etat={e.etat}>
                        {e.etat === "fait" ? (
                            <Check className="size-4 text-(--etat-fait)" strokeWidth={2.5} />
                        ) : e.etat === "en_cours" ? (
                            <Loader2 className="size-4 animate-spin" />
                        ) : (
                            <Circle className="size-4 text-muted-foreground" />
                        )}
                        <span className={e.etat === "a_venir" ? "" : e.etat === "en_cours" ? "font-medium" : "text-muted-foreground"}>{e.libelle}</span>
                    </li>
                ))}
            </ul>
        </section>
    );
}

/** Une question à la fois, avec la réponse que le builder propose. Une réponse envoyée devient un message du fil. */
export function CarteQuestion({
    question,
    reponseProposee,
    choix,
    repondre,
    active,
}: {
    question: string;
    reponseProposee: string;
    choix: string[];
    repondre: (texte: string) => void;
    active: boolean;
}) {
    const { t } = useLangue();
    const [autre, setAutre] = useState(false);
    const [texte, setTexte] = useState("");
    return (
        <section className="my-2 py-1" data-carte="question">
            <h4 className="text-sm font-semibold">{t(T.question)}</h4>
            <p className="mb-2 text-sm">{question}</p>
            <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" disabled={!active} onClick={() => repondre(reponseProposee)} title={t(T.proposee)}>
                    {t(T.accepter)} : {reponseProposee}
                </Button>
                {choix.map((c) => (
                    <Button key={c} size="sm" variant="outline" disabled={!active} onClick={() => repondre(c)}>
                        {c}
                    </Button>
                ))}
                <Button size="sm" variant="ghost" disabled={!active} onClick={() => setAutre((v) => !v)}>
                    {t(T.autre)}
                </Button>
                <Button size="sm" variant="ghost" disabled={!active} onClick={() => repondre(t(T.passee))}>
                    {t(T.passer)}
                </Button>
            </div>
            {autre && active && (
                <div className="mt-2 flex gap-2">
                    <Textarea rows={2} value={texte} onChange={(e) => setTexte(e.target.value)} placeholder={t(T.saisie)} />
                    <Button size="sm" disabled={!texte.trim()} onClick={() => repondre(texte.trim())}>
                        {t(T.envoyer)}
                    </Button>
                </div>
            )}
        </section>
    );
}

/** N1 : la ligne du journal que le serveur joint au résultat d'une écriture (``{id, annulable, raison}``). */
const journalDe = (ligne: Extract<LigneDuFil, { genre: "action" }>): JournalDeLaLigne | null => {
    const r = ligne.resultat as { journal?: JournalDeLaLigne } | null | undefined;
    return r && typeof r === "object" && r.journal && typeof r.journal.id === "number" ? r.journal : null;
};

/** « Lit les dossiers d'audit ✓ » : une ligne compacte, dépliable pour voir les arguments et le résultat ; une roue tant que le résultat n'est pas là. */
export function LigneAction({ ligne }: { ligne: Extract<LigneDuFil, { genre: "action" }> }) {
    const { t } = useLangue();
    const [ouverte, setOuverte] = useState(false);
    return (
        <div className="text-sm text-muted-foreground" data-action={ligne.nom}>
            <button type="button" className="flex cursor-pointer items-center gap-1.5 hover:font-semibold" onClick={() => setOuverte((v) => !v)}>
                <ChevronRight className={`size-3.5 transition-transform ${ouverte ? "rotate-90" : ""}`} />
                <span>{ligne.nom}</span>
                {!ligne.fini ? (
                    <Loader2 className="size-3.5 animate-spin" aria-label={t({ en: "running", fr: "en cours" })} />
                ) : ligne.ok ? (
                    <Check className="size-3.5 text-(--etat-fait)" aria-label={t({ en: "done", fr: "fait" })} />
                ) : (
                    <X className="size-3.5 text-destructive" aria-label={t({ en: "failed", fr: "échec" })} />
                )}
            </button>
            {ligne.fini && journalDe(ligne) && <BoutonAnnuler journal={journalDe(ligne) as JournalDeLaLigne} />}
            {ouverte && (
                <div className="mt-1 ml-5 space-y-1">
                    <p className="font-semibold">{t(T.arguments)}</p>
                    <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs">{JSON.stringify(ligne.arguments, null, 2)}</pre>
                    {ligne.fini && (
                        <>
                            <p className="font-semibold">{t(T.resultat)}</p>
                            <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs">{JSON.stringify(ligne.resultat, null, 2)}</pre>
                        </>
                    )}
                </div>
            )}
        </div>
    );
}
