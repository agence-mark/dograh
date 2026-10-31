"use client";

/**
 * [.mark] builder-agent-vocal (lot 6, B30): the agents that use a recipe, and « Prepare the updates ». For each agent of the
 * organization the builder prepares a DRAFT with the new version, replays its suite and shows the result; a person publishes agent
 * by agent. An agent that customized the recipe gets a proposal, never an overwrite. Nothing is published from here.
 */
import { useEffect, useState } from "react";

import {
    agentsDUneRecetteApiV1BuilderTestsRecetteFamilleSlugAgentsGet,
    preparerLesMisesAJourApiV1BuilderTestsRecetteFamilleSlugPreparerPost,
} from "@/client";
import type { Texte } from "@/components/mark/langue/langue";
import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { detailFromError } from "@/lib/apiError";

import type { AgentDeRecette } from "./types";

const ETATS: Record<string, Texte> = {
    a_jour: { en: "up to date", fr: "à jour" },
    brouillon_prepare: { en: "draft prepared", fr: "brouillon préparé" },
    proposition: { en: "proposal (customized, nothing overwritten)", fr: "proposition (personnalisée, rien d'écrasé)" },
    autre_organisation: { en: "other organization", fr: "autre organisation" },
    refuse: { en: "refused", fr: "refusé" },
};

interface LigneDePreparation {
    agent: number;
    etat: string;
    message?: string;
    suite?: { ok: boolean; total: number; echecs: number; disponible: boolean };
}

export function AgentsDeLaRecette({ famille, slug }: { famille: string; slug: string }) {
    const { t } = useLangue();
    const [version, setVersion] = useState<number | null>(null);
    const [agents, setAgents] = useState<AgentDeRecette[] | null>(null);
    const [lignes, setLignes] = useState<LigneDePreparation[] | null>(null);
    const [enCours, setEnCours] = useState(false);
    const [erreur, setErreur] = useState<string | null>(null);

    useEffect(() => {
        void agentsDUneRecetteApiV1BuilderTestsRecetteFamilleSlugAgentsGet({ path: { famille, slug } }).then((r) => {
            if (r.error) setErreur(detailFromError(r.error, "The agents could not be read"));
            else {
                const d = r.data as { version: number; agents: AgentDeRecette[] };
                setVersion(d.version);
                setAgents(d.agents);
            }
        });
    }, [famille, slug]);

    const preparer = async () => {
        setEnCours(true);
        const r = await preparerLesMisesAJourApiV1BuilderTestsRecetteFamilleSlugPreparerPost({ path: { famille, slug }, body: { rejouer_la_suite: true } });
        setEnCours(false);
        if (r.error) {
            setErreur(detailFromError(r.error, "The updates could not be prepared"));
            return;
        }
        setLignes((r.data as { agents: LigneDePreparation[] }).agents);
    };

    if (agents === null) return erreur ? <p role="alert" className="text-sm text-destructive">{erreur}</p> : null;
    const aMettreAJour = agents.filter((a) => !a.a_jour).length;
    return (
        <section className="space-y-2 text-sm" data-testid="agents-de-la-recette">
            <h3 className="font-medium">{t({ en: "Agents using this recipe", fr: "Agents qui utilisent cette recette" })} ({agents.length})</h3>
            {agents.length === 0 && <p className="text-muted-foreground">{t({ en: "No agent yet.", fr: "Aucun agent pour l'instant." })}</p>}
            <ul className="space-y-0.5">
                {agents.map((a) => (
                    <li key={`${a.organisation}-${a.agent}`} className="flex gap-2">
                        <span>#{a.agent}</span>
                        <span className="text-muted-foreground">
                            v{a.version ?? "?"} {a.a_jour ? "" : `→ v${version}`}
                        </span>
                    </li>
                ))}
            </ul>
            {aMettreAJour > 0 && (
                <Button variant="outline" size="sm" disabled={enCours} onClick={() => void preparer()}>
                    {t({ en: "Prepare the updates (drafts, nothing published)", fr: "Préparer les mises à jour (brouillons, rien de publié)" })}
                </Button>
            )}
            {erreur && <p role="alert" className="text-destructive">{erreur}</p>}
            {lignes && (
                <ul className="space-y-1" data-testid="mises-a-jour-preparees">
                    {lignes.map((l) => (
                        <li key={l.agent} className="rounded border p-2">
                            #{l.agent} · {t(ETATS[l.etat] ?? { en: l.etat, fr: l.etat })}
                            {l.suite && l.suite.disponible && (
                                <span className="ml-2">
                                    {l.suite.ok ? t({ en: "suite green", fr: "suite verte" }) : `${l.suite.echecs} ${t({ en: "failure(s)", fr: "échec(s)" })}`}
                                </span>
                            )}
                            {l.message && <span className="ml-2 text-xs text-muted-foreground">{l.message}</span>}
                        </li>
                    ))}
                </ul>
            )}
        </section>
    );
}
