"use client";

/**
 * [.mark] passages-fiables (lot G): the « Alerts » page. The customer's problems raised during calls: call ended in error,
 * tool failure, model outage, transfer failed. Always listed here; the grouped mail (one per call) is an extra output,
 * never the only one. The portal will read the same route later.
 */
import { BellOff } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { lireLesAlertesApiV1AlertesGet } from "@/client";
import type { LigneDAlerte } from "@/client/types.gen";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Cellule, Ligne, Tableau } from "@/components/mark/studio/tableau";
import { Button } from "@/components/ui/button";
import { formatDateRelative } from "@/lib/dateTime";

import { useLangue } from "../langue/langue";
import { ETATS_DU_MAIL, SANS_MAIL, TYPES_D_ALERTE } from "./libelles";

const dateCourte = (iso: string | null | undefined, langue: "fr" | "en") => (iso ? formatDateRelative(iso, langue) : "");

/**
 * V2 : un tableau nu (jamais de cadre autour d'une liste), un état vide et un état d'erreur de l'écran (jamais le texte
 * du serveur), le lien de l'appel sans soulignement. La fenêtre (30 jours, 50 par page) est dite dans le « ! » du titre.
 */
export function PageAlertes() {
    const { t, langue } = useLangue();
    const [lignes, setLignes] = useState<LigneDAlerte[] | null>(null);
    const [page, setPage] = useState(0);
    const [aUneSuite, setAUneSuite] = useState(false);
    const [erreur, setErreur] = useState(false);

    const charger = useCallback(async () => {
        const reponse = await lireLesAlertesApiV1AlertesGet({ query: { page } });
        if (reponse.error || !reponse.data) {
            setErreur(true);
            return;
        }
        setErreur(false);
        setLignes(reponse.data.lignes);
        setAUneSuite(reponse.data.a_une_suite);
    }, [page]);

    useEffect(() => {
        void charger();
    }, [charger]);

    if (erreur) {
        return (
            <div data-testid="page-alertes">
                <EtatVide cas="erreur" reessayer={() => void charger()} />
            </div>
        );
    }
    if (lignes === null) {
        return (
            <div data-testid="page-alertes">
                <EtatVide cas="chargement" />
            </div>
        );
    }
    if (lignes.length === 0 && page === 0) {
        return (
            <div data-testid="page-alertes">
                <EtatVide cas="premier" icone={BellOff} titre={t({ en: "No alert.", fr: "Aucune alerte." })} />
            </div>
        );
    }

    return (
        <div className="space-y-4" data-testid="page-alertes">
            <Tableau
                colonnes={[
                    { titre: t({ en: "Alert", fr: "Alerte" }) },
                    { titre: t({ en: "Agent", fr: "Agent" }) },
                    { titre: t({ en: "Mail", fr: "Mail" }) },
                    { titre: t({ en: "When", fr: "Quand" }) },
                    { titre: t({ en: "Call", fr: "Appel" }), droite: true },
                ]}
            >
                {lignes.map((l) => (
                    <Ligne key={`${l.run_id}-${l.id}`}>
                        <Cellule
                            principale
                            sous={[l.outil ? `· ${l.outil}` : null, l.detail].filter(Boolean).join(" ") || undefined}
                        >
                            {TYPES_D_ALERTE[l.type] ? t(TYPES_D_ALERTE[l.type]) : l.type}
                        </Cellule>
                        <Cellule sous={l.etape ? `${t({ en: "Step", fr: "Étape" })} : ${l.etape}` : undefined}>{l.workflow_nom}</Cellule>
                        <Cellule>{l.mail && ETATS_DU_MAIL[l.mail] ? t(ETATS_DU_MAIL[l.mail]) : t(SANS_MAIL)}</Cellule>
                        <Cellule>{dateCourte(l.heure ?? l.cree_le, langue)}</Cellule>
                        <Cellule droite>
                            <Link className="cursor-pointer hover:font-medium" href={`/workflow/${l.workflow_id}/run/${l.run_id}`}>
                                {t({ en: "Open the call", fr: "Ouvrir l'appel" })} n° {l.run_id}
                            </Link>
                        </Cellule>
                    </Ligne>
                ))}
            </Tableau>
            {(page > 0 || aUneSuite) && (
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>
                        {t({ en: "Previous", fr: "Précédent" })}
                    </Button>
                    <span className="text-xs text-muted-foreground">{page + 1}</span>
                    <Button variant="outline" size="sm" disabled={!aUneSuite} onClick={() => setPage((p) => p + 1)}>
                        {t({ en: "Next", fr: "Suivant" })}
                    </Button>
                </div>
            )}
        </div>
    );
}
