"use client";

/**
 * [.mark] passages-fiables (lot G): the « To triage » page. One line per flag, raised by the agent (lot F) or by the code
 * (conversation going in circles, unknown exit, agent/arbiter disagreement, transition without result, reply held back,
 * slow model), with a link to the call, a status (open · in progress · resolved · merged) and a filter by agent.
 * The server reads the last 30 days, the calls that carry a flag, 50 calls per page (R7).
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { changerLeStatutDUnSignalementApiV1TriRunIdPut, lireLaFileDeTriApiV1TriGet } from "@/client";
import type { LigneDeTri } from "@/client/types.gen";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";
import { CATEGORIES, motifLisible, STATUTS, TYPES_DE_SIGNALEMENT } from "./libelles";

type Statut = LigneDeTri["statut"];

const dateCourte = (iso?: string | null) => (iso ? iso.slice(0, 16).replace("T", " ") : "");

/** The reason of a line: the agent's own words as they are; the code's technical value in plain words, the value second. */
function MotifDeLaLigne({ ligne }: { ligne: LigneDeTri }) {
    const { t } = useLangue();
    if (ligne.source === "agent") return <p className="text-muted-foreground">{ligne.motif}</p>;
    const { lisible, technique } = motifLisible(ligne.motif ?? "", ligne.type);
    if (!lisible) return <p className="font-mono text-xs text-muted-foreground">{ligne.motif}</p>;
    return (
        <p className="text-muted-foreground" data-testid="motif-lisible">
            {t(lisible)}
            {technique && <span className="ml-2 font-mono text-xs opacity-70">({technique})</span>}
        </p>
    );
}

export function PageATrier() {
    const { t } = useLangue();
    const [lignes, setLignes] = useState<LigneDeTri[] | null>(null);
    const [page, setPage] = useState(0);
    const [aUneSuite, setAUneSuite] = useState(false);
    const [tronquee, setTronquee] = useState(false);
    const [agent, setAgent] = useState<number | "">("");
    const [agents, setAgents] = useState<Record<number, string>>({});
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const reponse = await lireLaFileDeTriApiV1TriGet({ query: { page, workflow_id: agent === "" ? undefined : agent } });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The queue could not be read"));
            return;
        }
        const donnees = reponse.data;
        setErreur(null);
        setLignes(donnees.lignes);
        setAUneSuite(donnees.a_une_suite);
        setTronquee(donnees.recherche_tronquee === true);
        setAgents((avant) => ({ ...avant, ...Object.fromEntries(donnees.lignes.map((l) => [l.workflow_id, l.workflow_nom])) }));
    }, [page, agent]);

    useEffect(() => {
        void charger();
    }, [charger]);

    const changer = async (ligne: LigneDeTri, statut: Statut) => {
        const reponse = await changerLeStatutDUnSignalementApiV1TriRunIdPut({
            path: { run_id: ligne.run_id },
            body: { identifiant: ligne.id, statut },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "The status was not saved"));
            return;
        }
        setLignes((avant) => (avant ?? []).map((l) => (l.run_id === ligne.run_id && l.id === ligne.id ? { ...l, statut } : l)));
    };

    return (
        <div className="space-y-4" data-testid="page-a-trier">
            <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-2 text-sm">
                    <span>{t({ en: "Agent", fr: "Agent" })}</span>
                    <select
                        aria-label={t({ en: "Filter by agent", fr: "Filtrer par agent" })}
                        className="h-9 rounded-md border bg-background px-2 text-sm"
                        value={agent}
                        onChange={(e) => {
                            setPage(0);
                            setAgent(e.target.value === "" ? "" : Number(e.target.value));
                        }}
                    >
                        <option value="">{t({ en: "All agents", fr: "Tous les agents" })}</option>
                        {Object.entries(agents).map(([id, nom]) => (
                            <option key={id} value={id}>
                                {nom}
                            </option>
                        ))}
                    </select>
                </label>
                <p className="text-xs text-muted-foreground">
                    {t({
                        en: "Last 30 days, calls that carry a flag, 50 calls per page.",
                        fr: "30 derniers jours, les appels qui portent un signalement, 50 appels par page.",
                    })}
                </p>
            </div>
            {tronquee && (
                <p className="text-xs text-muted-foreground" data-testid="a-trier-tronquee">
                    {t({
                        en: "The search stopped at the reading limit: older calls were not read.",
                        fr: "La recherche s'est arrêtée à la limite de lecture : les appels plus anciens n'ont pas été lus.",
                    })}
                </p>
            )}
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {lignes !== null && lignes.length === 0 && (
                <p className="rounded border p-4 text-sm text-muted-foreground" data-testid="a-trier-vide">
                    {t({ en: "Nothing to triage.", fr: "Rien à trier." })}
                </p>
            )}
            {lignes !== null && lignes.length > 0 && (
                <ul className="space-y-2">
                    {lignes.map((l) => (
                        <li key={`${l.run_id}-${l.id}`} className="space-y-1 rounded border p-3 text-sm" data-testid={`ligne-${l.run_id}-${l.id}`}>
                            <div className="flex flex-wrap items-center gap-2">
                                <span className="rounded bg-muted px-2 py-0.5 text-xs">
                                    {l.source === "agent" ? t({ en: "Agent", fr: "Agent" }) : t({ en: "Code", fr: "Code" })}
                                </span>
                                <span className="font-medium">{TYPES_DE_SIGNALEMENT[l.type] ? t(TYPES_DE_SIGNALEMENT[l.type]) : l.type}</span>
                                {l.categorie && CATEGORIES[l.categorie] && (
                                    <span className="text-xs text-muted-foreground">· {t(CATEGORIES[l.categorie])}</span>
                                )}
                                <select
                                    aria-label={t({ en: "Status", fr: "Statut" })}
                                    className="ml-auto h-8 rounded-md border bg-background px-2 text-xs"
                                    value={l.statut}
                                    onChange={(e) => void changer(l, e.target.value as Statut)}
                                >
                                    {STATUTS.map((s) => (
                                        <option key={s.valeur} value={s.valeur}>
                                            {t(s.libelle)}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            {l.motif && <MotifDeLaLigne ligne={l} />}
                            <p className="flex flex-wrap gap-x-3 text-xs text-muted-foreground">
                                <span>{l.workflow_nom}</span>
                                {l.etape && (
                                    <span>
                                        {t({ en: "Step", fr: "Étape" })} : {l.etape}
                                    </span>
                                )}
                                <span>{dateCourte(l.cree_le)}</span>
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
