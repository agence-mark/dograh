"use client";

/**
 * [.mark] Builder partie 3, lots 8 et 22 : « Utilisé dans », la liste des prompts qui citent un objet par une étiquette (calculée par le
 * serveur en lisant les prompts des agents de l'organisation, `GET /mark/etiquettes-prompt/utilise-dans`). Pour un bloc, chaque
 * prompt choisit de SUIVRE la dernière version en Recette ou de RESTER sur la sienne ; le choix réécrit l'étiquette dans le brouillon
 * de cet agent (rien n'est publié). « Ouvrir l'étape » mène à l'étape exacte du graphe.
 */
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
    corrigerUneEtiquetteApiV1MarkEtiquettesPromptWorkflowIdCorrigerPost,
    lireUtiliseDansApiV1MarkEtiquettesPromptUtiliseDansGet,
} from "@/client/sdk.gen";
import type { Citation } from "@/client/types.gen";
import { notifier } from "@/components/mark/notifications";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

import { useLangue } from "../langue/langue";
import { relireLesEtiquettes } from "./useCatalogueEtiquettes";

export function UtiliseDans({ cle, versionRecette }: { cle: string; /** Bloc : la dernière version en Recette (absent : pas un bloc). */ versionRecette?: number | null }) {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [citations, setCitations] = useState<Citation[] | null>(null);
    const [echec, setEchec] = useState(false);
    const [enCours, setEnCours] = useState<string | null>(null);
    const bloc = cle.startsWith("bloc:");

    const lire = useCallback(async () => {
        try {
            const r = await lireUtiliseDansApiV1MarkEtiquettesPromptUtiliseDansGet({ query: { cle } });
            if (r.error || !r.data) setEchec(true);
            else {
                setEchec(false);
                setCitations(r.data.citations);
            }
        } catch {
            setEchec(true);
        }
    }, [cle]);

    useEffect(() => {
        if (loading || !user) return;
        void lire();
    }, [lire, loading, user]);

    const choisir = async (c: Citation, version: number | null) => {
        const id = `${c.agent_id}-${c.champ}`;
        setEnCours(id);
        try {
            const r = await corrigerUneEtiquetteApiV1MarkEtiquettesPromptWorkflowIdCorrigerPost({
                path: { workflow_id: c.agent_id },
                body: version === null ? { type: "suivre", cle: c.cle, champ: c.champ } : { type: "passer_version", cle: c.cle, champ: c.champ, version },
            });
            if (r.error) {
                notifier.echec({ fr: "Choix non enregistré : l'agent a changé. La liste est relue.", en: "Choice not saved: the agent changed. The list is read again." }, { erreur: r.error });
            } else {
                notifier.succes(
                    version === null
                        ? { fr: "Ce prompt suit la dernière version (brouillon).", en: "This prompt follows the latest version (draft)." }
                        : { fr: `Ce prompt reste sur la v${version} (brouillon).`, en: `This prompt stays on v${version} (draft).` },
                );
            }
            relireLesEtiquettes();
            await lire();
        } finally {
            setEnCours(null);
        }
    };

    if (echec) return <p className="py-2 text-sm text-destructive">{t({ en: "Could not read where it is used. Reload the page.", fr: "Lecture impossible. Rechargez la page." })}</p>;
    if (citations === null) return <p className="py-2 text-sm text-muted-foreground">{t({ en: "Reading…", fr: "Lecture…" })}</p>;
    if (citations.length === 0)
        return <p className="py-2 text-sm text-muted-foreground" data-testid="utilise-dans-vide">{t({ en: "No prompt cites it yet.", fr: "Aucun prompt ne le cite pour l'instant." })}</p>;
    return (
        <ul className="divide-y" data-testid="utilise-dans">
            {citations.map((c) => {
                const id = `${c.agent_id}-${c.champ}`;
                const reste = c.version ?? null;
                return (
                    <li key={id} className="flex items-center gap-3 py-2.5 text-sm" data-citation={id}>
                        <span className="min-w-0 flex-1 truncate">
                            {c.agent}
                            {c.etape ? ` › ${t({ en: "Step", fr: "Étape" })} « ${c.etape} »` : ` › ${t({ en: "Settings", fr: "Réglages" })}`}
                        </span>
                        {c.noeud_id && (
                            <Link href={`/workflow/${c.agent_id}?etape=${encodeURIComponent(c.noeud_id)}`} className="shrink-0 text-xs text-muted-foreground hover:font-semibold">
                                {t({ en: "Open the step", fr: "Ouvrir l'étape" })}
                            </Link>
                        )}
                        {bloc && versionRecette && (
                            <div role="radiogroup" aria-label={t({ en: "Follow or stay", fr: "Suivre ou rester" })} className="flex shrink-0 rounded-md bg-muted p-0.5 text-xs">
                                {[null, reste ?? versionRecette].map((v) => {
                                    const choisi = v === reste;
                                    return (
                                        <button
                                            key={v ?? "suivre"}
                                            type="button"
                                            role="radio"
                                            aria-checked={choisi}
                                            disabled={enCours === id || choisi}
                                            onClick={() => void choisir(c, v)}
                                            className={cn("cursor-pointer rounded px-2 py-1 hover:font-semibold", choisi && "bg-background font-medium shadow-sm")}
                                        >
                                            {v === null ? t({ en: "Follows the latest", fr: "Suit la dernière" }) : t({ en: `Stays on v${v}`, fr: `Reste sur v${v}` })}
                                        </button>
                                    );
                                })}
                            </div>
                        )}
                    </li>
                );
            })}
        </ul>
    );
}
