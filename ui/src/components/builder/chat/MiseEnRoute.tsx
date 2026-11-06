"use client";

/**
 * [.mark] Partie 3, N4 (décision 19, maquette `SuiviBuilder`) : « Mise en route », une carte sous « À améliorer » avec une barre de
 * progression reliée à « Prêt à publier » (la liste du lot L3a, `GET /workflow/{id}/preparation`, la même que Réglages et la fenêtre de
 * publication). L'agent suivi est le premier de la liste ; un clic ouvre ses Réglages. Aucune carte quand l'organisation n'a pas
 * encore d'agent (rien à mettre en route).
 */
import { Rocket } from "lucide-react";
import Link from "next/link";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { adresseOnglet } from "@/components/mark/agent/onglets-agent";
import { useListeDePret } from "@/components/mark/agent/pret/ListePret";

const T = {
    titre: { en: "Getting started", fr: "Mise en route" },
    bloque: { en: "A check still blocks the publication", fr: "Un contrôle bloque encore la publication" },
    reste: { en: "A few points to look at before publishing", fr: "Quelques points à voir avant de publier" },
    pret: { en: "Ready to publish", fr: "Prêt à publier" },
    ou: { en: "Settings › Ready to publish", fr: "Réglages › Prêt à publier" },
    progression: { en: "Progress toward ready to publish", fr: "Progression vers prêt à publier" },
    sur: { en: "of", fr: "sur" },
} satisfies Record<string, Texte>;

export function MiseEnRoute({ agent }: { agent: { id: number; name: string } | null }) {
    if (!agent) return null;
    return <MiseEnRouteDeLAgent agent={agent} />;
}

function MiseEnRouteDeLAgent({ agent }: { agent: { id: number; name: string } }) {
    const { t } = useLangue();
    const { lignes } = useListeDePret(agent.id);
    // Rien à montrer tant que la liste n'est pas lue (la carte n'apparaît pas avec un faux « 0 sur 0 »).
    if (!lignes) return null;
    const visibles = lignes.filter((l) => l.etat !== "sans_objet");
    if (visibles.length === 0) return null;
    const reste = visibles.filter((l) => l.etat === "a_faire" || l.etat === "bloquant");
    const faites = visibles.length - reste.length;
    const bloque = reste.some((l) => l.etat === "bloquant");
    const pct = Math.round((faites / visibles.length) * 100);
    return (
        <div data-section="mise-en-route">
            <h2 className="pb-3 text-sm font-semibold">{t(T.titre)}</h2>
            <Link href={adresseOnglet(agent.id, "reglages")} className="block cursor-pointer rounded-xl border bg-card p-4 transition-colors hover:bg-muted/50">
                <div className="flex items-center gap-3">
                    <span className="flex size-8 items-center justify-center rounded-lg border">
                        <Rocket className="size-4" aria-hidden />
                    </span>
                    <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{agent.name}</p>
                        <p className="text-xs text-muted-foreground">
                            {bloque ? t(T.bloque) : reste.length > 0 ? t(T.reste) : t(T.pret)} · {t(T.ou)}
                        </p>
                    </div>
                    <span className="text-sm tabular-nums text-muted-foreground">
                        {faites} {t(T.sur)} {visibles.length}
                    </span>
                </div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={t(T.progression)}>
                    <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
                </div>
            </Link>
        </div>
    );
}
