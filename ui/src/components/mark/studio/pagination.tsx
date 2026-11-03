"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";

/**
 * Pagination (E61) : toute liste qui peut grandir charge une page à la fois, côté serveur (`limit` / `offset`),
 * 25 lignes par page. La barre n'apparaît qu'au-delà d'une page. Un filtre ou une recherche ramène à la page 1
 * (l'appelant remet `page` à 0).
 *
 * Deux usages :
 *  - serveur : `total`, `page` (à partir de 0) et `changerPage` ; `children` reçoit `{ limit, offset }` ;
 *  - local (petites listes déjà en mémoire) : `liste` ; `children` reçoit la tranche de la page.
 */
export const PAR_PAGE = 25;

type Commun = { parPage?: number };
type Serveur = Commun & {
    total: number;
    page: number;
    changerPage: (page: number) => void;
    liste?: undefined;
    children?: React.ReactNode;
};
type Local<T> = Commun & {
    liste: T[];
    children: (page: T[]) => React.ReactNode;
    total?: undefined;
};

export function BarrePagination({
    total,
    page,
    parPage = PAR_PAGE,
    changerPage,
}: {
    total: number;
    page: number;
    parPage?: number;
    changerPage: (page: number) => void;
}) {
    const { t } = useLangue();
    if (total <= parPage) return null;
    const pages = Math.max(1, Math.ceil(total / parPage));
    const p = Math.min(Math.max(page, 0), pages - 1);
    const debut = p * parPage;
    return (
        <div className="flex items-center justify-end gap-3 pt-3 text-sm text-muted-foreground">
            <span className="tabular-nums">
                {debut + 1}–{Math.min(debut + parPage, total)} {t({ en: "of", fr: "sur" })} {total}
            </span>
            <span className="inline-flex gap-1">
                <Button
                    variant="outline"
                    size="icon"
                    className="size-8"
                    disabled={p === 0}
                    onClick={() => changerPage(p - 1)}
                    aria-label={t({ en: "Previous page", fr: "Page précédente" })}
                >
                    <ChevronLeft className="size-4" />
                </Button>
                <Button
                    variant="outline"
                    size="icon"
                    className="size-8"
                    disabled={p >= pages - 1}
                    onClick={() => changerPage(p + 1)}
                    aria-label={t({ en: "Next page", fr: "Page suivante" })}
                >
                    <ChevronRight className="size-4" />
                </Button>
            </span>
        </div>
    );
}

/** Le `limit` / `offset` d'une page, pour l'appel au serveur. */
export const fenetrePage = (page: number, parPage = PAR_PAGE) => ({ limit: parPage, offset: page * parPage });

export function Paginee<T>(props: Serveur | Local<T>) {
    const [pageLocale, setPageLocale] = useState(0);
    const parPage = props.parPage ?? PAR_PAGE;
    if (props.liste) {
        const pages = Math.max(1, Math.ceil(props.liste.length / parPage));
        const p = Math.min(pageLocale, pages - 1);
        return (
            <>
                {props.children(props.liste.slice(p * parPage, p * parPage + parPage))}
                <BarrePagination total={props.liste.length} page={p} parPage={parPage} changerPage={setPageLocale} />
            </>
        );
    }
    return (
        <>
            {props.children}
            <BarrePagination total={props.total ?? 0} page={props.page ?? 0} parPage={parPage} changerPage={props.changerPage} />
        </>
    );
}
