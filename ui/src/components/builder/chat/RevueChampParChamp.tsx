"use client";

/**
 * [.mark] builder partie 2, U5 (lot C2) : la revue des changements du builder, champ par champ (« changement 2/5 »).
 * Accepter / Refuser un changement, ou tout accepter / tout refuser ; chaque acceptation range une version de brouillon
 * restaurable (« Revenir avant »). Les changements en attente restent signalés au-dessus de la saisie (E88).
 * Jamais une publication : un brouillon, relu par une personne.
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import {
    accepterLesChangementsApiV1BuilderFilsFilIdChangementsAccepterPost,
    lireLesChangementsApiV1BuilderFilsFilIdChangementsGet,
    listerLesVersionsApiV1BuilderAgentsWorkflowIdVersionsGet,
    refuserLesChangementsApiV1BuilderFilsFilIdChangementsRefuserPost,
    restaurerUneVersionApiV1BuilderAgentsWorkflowIdVersionsNumeroRestaurerPost,
} from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { notifier } from "@/components/mark/notifications/notifier";
import { Button } from "@/components/ui/button";
import { echecAffiche, phraseEchec } from "@/components/mark/notifications/echec-affiche";
import { FenetreRestauration } from "./FenetreRestauration";

const T = {
    titre: { en: "Change", fr: "Changement" },
    sur: { en: "of", fr: "sur" },
    champ: { en: "Field", fr: "Champ" },
    avant: { en: "Before", fr: "Avant" },
    apres: { en: "After", fr: "Après" },
    vide: { en: "(empty)", fr: "(vide)" },
    accepter: { en: "Accept", fr: "Accepter" },
    refuser: { en: "Refuse", fr: "Refuser" },
    toutAccepter: { en: "Accept all", fr: "Tout accepter" },
    toutRefuser: { en: "Refuse all", fr: "Tout refuser" },
    aucun: { en: "No change to review.", fr: "Aucun changement à relire." },
    versions: { en: "Saved versions", fr: "Versions enregistrées" },
    revenir: { en: "Go back before this", fr: "Revenir avant celle-ci" },
    invalide: { en: "This change no longer applies.", fr: "Ce changement ne s'applique plus." },
} satisfies Record<string, Texte>;

export type Changement = { rang: number; op: string; cible: string | null; champ: string; avant: unknown; apres: unknown; invalide?: boolean };
type Version = { numero: number; cause: string; date: string };

export function montrer(valeur: unknown, vide: string): string {
    if (valeur === null || valeur === undefined || valeur === "") return vide;
    return typeof valeur === "string" ? valeur : JSON.stringify(valeur, null, 2);
}

export function RevueChampParChamp({
    filId,
    workflowId,
    apres,
}: {
    filId: number;
    workflowId: number | null;
    /** Appelé après chaque décision (le fil relit son compteur de changements). */
    apres?: () => void;
}) {
    const { t } = useLangue();
    const [liste, setListe] = useState<Changement[]>([]);
    const [rang, setRang] = useState(0);
    const [versions, setVersions] = useState<Version[]>([]);
    const [erreur, setErreur] = useState<string | null>(null);
    // Lot M : revenir à une version passe d'abord par l'aperçu (ce qui sera perdu), puis la confirmation.
    const [aApercevoir, setAApercevoir] = useState<number | null>(null);

    const charger = useCallback(async () => {
        const r = await lireLesChangementsApiV1BuilderFilsFilIdChangementsGet({ path: { fil_id: filId } });
        if (r.error || !r.data) return setErreur(echecAffiche(r.error));
        const donnees = r.data as { changements: Changement[] };
        setListe(donnees.changements);
        setRang((n) => Math.min(n, Math.max(donnees.changements.length - 1, 0)));
        if (workflowId !== null) {
            const v = await listerLesVersionsApiV1BuilderAgentsWorkflowIdVersionsGet({ path: { workflow_id: workflowId }, query: { fil_id: filId } });
            if (v.data) setVersions(v.data as Version[]);
        }
    }, [filId, workflowId]);

    useEffect(() => {
        void charger();
    }, [charger]);

    const decider = async (accepter: boolean, rangs: number[]) => {
        const appel = accepter
            ? accepterLesChangementsApiV1BuilderFilsFilIdChangementsAccepterPost
            : refuserLesChangementsApiV1BuilderFilsFilIdChangementsRefuserPost;
        const r = await appel({ path: { fil_id: filId }, body: { rangs } });
        if (r.error) {
            setErreur(phraseEchec(r.error));
            notifier.echec({ en: "The decision could not be saved. Try again.", fr: "La décision n'a pas pu être enregistrée. Réessayez." }, { erreur: r.error });
            return;
        }
        setErreur(null);
        notifier.succes(accepter ? { en: "Changes accepted.", fr: "Changements acceptés." } : { en: "Changes refused.", fr: "Changements refusés." });
        await charger();
        apres?.();
    };

    const revenir = async (numero: number) => {
        if (workflowId === null) return;
        setAApercevoir(null);
        const r = await restaurerUneVersionApiV1BuilderAgentsWorkflowIdVersionsNumeroRestaurerPost({ path: { workflow_id: workflowId, numero } });
        if (r.error) {
            setErreur(phraseEchec(r.error));
            notifier.echec({ en: "The version could not be restored. Try again.", fr: "La version n'a pas pu être restaurée. Réessayez." }, { erreur: r.error });
            return;
        }
        setErreur(null);
        notifier.succes({ en: "Version restored.", fr: "Version restaurée." });
        await charger();
        apres?.();
    };

    const courant = liste[rang];
    return (
        <section className="space-y-3 py-1" data-carte="revue">
            {courant ? (
                <>
                    <div className="flex items-center justify-between gap-2">
                        <h4 className="text-sm font-semibold">
                            {t(T.titre)} {rang + 1}/{liste.length}
                        </h4>
                        <div className="flex gap-1">
                            <Button size="icon" variant="ghost" aria-label="<" disabled={rang === 0} onClick={() => setRang(rang - 1)}>
                                <ChevronLeft className="size-4" />
                            </Button>
                            <Button size="icon" variant="ghost" aria-label=">" disabled={rang >= liste.length - 1} onClick={() => setRang(rang + 1)}>
                                <ChevronRight className="size-4" />
                            </Button>
                        </div>
                    </div>
                    <p className="text-sm">
                        <span className="font-semibold">{t(T.champ)} : </span>
                        {courant.cible ? `${courant.cible} · ` : ""}
                        {courant.champ}
                    </p>
                    <div className="grid gap-2 sm:grid-cols-2">
                        <div>
                            <p className="text-xs font-semibold">{t(T.avant)}</p>
                            <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap" data-cote="avant">
                                {montrer(courant.avant, t(T.vide))}
                            </pre>
                        </div>
                        <div>
                            <p className="text-xs font-semibold">{t(T.apres)}</p>
                            <pre className="max-h-48 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap" data-cote="apres">
                                {montrer(courant.apres, t(T.vide))}
                            </pre>
                        </div>
                    </div>
                    {courant.invalide && <p className="text-xs text-destructive">{t(T.invalide)}</p>}
                    <div className="flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => void decider(true, [courant.rang])}>
                            {t(T.accepter)}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => void decider(false, [courant.rang])}>
                            {t(T.refuser)}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void decider(true, [])}>
                            {t(T.toutAccepter)}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => void decider(false, [])}>
                            {t(T.toutRefuser)}
                        </Button>
                    </div>
                </>
            ) : (
                <p className="text-sm text-muted-foreground">{t(T.aucun)}</p>
            )}
            {versions.length > 0 && (
                <div>
                    <p className="text-xs font-semibold">{t(T.versions)}</p>
                    <ul className="space-y-1">
                        {versions.map((v) => (
                            <li key={v.numero} className="flex items-center gap-2 text-xs text-muted-foreground">
                                <span>
                                    #{v.numero} · {v.cause} · {new Date(v.date).toLocaleString()}
                                </span>
                                <button type="button" className="cursor-pointer hover:font-semibold" onClick={() => setAApercevoir(v.numero)}>
                                    {t(T.revenir)}
                                </button>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
            {erreur && <p className="text-sm text-destructive">{erreur}</p>}
            {aApercevoir !== null && workflowId !== null && (
                <FenetreRestauration workflowId={workflowId} numero={aApercevoir} confirmer={() => revenir(aApercevoir)} fermer={() => setAApercevoir(null)} />
            )}
        </section>
    );
}
