"use client";

/**
 * [.mark] Les onglets de la fenêtre d'un nœud (E15). Tous les volets restent montés (celui qui n'est pas actif est
 * masqué par l'attribut `hidden`) : un bloc ne se remonte pas, ne recharge pas ses données et garde son brouillon en
 * changeant d'onglet. Une seule section = pas de ligne d'onglets. L'onglet choisi survit à un changement des sections
 * affichées tant qu'il existe encore, sinon on retombe sur le premier. K2b : la ligne d'onglets reste fixe sous l'en-tête, seul
 * le corps défile (maquette `modale-noeud.tsx`).
 */
import { type ReactNode, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";

import { type SectionNoeud, TITRES_DES_SECTIONS } from "./sections-noeud";

export function OngletsNoeud({
    entete,
    sections,
}: {
    entete?: ReactNode;
    sections: { id: SectionNoeud; contenu: ReactNode }[];
}) {
    const { t } = useLangue();
    const [choisie, setChoisie] = useState<SectionNoeud | null>(null);
    const actif = sections.find((s) => s.id === choisie) ?? sections[0];
    return (
        <div className="flex min-h-0 flex-1 flex-col" data-onglets-noeud>
            {entete}
            {sections.length > 1 && (
                <div role="tablist" className="flex shrink-0 gap-1 overflow-x-auto border-b px-6">
                    {sections.map((s) => (
                        <button
                            key={s.id}
                            type="button"
                            role="tab"
                            aria-selected={actif?.id === s.id}
                            data-section={s.id}
                            onClick={() => setChoisie(s.id)}
                            className={`-mb-px cursor-pointer whitespace-nowrap border-b-2 px-3 py-2 text-sm ${
                                actif?.id === s.id
                                    ? "border-primary font-medium"
                                    : "border-transparent text-muted-foreground hover:font-medium hover:text-foreground"
                            }`}
                        >
                            {t(TITRES_DES_SECTIONS[s.id])}
                        </button>
                    ))}
                </div>
            )}
            <div className="min-h-0 max-h-[60vh] overflow-y-auto px-6 py-5">
                {sections.map((s) => (
                    <div key={s.id} role="tabpanel" className="grid gap-5" data-volet={s.id} hidden={s.id !== actif?.id}>
                        {s.contenu}
                    </div>
                ))}
            </div>
        </div>
    );
}
