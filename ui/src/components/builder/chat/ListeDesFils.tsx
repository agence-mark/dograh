"use client";

/** [.mark] builder partie 2, U5 : l'historique des conversations du builder (état, coût, « N changements à valider »). Liste nue, jamais dans un cadre. */
import { MessageSquare } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { listerLesFilsApiV1BuilderFilsGet, type VueFil } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { EnDirect, MarqueClaudeCode } from "@/components/mark/sources/marques";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { useAuth } from "@/lib/auth";

import { useAdressesDuBuilder } from "./adresses";

const T = {
    vide: { en: "No conversation yet", fr: "Aucune conversation" },
    changements: { en: "change(s) to validate", fr: "changement(s) à valider" },
    en_cours: { en: "Working", fr: "En cours" },
    terminee: { en: "Done", fr: "Terminée" },
    arretee: { en: "Stopped", fr: "Arrêtée" },
    erreur: { en: "Error", fr: "Erreur" },
    nouvelle: { en: "New", fr: "Nouvelle" },
} satisfies Record<string, Texte>;

export function ListeDesFils({ limite, workflowId }: { limite?: number; workflowId?: number }) {
    const { t } = useLangue();
    const { user, loading: authLoading } = useAuth();
    const adresses = useAdressesDuBuilder();
    const [fils, setFils] = useState<VueFil[] | null>(null);
    const [erreur, setErreur] = useState(false);

    useEffect(() => {
        if (authLoading || !user) return;
        void listerLesFilsApiV1BuilderFilsGet({ query: workflowId ? { workflow_id: workflowId } : undefined }).then((r) => {
            if (r.error || !r.data) setErreur(true);
            else setFils(r.data);
        });
    }, [authLoading, user, workflowId]);

    if (erreur) return <EtatVide cas="erreur" reessayer={() => window.location.reload()} />;
    if (fils === null) return <EtatVide cas="chargement" lignes={3} />;
    if (fils.length === 0) return <EtatVide cas="premier" icone={MessageSquare} titre={t(T.vide)} />;
    return (
        <ul className="divide-y">
            {fils.slice(0, limite).map((f) => (
                <li key={f.id}>
                    <Link href={adresses.fil(f.id)} className="flex cursor-pointer items-center justify-between gap-3 py-2 hover:font-semibold">
                        <span className="flex min-w-0 flex-col">
                            <span className="truncate text-sm">{f.titre}</span>
                            {f.genre === "claude_code" && (
                                <span className="flex items-center gap-2">
                                    <MarqueClaudeCode par={f.auteur} />
                                    {f.etat === "en_cours" && <EnDirect />}
                                </span>
                            )}
                        </span>
                        <span className="shrink-0 text-xs text-muted-foreground">
                            {f.changements > 0 ? `${f.changements} ${t(T.changements)} · ` : ""}
                            {t(T[f.etat as keyof typeof T] ?? T.nouvelle)} · ${f.cout.toFixed(2)}
                        </span>
                    </Link>
                </li>
            ))}
        </ul>
    );
}
