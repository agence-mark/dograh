"use client";

/**
 * [.mark] U8 (G1b) : la section « À améliorer » de l'accueil du builder (maquette `SuiviBuilder`), sous la saisie, avant le Chat.
 * Les trois problèmes « à trier » les plus graves, lus sur `GET /ameliorations` (la même route que la page, organisation de la
 * personne : dans l'espace d'un client, seulement ce client). Une ligne : gravité · titre · agent, fréquence, cause probable.
 * « Tout voir » ouvre la page. Chargement, erreur, rien à améliorer : `EtatVide`, jamais un écran blanc.
 */
import { Inbox } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { lireLesAmeliorationsApiV1AmeliorationsGet } from "@/client";
import type { PageDAmeliorations } from "@/client/types.gen";
import { useLangue } from "@/components/mark/langue/langue";
import { EtatVide } from "@/components/mark/studio/etat-vide";
import { Gravite } from "@/components/mark/studio/marques";
import { useAuth } from "@/lib/auth";

import { CAUSES, texteDeFrequence, titreLisible } from "./libelles";

const T = {
    titre: { en: "To improve", fr: "À améliorer" },
    toutVoir: { en: "See all", fr: "Tout voir" },
    rien: { en: "Nothing to improve", fr: "Rien à améliorer" },
};

type Charge = { etat: "chargement" } | { etat: "erreur" } | { etat: "acces" } | { etat: "pret"; lignes: PageDAmeliorations["lignes"] };

export function SectionAAmeliorer({ lien }: { lien: string }) {
    const { t } = useLangue();
    const { user, loading } = useAuth();
    const [charge, setCharge] = useState<Charge>({ etat: "chargement" });

    const lire = useCallback(async () => {
        setCharge({ etat: "chargement" });
        const r = await lireLesAmeliorationsApiV1AmeliorationsGet({ query: { etat: "a_trier" } });
        setCharge(r.error ? { etat: r.response?.status === 403 ? "acces" : "erreur" } : !r.data ? { etat: "erreur" } : { etat: "pret", lignes: r.data.lignes.slice(0, 3) });
    }, []);

    useEffect(() => {
        if (loading || !user) return;
        void lire();
    }, [loading, user, lire]);

    return (
        <section>
            <div className="flex items-center gap-2 pb-3">
                <Inbox className="size-4 text-muted-foreground" aria-hidden />
                <h2 className="text-base font-semibold">{t(T.titre)}</h2>
                <Link href={lien} className="ml-auto text-sm text-(--acc) hover:font-semibold">
                    {t(T.toutVoir)}
                </Link>
            </div>
            {charge.etat === "chargement" ? (
                <EtatVide cas="chargement" lignes={3} />
            ) : charge.etat === "acces" ? (
                <EtatVide cas="acces" compact />
            ) : charge.etat === "erreur" ? (
                <EtatVide cas="erreur" reessayer={() => void lire()} compact />
            ) : charge.lignes.length === 0 ? (
                <EtatVide cas="fait" titre={t(T.rien)} compact />
            ) : (
                <ul className="divide-y">
                    {charge.lignes.map((p) => {
                        const titre = titreLisible(p);
                        return (
                            <li key={p.id}>
                                <Link href={lien} className="flex cursor-pointer items-center gap-4 px-1 py-3.5 hover:bg-muted/40 hover:font-semibold">
                                    <span className="w-20 shrink-0">
                                        <Gravite n={p.gravite as 1 | 2 | 3} />
                                    </span>
                                    <span className="min-w-0 flex-1">
                                        <span className="block truncate text-sm font-medium">{typeof titre === "string" ? titre : t(titre)}</span>
                                        <span className="block text-xs font-normal text-muted-foreground">
                                            {[p.workflow_nom, texteDeFrequence(p, t), p.cause && CAUSES[p.cause] ? t(CAUSES[p.cause]) : ""].filter(Boolean).join(" · ")}
                                        </span>
                                    </span>
                                </Link>
                            </li>
                        );
                    })}
                </ul>
            )}
        </section>
    );
}
