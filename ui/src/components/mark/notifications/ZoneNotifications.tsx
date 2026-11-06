"use client";

/**
 * [.mark] La zone des notifications passagères, montée une fois dans `app/layout.tsx` (portée de la maquette
 * `/labo/design/notifications`). En bas à droite, pastille pleine foncée (jamais d'orange), un bouton facultatif,
 * une croix. `aria-live="polite"` pour la zone, `role="alert"` (annonce immédiate) pour l'échec. La minuterie
 * s'arrête au survol et au focus ; Échap ferme la notification qui a le focus.
 */
import { Check, Info as IconeInfo, Loader2, TriangleAlert, X } from "lucide-react";
import { useState, useSyncExternalStore } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { compteDeLEquipe } from "@/lib/espaceCourant";

import { abonner, fermer, lireNotifications, type Notification, reprendre, type SorteNotif, suspendre, VISIBLES_AU_PLUS } from "./magasin";

const COULEURS: Record<SorteNotif, string> = {
    succes: "bg-(--notif-succes)",
    echec: "bg-(--notif-echec)",
    avertissement: "bg-(--notif-avertissement)",
    information: "bg-(--notif-information)",
    encours: "bg-(--notif-encours)",
};

const ICONES = { succes: Check, echec: X, avertissement: TriangleAlert, information: IconeInfo, encours: Loader2 } as const;

const T: Record<string, Texte> = {
    fermer: { en: "Close", fr: "Fermer" },
    details: { en: "Details", fr: "Détails" },
    masquer: { en: "Hide details", fr: "Masquer les détails" },
    zone: { en: "Notifications", fr: "Notifications" },
};

function Pastille({ sorte }: { sorte: SorteNotif }) {
    const Icone = ICONES[sorte];
    return (
        <span aria-hidden className={`mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full text-white ${COULEURS[sorte]}`}>
            <Icone className={`size-3 ${sorte === "encours" ? "animate-spin" : ""}`} strokeWidth={3} />
        </span>
    );
}

export function CarteNotification({ n, equipe }: { n: Notification; equipe: boolean }) {
    const { t } = useLangue();
    const [ouvert, setOuvert] = useState(false);
    const aDetail = equipe && Boolean(n.detail);
    return (
        <div
            role={n.sorte === "echec" ? "alert" : "status"}
            data-sorte={n.sorte}
            onMouseEnter={() => suspendre(n.cle)}
            onMouseLeave={() => reprendre(n.cle)}
            onFocus={() => suspendre(n.cle)}
            onBlur={() => reprendre(n.cle)}
            onKeyDown={(e) => {
                if (e.key === "Escape") fermer(n.cle);
            }}
            className="pointer-events-auto w-[356px] max-w-full rounded-xl border bg-popover px-3.5 py-3 text-sm text-popover-foreground shadow-lg animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
            <div className="flex items-start gap-3">
                <Pastille sorte={n.sorte} />
                <p className="flex-1 leading-snug">{t(n.texte)}</p>
                {n.bouton && (
                    <button
                        type="button"
                        onClick={() => {
                            fermer(n.cle);
                            n.bouton?.action();
                        }}
                        className="shrink-0 cursor-pointer text-sm font-semibold text-(--cta) hover:font-bold"
                    >
                        {t(n.bouton.libelle)}
                    </button>
                )}
                <button type="button" aria-label={t(T.fermer)} onClick={() => fermer(n.cle)} className="-mr-1 mt-0.5 shrink-0 cursor-pointer text-muted-foreground hover:text-foreground">
                    <X className="size-4" />
                </button>
            </div>
            {aDetail && (
                <div className="mt-1.5 pl-8">
                    <button type="button" aria-expanded={ouvert} onClick={() => setOuvert(!ouvert)} className="cursor-pointer text-xs text-muted-foreground hover:font-semibold">
                        {t(ouvert ? T.masquer : T.details)}
                    </button>
                    {ouvert && <p className="mt-1 break-words font-mono text-xs text-muted-foreground">{n.detail}</p>}
                </div>
            )}
        </div>
    );
}

export function ZoneNotifications() {
    const { t } = useLangue();
    const liste = useSyncExternalStore(abonner, lireNotifications, lireNotifications);
    const visibles = liste.slice(-VISIBLES_AU_PLUS);
    const equipe = compteDeLEquipe();
    return (
        <div
            aria-live="polite"
            aria-label={t(T.zone)}
            className="pointer-events-none fixed right-5 bottom-5 z-[100] flex flex-col items-end gap-2"
        >
            {visibles.map((n) => (
                <CarteNotification key={n.cle} n={n} equipe={equipe} />
            ))}
        </div>
    );
}
