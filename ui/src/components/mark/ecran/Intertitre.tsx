"use client";

/**
 * [.mark] A group inside an open theme: a subtitle, never a menu (convention E1).
 */
import type { ReactNode } from "react";

import { type Texte, useLangue } from "../langue/langue";
import { Info } from "../studio/marques";
import { TitreTableau } from "../studio/tableau";
import { useFormeMaquette } from "./forme-maquette";

export const Intertitre = ({
    id,
    titre,
    description,
    action,
    children,
}: {
    id?: string;
    titre: Texte;
    description?: Texte;
    /** Forme de la maquette seulement : un geste à droite du titre (« Enregistrer »). */
    action?: ReactNode;
    children: ReactNode;
}) => {
    const { t } = useLangue();
    // [.mark] K4b : dans la forme de la maquette, un intertitre est le titre d'un tableau (titre + « ! », trait, lignes).
    const maquette = useFormeMaquette();
    if (maquette) {
        return (
            <section id={id} data-groupe={id}>
                <TitreTableau titre={t(titre)} info={description && <Info>{t(description)}</Info>} action={action} />
                <div className="mt-4 divide-y border-t">{children}</div>
            </section>
        );
    }
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
