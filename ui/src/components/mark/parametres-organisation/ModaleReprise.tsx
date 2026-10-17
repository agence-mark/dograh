"use client";

/**
 * [.mark] « Take over the fiches » (chantier agents-specialises, lot 11; the takeover is the lot-4 tool
 * of the fiche plan, C3/R7).
 *
 * Before a fiche stopped inheriting, an empty field was « inherited ». The takeover writes into each fiche
 * what it used to inherit, and attaches to each agent the one fiche its numbers lead to. This window
 * shows the TRIAL RUN first (the server's default: it lists what it would write and writes nothing), then
 * writes on a second, deliberate click. Replayable: a second run finds nothing to do. A value already on a
 * fiche is never replaced; what the takeover will not decide alone is listed apart, and nothing is written
 * for it. Centred window, never a side panel.
 */
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { repriseDesFichesApiV1OrganizationsEtablissementsReprisePost } from "@/client/sdk.gen";
import type { ResultatReprise } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { detailFromError } from "@/lib/apiError";

import { type Texte, useLangue } from "../langue/langue";

const SUJETS: Record<"fiche" | "rendez_vous" | "agent", Texte> = {
    fiche: { en: "Fiche", fr: "Fiche" },
    rendez_vous: { en: "Appointments", fr: "Rendez-vous" },
    agent: { en: "Agent", fr: "Agent" },
};

export function ModaleReprise({ ouverte, onFermer }: { ouverte: boolean; onFermer: (ecrit: boolean) => void }) {
    const { t } = useLangue();
    const [essai, setEssai] = useState<ResultatReprise | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [ecrit, setEcrit] = useState(false);

    const lancer = useCallback(async (ecrire: boolean) => {
        setEnCours(true);
        setErreur(null);
        const reponse = await repriseDesFichesApiV1OrganizationsEtablissementsReprisePost({ body: { ecrire } });
        setEnCours(false);
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "Takeover failed"));
            return;
        }
        setEssai(reponse.data);
        if (ecrire) {
            setEcrit(true);
            toast.success(t({ en: "Takeover written", fr: "Reprise écrite" }));
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // Opening the window runs the TRIAL: nothing is written until the second click.
    useEffect(() => {
        if (!ouverte) return;
        setEssai(null);
        setEcrit(false);
        void lancer(false);
    }, [ouverte, lancer]);

    const actions = essai?.actions ?? [];
    const aDecider = essai?.a_decider ?? [];

    return (
        <Dialog open={ouverte} onOpenChange={(o) => (o ? null : onFermer(ecrit))}>
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-3xl" data-testid="modale-reprise">
                <DialogHeader>
                    <DialogTitle>{t({ en: "Take over the fiches and agents", fr: "Reprendre les fiches et les agents" })}</DialogTitle>
                    <DialogDescription>
                        {t({
                            en: "Writes into each fiche what it used to inherit (hours, address, announcements, appointment settings) and attaches each agent to the fiche its numbers lead to. Below is the trial run: nothing is written yet. A value already on a fiche is never replaced.",
                            fr: "Écrit dans chaque fiche ce qu'elle héritait (horaires, adresse, annonces, réglages de rendez-vous) et rattache chaque agent à la fiche vers laquelle mènent ses numéros. Ci-dessous l'essai : rien n'est encore écrit. Une valeur déjà posée sur une fiche n'est jamais remplacée.",
                        })}
                    </DialogDescription>
                </DialogHeader>
                {erreur && (
                    <p className="text-sm text-destructive" role="alert" data-testid="erreur-reprise">
                        {erreur}
                    </p>
                )}
                {essai === null ? (
                    !erreur && <p className="text-sm text-muted-foreground">{t({ en: "Loading…", fr: "Chargement…" })}</p>
                ) : (
                    <div className="space-y-4">
                        <p className="text-sm font-medium" data-testid="etat-reprise">
                            {essai.ecrit
                                ? t({ en: "Written. These changes are in place:", fr: "Écrit. Ces changements sont en place :" })
                                : t({ en: "Trial run, nothing written. It would write:", fr: "Essai, rien d'écrit. Elle écrirait :" })}{" "}
                            <span className="text-muted-foreground">
                                {actions.length} {t({ en: "change(s)", fr: "changement(s)" })} · {essai.deja_a_jour ?? 0}{" "}
                                {t({ en: "already up to date", fr: "déjà à jour" })}
                            </span>
                        </p>
                        {actions.length > 0 && (
                            <table className="w-full text-left text-sm" data-testid="actions-reprise">
                                <thead className="text-xs text-muted-foreground">
                                    <tr>
                                        <th className="pr-2 font-normal">{t({ en: "What", fr: "Quoi" })}</th>
                                        <th className="pr-2 font-normal">{t({ en: "Target", fr: "Cible" })}</th>
                                        <th className="pr-2 font-normal">{t({ en: "Field", fr: "Champ" })}</th>
                                        <th className="font-normal">{t({ en: "Before → after", fr: "Avant → après" })}</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {actions.map((a, i) => (
                                        <tr key={`${a.sujet}-${a.cible}-${a.champ}-${i}`} className="border-t border-border align-top">
                                            <td className="py-1 pr-2">{t(SUJETS[a.sujet])}</td>
                                            <td className="py-1 pr-2">{a.cible}</td>
                                            <td className="py-1 pr-2 font-mono text-xs">{a.champ}</td>
                                            <td className="whitespace-pre-line py-1">
                                                <span className="text-muted-foreground">{a.avant ?? "—"}</span> → {a.apres ?? "—"}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                        {actions.length === 0 && (
                            <p className="text-sm text-muted-foreground" data-testid="reprise-rien">
                                {t({ en: "Nothing to write: everything is already as the takeover would leave it.", fr: "Rien à écrire : tout est déjà comme la reprise le laisserait." })}
                            </p>
                        )}
                        {aDecider.length > 0 && (
                            <div className="space-y-1" data-testid="a-decider-reprise">
                                <p className="text-sm font-medium">
                                    {t({ en: "To decide yourself (nothing is written for these):", fr: "À décider vous-même (rien n'est écrit pour ces cas) :" })}
                                </p>
                                <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                                    {aDecider.map((ligne, i) => (
                                        <li key={i}>{ligne}</li>
                                    ))}
                                </ul>
                            </div>
                        )}
                    </div>
                )}
                <DialogFooter>
                    <Button variant="outline" onClick={() => onFermer(ecrit)}>
                        {ecrit ? t({ en: "Close", fr: "Fermer" }) : t({ en: "Cancel", fr: "Annuler" })}
                    </Button>
                    {!ecrit && (
                        <Button onClick={() => void lancer(true)} disabled={enCours || essai === null || actions.length === 0} data-testid="ecrire-la-reprise">
                            {t({ en: "Write these changes", fr: "Écrire ces changements" })}
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
