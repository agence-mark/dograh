"use client";

/**
 * [.mark] Partie 3, N4 (décision 19, maquette `SuiviBuilder`) : « Reprendre », les trois derniers chats en cartes simples sous la saisie
 * de l'accueil du builder. Le titre, puis l'agent, « quand », la marque Claude Code et la pastille des changements à valider.
 * Une seule lecture (les noms d'agents viennent de l'accueil, qui les a déjà lus) ; chargement, erreur et « aucun chat » par `EtatVide`.
 */
import Link from "next/link";
import { MessageSquare } from "lucide-react";
import { useEffect, useState } from "react";

import { listerLesFilsApiV1BuilderFilsGet, type VueFil } from "@/client";
import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { MarqueClaudeCode } from "@/components/mark/sources/marques";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Pastille } from "@/components/mark/studio/marques";
import { useAuth } from "@/lib/auth";

import { useAdressesDuBuilder } from "./adresses";
import { quand } from "./ListeDesFils";

const T = {
    titre: { en: "Resume", fr: "Reprendre" },
    toutVoir: { en: "See all", fr: "Tout voir" },
    vide: { en: "No chat", fr: "Aucun chat" },
} satisfies Record<string, Texte>;

export function ReprendreLesChats({ agents }: { agents: Record<number, string> }) {
    const { t, langue } = useLangue();
    const { user, loading } = useAuth();
    const adresses = useAdressesDuBuilder();
    const [fils, setFils] = useState<VueFil[] | null>(null);
    const [erreur, setErreur] = useState(false);

    const lire = () => {
        setErreur(false);
        void listerLesFilsApiV1BuilderFilsGet().then((r) => {
            if (r.error || !r.data) setErreur(true);
            else setFils(r.data.slice(0, 3));
        });
    };
    useEffect(() => {
        if (loading || !user) return;
        lire();
    }, [loading, user]);

    return (
        <div data-section="reprendre">
            <div className="flex items-center justify-between pb-3">
                <h2 className="text-sm font-semibold">{t(T.titre)}</h2>
                <Link href={adresses.liste} className="cursor-pointer text-sm text-(--link) hover:font-semibold">
                    {t(T.toutVoir)}
                </Link>
            </div>
            {erreur ? (
                <EtatVide cas="erreur" reessayer={lire} compact />
            ) : fils === null ? (
                <EtatVide cas="chargement" lignes={2} />
            ) : fils.length === 0 ? (
                <EtatVide cas="premier" icone={MessageSquare} titre={t(T.vide)} compact />
            ) : (
                <div className="grid gap-3 sm:grid-cols-3">
                    {fils.map((f) => (
                        <Link
                            key={f.id}
                            href={adresses.fil(f.id)}
                            data-reprendre={f.id}
                            className="flex cursor-pointer flex-col gap-2 rounded-xl border bg-card p-4 transition-colors hover:bg-muted/50"
                        >
                            <p className="line-clamp-2 text-sm font-medium">{f.titre}</p>
                            <p className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                                {f.workflow_id && agents[f.workflow_id] && <span className="truncate">{agents[f.workflow_id]}</span>}
                                <span>{quand(f.modifie_le, langue)}</span>
                                {f.genre === "claude_code" && <MarqueClaudeCode par={f.auteur} />}
                                {f.changements > 0 && <Pastille n={f.changements} urgent />}
                            </p>
                        </Link>
                    ))}
                </div>
            )}
        </div>
    );
}
