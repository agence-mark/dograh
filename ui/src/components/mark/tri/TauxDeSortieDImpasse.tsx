"use client";

/**
 * [.mark] agent-facon-tala (lot D3), porté sur « À améliorer » à la clôture (D2, décision d'Evan 09/11 : l'ancienne page « À trier » est
 * retirée). Un onglet : une ligne par agent sur les 7 ou 30 derniers jours : les appels, la part passée par une impasse, la part où le
 * modèle a été repris et s'est rattrapé seul (relances répétées, aucune impasse). Les relances sont seulement comptées, jamais des
 * lignes à trier. Aucun seuil, aucune alerte : les chiffres se lisent. Un clic sur un agent l'ouvre. Tableau sans cadre.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { lireLesTauxDeSortieDImpasseApiV1TriTauxGet } from "@/client";
import type { LigneDeTaux } from "@/client/types.gen";
import { echecAffiche } from "@/components/mark/notifications/echec-affiche";
import { ECHECS } from "@/components/mark/notifications/phrases-echec";
import { EtatVide } from "../studio/etat-vide";
import { Cellule, Ligne, Tableau } from "../studio/tableau";
import { useLangue } from "../langue/langue";

const PERIODES = [7, 30] as const;

const pourcent = (part?: number | null) => (part === null || part === undefined ? "—" : `${Math.round(part * 100)} %`);

export function TauxDeSortieDImpasse() {
    const { t } = useLangue();
    const [jours, setJours] = useState<number>(7);
    const [lignes, setLignes] = useState<LigneDeTaux[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    // La période choisie à l'instant où une réponse arrive : une réponse d'une autre période est périmée et ignorée.
    const periodeCourante = useRef(jours);
    periodeCourante.current = jours;

    const charger = useCallback(async () => {
        const demandee = jours;
        const reponse = await lireLesTauxDeSortieDImpasseApiV1TriTauxGet({ query: { jours: demandee } });
        if (demandee !== periodeCourante.current) return;
        if (reponse.error || !reponse.data) {
            setErreur(echecAffiche(reponse.error, ECHECS.triTaux));
            return;
        }
        setErreur(null);
        setLignes(reponse.data.lignes);
    }, [jours]);

    useEffect(() => {
        void charger();
    }, [charger]);

    return (
        <section className="space-y-3" data-testid="taux-impasse" aria-label={t({ en: "Dead-end rates by agent", fr: "Taux d'impasse par agent" })}>
            <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-sm font-medium">{t({ en: "Dead ends by agent", fr: "Impasses par agent" })}</h2>
                <div className="flex gap-1" role="group" aria-label={t({ en: "Period", fr: "Période" })}>
                    {PERIODES.map((p) => (
                        <button
                            key={p}
                            type="button"
                            aria-pressed={jours === p}
                            className={`h-7 cursor-pointer rounded-md px-2 text-xs ${jours === p ? "bg-muted font-medium" : "text-muted-foreground hover:font-medium"}`}
                            onClick={() => setJours(p)}
                        >
                            {p} {t({ en: "days", fr: "jours" })}
                        </button>
                    ))}
                </div>
            </div>
            {erreur ? (
                <EtatVide cas="erreur" compact reessayer={() => void charger()} />
            ) : lignes === null ? (
                <EtatVide cas="chargement" lignes={3} />
            ) : lignes.length === 0 ? (
                <p className="py-6 text-sm text-muted-foreground" data-testid="taux-vide">
                    {t({ en: "No call over this period.", fr: "Aucun appel sur cette période." })}
                </p>
            ) : (
                <Tableau
                    colonnes={[
                        { titre: t({ en: "Agent", fr: "Agent" }) },
                        { titre: t({ en: "Calls", fr: "Appels" }), droite: true },
                        { titre: t({ en: "With a dead end", fr: "Avec impasse" }), droite: true },
                        { titre: t({ en: "Recovered by itself", fr: "Repris, sans impasse" }), droite: true },
                    ]}
                >
                    {lignes.map((l) => (
                        <Ligne key={l.workflow_id} href={`/workflow/${l.workflow_id}`}>
                            <Cellule principale>
                                <span data-testid={`taux-${l.workflow_id}`}>{l.workflow_nom}</span>
                            </Cellule>
                            <Cellule droite>{l.appels}</Cellule>
                            <Cellule droite>
                                <span data-testid={`part-impasse-${l.workflow_id}`}>
                                    {pourcent(l.part_impasse)} <span className="text-xs text-muted-foreground">({l.avec_impasse})</span>
                                </span>
                            </Cellule>
                            <Cellule droite>
                                <span data-testid={`part-reprise-${l.workflow_id}`}>
                                    {pourcent(l.part_reprise)}{" "}
                                    <span className="text-xs text-muted-foreground">
                                        ({l.avec_reprise_sans_impasse} / {l.appels_avec_compteur} {t({ en: "calls with the counter", fr: "appels avec le compteur" })})
                                    </span>
                                </span>
                            </Cellule>
                        </Ligne>
                    ))}
                </Tableau>
            )}
        </section>
    );
}
