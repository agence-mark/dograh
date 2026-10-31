"use client";

/**
 * [.mark] passages-fiables (lot G): the « To triage » page. One line per flag, raised by the agent (lot F) or by the code
 * (conversation going in circles, unknown exit, agent/arbiter disagreement, transition without result, reply held back,
 * slow model), with a link to the call, a status (open · in progress · resolved · merged) and a filter by agent.
 * The server reads the last 30 days, the calls that carry a flag, 50 calls per page (R7).
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    changerLeStatutDUnSignalementApiV1TriRunIdPut,
    lireLaFileDeTriApiV1TriGet,
    lireLesPersonnesAssignablesApiV1TriPersonnesGet,
} from "@/client";
import type { LigneDeTri } from "@/client/types.gen";
import { ORIGINES_DE_TRI } from "@/components/builder/tests/libelles";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { useLangue } from "../langue/langue";
import { CATEGORIES, motifLisible, STATUTS, TYPES_DE_SIGNALEMENT } from "./libelles";
import { TauxDeSortieDImpasse } from "./TauxDeSortieDImpasse";

type Statut = LigneDeTri["statut"];
type Origine = "client" | "recette" | "code";
const ORIGINES: Origine[] = ["client", "recette", "code"];

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
    // [.mark] builder lot 6 : tri par origine, assigné, et création d'un test depuis la réplique.
    const [origine, setOrigine] = useState<Origine | "">("");
    const [personnes, setPersonnes] = useState<Array<{ id: number; nom: string }>>([]);
    const [agents, setAgents] = useState<Record<number, string>>({});
    const [erreur, setErreur] = useState<string | null>(null);

    const charger = useCallback(async () => {
        const reponse = await lireLaFileDeTriApiV1TriGet({ query: { page, workflow_id: agent === "" ? undefined : agent, origine: origine === "" ? undefined : origine } });
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
    }, [page, agent, origine]);

    useEffect(() => {
        void charger();
    }, [charger]);

    useEffect(() => {
        void lireLesPersonnesAssignablesApiV1TriPersonnesGet().then((r) => {
            if (!r.error && Array.isArray(r.data)) setPersonnes(r.data as Array<{ id: number; nom: string }>);
        });
    }, []);

    const classer = async (ligne: LigneDeTri, changement: { assigne?: number | null; origine?: Origine }) => {
        const reponse = await changerLeStatutDUnSignalementApiV1TriRunIdPut({
            path: { run_id: ligne.run_id },
            body: { identifiant: ligne.id, ...changement },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "The change was not saved"));
            return;
        }
        setLignes((avant) => (avant ?? []).map((l) => (l.run_id === ligne.run_id && l.id === ligne.id ? { ...l, ...changement } : l)));
    };

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
            <TauxDeSortieDImpasse
                agentChoisi={agent}
                onChoisir={(id) => {
                    setPage(0);
                    setAgent(id);
                }}
                onAgents={(noms) => setAgents((avant) => ({ ...noms, ...avant }))}
            />
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
                <label className="flex items-center gap-2 text-sm">
                    <span>{t({ en: "Origin", fr: "Origine" })}</span>
                    <select
                        aria-label={t({ en: "Filter by origin", fr: "Filtrer par origine" })}
                        className="h-9 rounded-md border bg-background px-2 text-sm"
                        value={origine}
                        onChange={(e) => {
                            setPage(0);
                            setOrigine(e.target.value as Origine | "");
                        }}
                    >
                        <option value="">{t({ en: "All origins", fr: "Toutes les origines" })}</option>
                        {ORIGINES.map((o) => (
                            <option key={o} value={o}>
                                {t(ORIGINES_DE_TRI[o].libelle)}
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
                            <div className="flex flex-wrap items-center gap-3 text-xs">
                                <label className="flex items-center gap-1">
                                    <span>{t({ en: "Assigned to", fr: "Assigné à" })}</span>
                                    <select
                                        aria-label={t({ en: "Assigned to", fr: "Assigné à" })}
                                        className="h-8 rounded-md border bg-background px-2"
                                        value={l.assigne ?? ""}
                                        onChange={(e) => void classer(l, { assigne: e.target.value === "" ? null : Number(e.target.value) })}
                                    >
                                        <option value="">{t({ en: "Nobody", fr: "Personne" })}</option>
                                        {personnes.map((p) => (
                                            <option key={p.id} value={p.id}>
                                                {p.nom}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                <label className="flex items-center gap-1">
                                    <span>{t({ en: "Origin", fr: "Origine" })}</span>
                                    <select
                                        aria-label={t({ en: "Origin of the flag", fr: "Origine du signalement" })}
                                        className="h-8 rounded-md border bg-background px-2"
                                        value={l.origine ?? ""}
                                        onChange={(e) => e.target.value !== "" && void classer(l, { origine: e.target.value as Origine })}
                                    >
                                        <option value="">
                                            {t({ en: "To decide", fr: "À décider" })}
                                            {l.origine_suggeree ? ` (${t({ en: "suggested", fr: "suggérée" })} : ${t(ORIGINES_DE_TRI[l.origine_suggeree].libelle)})` : ""}
                                        </option>
                                        {ORIGINES.map((o) => (
                                            <option key={o} value={o}>
                                                {t(ORIGINES_DE_TRI[o].libelle)}
                                            </option>
                                        ))}
                                    </select>
                                </label>
                                {(l.origine ?? l.origine_suggeree) && (
                                    <span className="text-muted-foreground" data-testid="suite-de-l-origine">
                                        → {t(ORIGINES_DE_TRI[(l.origine ?? l.origine_suggeree) as Origine].suite)}
                                    </span>
                                )}
                            </div>
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
                                <Link className="underline" href={`/workflow/${l.workflow_id}/run/${l.run_id}?creer_test=${Math.max(1, l.tour ?? 1)}`}>
                                    {t({ en: "Create a test", fr: "Créer un test" })}
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
