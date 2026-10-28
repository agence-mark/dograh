"use client";

/**
 * [.mark] passages-fiables (lot G): the « Alerts » page. The customer's problems raised during calls: call ended in error,
 * tool failure, model outage, transfer failed. Always listed here; the grouped mail (one per call) is an extra output,
 * never the only one. The portal will read the same route later.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { lireLesAlertesApiV1AlertesGet } from "@/client";
import type { LigneDAlerte } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";
import { ETATS_DU_MAIL, SANS_MAIL, TYPES_D_ALERTE } from "./libelles";

const dateCourte = (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

export function PageAlertes() {
    const { t } = useLangue();
    const [lignes, setLignes] = useState<LigneDAlerte[] | null>(null);
    const [page, setPage] = useState(0);
    const [aUneSuite, setAUneSuite] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const reponse = await lireLesAlertesApiV1AlertesGet({ query: { page } });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The alerts could not be read"));
            return;
        }
        setErreur(null);
        setLignes(reponse.data.lignes);
        setAUneSuite(reponse.data.a_une_suite);
    }, [page]);

    useEffect(() => {
        void charger();
    }, [charger]);

    return (
        <div className="space-y-4" data-testid="page-alertes">
            <p className="text-xs text-muted-foreground">
                {t({
                    en: "Last 30 days, calls that raised an alert, 50 calls per page.",
                    fr: "30 derniers jours, les appels qui ont levé une alerte, 50 appels par page.",
                })}
            </p>
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {lignes !== null && lignes.length === 0 && (
                <p className="rounded border p-4 text-sm text-muted-foreground" data-testid="alertes-vide">
                    {t({ en: "No alert.", fr: "Aucune alerte." })}
                </p>
            )}
            {lignes !== null && lignes.length > 0 && (
                <ul className="space-y-2">
                    {lignes.map((l) => (
                        <li key={`${l.run_id}-${l.id}`} className="space-y-1 rounded border p-3 text-sm" data-testid={`alerte-${l.run_id}-${l.id}`}>
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="font-medium">{TYPES_D_ALERTE[l.type] ? t(TYPES_D_ALERTE[l.type]) : l.type}</span>
                                {l.outil && <span className="text-xs text-muted-foreground">· {l.outil}</span>}
                                <span className="ml-auto text-xs text-muted-foreground">
                                    {l.mail && ETATS_DU_MAIL[l.mail] ? t(ETATS_DU_MAIL[l.mail]) : t(SANS_MAIL)}
                                </span>
                            </div>
                            {l.detail && <p className="text-muted-foreground">{l.detail}</p>}
                            <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                                <span>{l.workflow_nom}</span>
                                {l.etape && (
                                    <span>
                                        {t({ en: "Step", fr: "Étape" })} : {l.etape}
                                    </span>
                                )}
                                <span>{dateCourte(l.heure ?? l.cree_le)}</span>
                                <Link className="underline" href={`/workflow/${l.workflow_id}/run/${l.run_id}`}>
                                    {t({ en: "Open the call", fr: "Ouvrir l'appel" })} n° {l.run_id}
                                </Link>
                            </p>
                        </li>
                    ))}
                </ul>
            )}
            <div className="flex items-center gap-2">
                <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                    {t({ en: "Previous", fr: "Précédent" })}
                </Button>
                <span className="text-xs text-muted-foreground">{page + 1}</span>
                <Button variant="outline" size="sm" disabled={!aUneSuite} onClick={() => setPage((p) => p + 1)}>
                    {t({ en: "Next", fr: "Suivant" })}
                </Button>
            </div>
        </div>
    );
}
