"use client";

/**
 * [.mark] builder-agent-vocal (lot 4): the right-click menu of a node: « Ask the builder ». The node is quoted in the
 * panel's writing zone (`@name`) and the panel opens.
 */
import { Sparkles } from "lucide-react";
import { useEffect } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";

import { useBuilderEcran } from "./store";

const T = {
    demander: { en: "Ask the builder", fr: "Demander au builder" },
} satisfies Record<string, Texte>;

export interface MenuOuvert {
    x: number;
    y: number;
    id: string;
    nom: string;
}

export function MenuDuNoeud({ menu, onFermer }: { menu: MenuOuvert | null; onFermer: () => void }) {
    const { t } = useLangue();
    const ouvrir = useBuilderEcran((s) => s.ouvrir);
    const citer = useBuilderEcran((s) => s.citer);

    useEffect(() => {
        if (!menu) return;
        const fermer = () => onFermer();
        const touche = (e: KeyboardEvent) => {
            if (e.key === "Escape") onFermer();
        };
        window.addEventListener("click", fermer);
        window.addEventListener("keydown", touche);
        return () => {
            window.removeEventListener("click", fermer);
            window.removeEventListener("keydown", touche);
        };
    }, [menu, onFermer]);

    if (!menu) return null;
    return (
        <div
            role="menu"
            data-menu="noeud"
            className="fixed z-50 min-w-48 rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
            style={{ left: menu.x, top: menu.y }}
        >
            <button
                type="button"
                role="menuitem"
                className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent"
                onClick={() => {
                    ouvrir();
                    citer({ id: menu.id, nom: menu.nom });
                    onFermer();
                }}
            >
                <Sparkles className="h-4 w-4" aria-hidden />
                {t(T.demander)}
            </button>
        </div>
    );
}
