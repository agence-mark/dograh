"use client";

/**
 * [.mark] builder-agent-vocal (lot 4, B36): the « Design document » card. Written by the builder BEFORE anything is
 * built: goal and what counts as success, hypotheses to confirm, the data and what to do when it is missing, the
 * tools and their answers (« system unavailable » included), example calls. A person approves it, or sends it back
 * with a note; nothing is built before.
 */
import { useCallback, useEffect, useState } from "react";

import { deciderDeLaConceptionApiV1BuilderConceptionWorkflowIdDecisionPost, lireLaConceptionApiV1BuilderConceptionWorkflowIdGet } from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { detailFromError } from "@/lib/apiError";

import { useBuilderEcran } from "../store";
import { Carte } from "./Carte";

const T = {
    titre: { en: "Design document", fr: "Document de conception" },
    aide: { en: "Nothing is built until a person approves it.", fr: "Rien n'est construit tant qu'une personne ne l'a pas approuvé." },
    aucun: { en: "No design document written yet.", fr: "Aucun document de conception pour l'instant." },
    objectif: { en: "Goal", fr: "Objectif" },
    reussite: { en: "Success", fr: "Ce qui compte comme réussi" },
    hypotheses: { en: "Hypotheses to confirm", fr: "Hypothèses à confirmer" },
    donnees: { en: "Data, and what to do if it is missing", fr: "Données, et que faire si elles manquent" },
    outils: { en: "Tools and their answers", fr: "Outils et leurs réponses" },
    exemples: { en: "Example calls", fr: "Exemples d'appels" },
    approuver: { en: "Approve", fr: "Approuver" },
    renvoyer: { en: "Send back with a note", fr: "Renvoyer avec une note" },
    note: { en: "Note for the builder", fr: "Note pour le builder" },
    propose: { en: "Waiting for a person", fr: "En attente d'une personne" },
    approuve: { en: "Approved by", fr: "Approuvé par" },
    renvoye: { en: "Sent back", fr: "Renvoyé" },
    echec: { en: "The request failed.", fr: "La demande a échoué." },
    ajour: { en: "Revision", fr: "Révision" },
} satisfies Record<string, Texte>;

interface ConceptionLue {
    etat: "propose" | "approuve" | "renvoye";
    revision: number;
    note?: string | null;
    decide_par?: string | null;
    conception: {
        objectif: string;
        reussite: string;
        hypotheses: string[];
        donnees: { nom: string; si_absente: string }[];
        outils: { nom: string; reponses: string[]; si_indisponible: string }[];
        exemples_appels: string[];
    };
}

export function CarteConception({ workflowId }: { workflowId: number }) {
    const { t } = useLangue();
    const contexte = useBuilderEcran((s) => s.contexte);
    const [etat, setEtat] = useState<ConceptionLue | null>(null);
    const [note, setNote] = useState("");
    const [renvoi, setRenvoi] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const reponse = await lireLaConceptionApiV1BuilderConceptionWorkflowIdGet({ path: { workflow_id: workflowId } });
        if (!reponse.error) setEtat(((reponse.data as { conception?: ConceptionLue | null } | undefined)?.conception ?? null) as ConceptionLue | null);
    }, [workflowId]);

    // Read again after every action of the builder (the context store is refreshed then).
    useEffect(() => {
        void charger();
    }, [charger, contexte]);

    const decider = async (approuve: boolean) => {
        setErreur(null);
        const reponse = await deciderDeLaConceptionApiV1BuilderConceptionWorkflowIdDecisionPost({
            path: { workflow_id: workflowId },
            body: { approuve, note: approuve ? null : note.trim() || null },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, t(T.echec)));
            return;
        }
        setRenvoi(false);
        setNote("");
        await charger();
    };

    if (!etat) {
        return (
            <Carte type="conception" titre={t(T.titre)}>
                <p className="text-xs text-muted-foreground">{t(T.aucun)}</p>
            </Carte>
        );
    }
    const c = etat.conception;
    return (
        <Carte type="conception" titre={t(T.titre)} aide={t(T.aide)}>
            <dl className="space-y-2 text-xs">
                <div>
                    <dt className="font-medium">{t(T.objectif)}</dt>
                    <dd>{c.objectif}</dd>
                </div>
                <div>
                    <dt className="font-medium">{t(T.reussite)}</dt>
                    <dd>{c.reussite}</dd>
                </div>
                {c.hypotheses.length > 0 && (
                    <div>
                        <dt className="font-medium">{t(T.hypotheses)}</dt>
                        <dd>
                            <ul className="list-disc pl-4">{c.hypotheses.map((h) => <li key={h}>{h}</li>)}</ul>
                        </dd>
                    </div>
                )}
                {c.donnees.length > 0 && (
                    <div>
                        <dt className="font-medium">{t(T.donnees)}</dt>
                        <dd>
                            <ul className="list-disc pl-4">{c.donnees.map((d) => <li key={d.nom}><b>{d.nom}</b> : {d.si_absente}</li>)}</ul>
                        </dd>
                    </div>
                )}
                {c.outils.length > 0 && (
                    <div>
                        <dt className="font-medium">{t(T.outils)}</dt>
                        <dd>
                            <ul className="list-disc pl-4">
                                {c.outils.map((o) => (
                                    <li key={o.nom}>
                                        <b>{o.nom}</b> : {o.reponses.join(", ")} · {o.si_indisponible}
                                    </li>
                                ))}
                            </ul>
                        </dd>
                    </div>
                )}
                {c.exemples_appels.length > 0 && (
                    <div>
                        <dt className="font-medium">{t(T.exemples)}</dt>
                        <dd>
                            <ul className="list-disc pl-4">{c.exemples_appels.map((e) => <li key={e}>{e}</li>)}</ul>
                        </dd>
                    </div>
                )}
            </dl>
            <p className="mt-2 text-xs text-muted-foreground" data-etat-conception={etat.etat}>
                {t(T.ajour)} {etat.revision} ·{" "}
                {etat.etat === "approuve" ? `${t(T.approuve)} ${etat.decide_par ?? ""}` : etat.etat === "renvoye" ? `${t(T.renvoye)} : ${etat.note ?? ""}` : t(T.propose)}
            </p>
            {etat.etat !== "approuve" && (
                <div className="mt-2 space-y-2">
                    {renvoi && <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder={t(T.note)} aria-label={t(T.note)} className="min-h-16 text-xs" />}
                    <div className="flex gap-2">
                        <Button type="button" size="sm" onClick={() => void decider(true)}>
                            {t(T.approuver)}
                        </Button>
                        <Button type="button" size="sm" variant="outline" disabled={renvoi && !note.trim()} onClick={() => (renvoi ? void decider(false) : setRenvoi(true))}>
                            {t(T.renvoyer)}
                        </Button>
                    </div>
                </div>
            )}
            {erreur && <p role="alert" className="mt-2 text-xs text-destructive">{erreur}</p>}
        </Carte>
    );
}
