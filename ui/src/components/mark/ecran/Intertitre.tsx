"use client";

/**
 * [.mark] A group inside an open theme: a subtitle, never a menu (convention E1).
 */
import type { ReactNode } from "react";

import { type Texte, useLangue } from "../langue/langue";

export const Intertitre = ({
    id,
    titre,
    description,
    children,
}: {
    id?: string;
    titre: Texte;
    description?: Texte;
    children: ReactNode;
}) => {
    const { t } = useLangue();
    return (
        <div id={id} data-groupe={id} className="space-y-4 border-t pt-5 first:border-t-0 first:pt-0">
            <div>
                <h3 className="text-sm font-semibold">{t(titre)}</h3>
                {description && <p className="mt-0.5 text-xs text-muted-foreground">{t(description)}</p>}
            </div>
            {children}
        </div>
    );
};
