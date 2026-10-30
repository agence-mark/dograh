"use client";

/**
 * [.mark] builder-agent-vocal (lot 2): the queue of proposals (from the builder and from the team). A person accepts
 * or refuses; accepting a move to Recipe needs the bench that proves it; a refusal keeps its reason.
 */
import { useCallback, useEffect, useState } from "react";

import {
    accepterApiV1BuilderBibliothequePropositionsIdentifiantAccepterPost,
    listerLesPropositionsApiV1BuilderBibliothequePropositionsGet,
    refuserApiV1BuilderBibliothequePropositionsIdentifiantRefuserPost,
} from "@/client";
import type { Proposition } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import { dateCourte, TYPES_DE_PROPOSITION } from "./libelles";

const CHAMP = "w-full rounded-md border bg-background px-2 py-1.5 text-sm";

export function PropositionsDeLaBibliotheque({ onDecision }: { onDecision?: () => void }) {
    const { t } = useLangue();
    const [liste, setListe] = useState<Proposition[] | null>(null);
    const [erreur, setErreur] = useState<string | null>(null);
    const [banc, setBanc] = useState<Record<string, string>>({});
    const [motif, setMotif] = useState<Record<string, string>>({});

    const charger = useCallback(async () => {
        const reponse = await listerLesPropositionsApiV1BuilderBibliothequePropositionsGet({ query: { etat: "en_attente" } });
        if (reponse.error || !reponse.data) {
            setErreur(detailFromError(reponse.error, "The queue could not be read"));
            return;
        }
        setErreur(null);
        setListe(reponse.data);
    }, []);

    useEffect(() => {
        void charger();
    }, [charger]);

    const accepter = async (p: Proposition) => {
        const description = (banc[p.id] ?? "").trim();
        const reponse = await accepterApiV1BuilderBibliothequePropositionsIdentifiantAccepterPost({
            path: { identifiant: p.id },
            body: description ? { banc: { description } } : {},
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "The proposal was not accepted"));
            return;
        }
        await charger();
        onDecision?.();
    };

    const refuser = async (p: Proposition) => {
        const reponse = await refuserApiV1BuilderBibliothequePropositionsIdentifiantRefuserPost({
            path: { identifiant: p.id },
            body: { motif: (motif[p.id] ?? "").trim() },
        });
        if (reponse.error) {
            setErreur(detailFromError(reponse.error, "The proposal was not refused"));
            return;
        }
        await charger();
        onDecision?.();
    };

    return (
        <div className="space-y-3" data-testid="propositions">
            {erreur && (
                <p role="alert" className="text-sm text-destructive">
                    {erreur}
                </p>
            )}
            {liste !== null && liste.length === 0 && (
                <p className="rounded border p-4 text-sm text-muted-foreground" data-testid="propositions-vide">
                    {t({ en: "No proposal waiting.", fr: "Aucune proposition en attente." })}
                </p>
            )}
            <ul className="space-y-2">
                {(liste ?? []).map((p) => (
                    <li key={p.id} className="space-y-2 rounded border p-3 text-sm" data-testid={`proposition-${p.id}`}>
                        <div className="flex flex-wrap items-center gap-2">
                            <span className="rounded bg-muted px-2 py-0.5 text-xs">{t(TYPES_DE_PROPOSITION[p.type])}</span>
                            <span className="font-medium">
                                {p.famille}/{p.slug}
                            </span>
                            {p.version != null && <span className="text-xs text-muted-foreground">v{p.version}</span>}
                            <span className="text-xs text-muted-foreground">
                                {p.auteur} · {dateCourte(p.date)}
                            </span>
                        </div>
                        <p>{p.justification}</p>
                        {p.contenu && (
                            <pre className="max-h-40 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(p.contenu, null, 2)}</pre>
                        )}
                        {p.banc && (
                            <p className="text-xs">
                                {t({ en: "Bench offered", fr: "Banc proposé" })} : {p.banc.description}
                            </p>
                        )}
                        <div className="grid gap-2 md:grid-cols-2">
                            <div className="space-y-1">
                                {p.type !== "rejet" && (
                                    <label className="block space-y-1">
                                        <span>
                                            {p.type === "passage_recette"
                                                ? t({ en: "The bench that proves it", fr: "Le banc qui la prouve" })
                                                : t({ en: "Bench (to make it a Recipe at once)", fr: "Banc (pour en faire une Recette tout de suite)" })}
                                        </span>
                                        <input
                                            className={CHAMP}
                                            value={banc[p.id] ?? ""}
                                            onChange={(e) => setBanc((avant) => ({ ...avant, [p.id]: e.target.value }))}
                                        />
                                    </label>
                                )}
                                <Button size="sm" onClick={() => void accepter(p)}>
                                    {t({ en: "Accept", fr: "Accepter" })}
                                </Button>
                            </div>
                            <div className="space-y-1">
                                <label className="block space-y-1">
                                    <span>{t({ en: "Reason for refusing", fr: "Raison du refus" })}</span>
                                    <input
                                        className={CHAMP}
                                        value={motif[p.id] ?? ""}
                                        onChange={(e) => setMotif((avant) => ({ ...avant, [p.id]: e.target.value }))}
                                    />
                                </label>
                                <Button size="sm" variant="outline" disabled={!(motif[p.id] ?? "").trim()} onClick={() => void refuser(p)}>
                                    {t({ en: "Refuse", fr: "Refuser" })}
                                </Button>
                            </div>
                        </div>
                    </li>
                ))}
            </ul>
        </div>
    );
}
