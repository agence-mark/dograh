"use client";

/**
 * [.mark] Le cadre commun du studio (E1, E5) : barre latérale à gauche, barre du haut (fil d'Ariane, barre d'actions),
 * contenu. Le contenu garde le défilement du document (les écrans existants posent leur propre hauteur).
 *
 * - `miettes` : le fil d'Ariane ; sans lui, « Espace / Entrée du menu » est déduit de l'adresse.
 * - `actions` : la barre d'actions, à droite. `milieu` : ce qui se pose après le fil (les onglets d'un agent).
 * - `replie` : une page qui demande la barre repliée en icônes (l'éditeur d'agent) la replie sans changer le choix de
 *   la personne pour les autres pages.
 * - `sansEntete` : une page qui porte déjà sa propre barre (l'éditeur) ; la barre latérale reste.
 */
import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { SidebarInset, SidebarProvider, SidebarRail, SidebarTrigger } from "@/components/ui/sidebar";

import { type CompteurMenu, SidebarStudio } from "./sidebar-studio";
import { entreeActive, espaceDe, menuDe } from "./navigation-studio";

export type Miette = { libelle: string; href?: string };

// L'état de la barre (dépliée ou repliée) est un choix de la personne, gardé par son navigateur.
export const CLE_BARRE = "mark.barre";
const lireBarre = (): boolean => {
    try {
        return window.localStorage.getItem(CLE_BARRE) !== "replie";
    } catch {
        return true;
    }
};
const garderBarre = (ouverte: boolean) => {
    try {
        window.localStorage.setItem(CLE_BARRE, ouverte ? "ouvert" : "replie");
    } catch {
        // Navigateur sans stockage : le choix tient jusqu'au rechargement.
    }
};

export function ShellStudio({
    miettes,
    actions,
    milieu,
    replie = false,
    sansEntete = false,
    compteurs,
    children,
}: {
    miettes?: Miette[];
    actions?: React.ReactNode;
    milieu?: React.ReactNode;
    replie?: boolean;
    sansEntete?: boolean;
    compteurs?: Record<string, CompteurMenu>;
    children: React.ReactNode;
}) {
    const { t } = useLangue();
    const pathname = usePathname();
    const [choix, setChoix] = useState(true);
    const [forcee, setForcee] = useState<boolean | null>(replie ? false : null);

    useEffect(() => {
        setChoix(lireBarre());
    }, []);

    // Entrer dans une page qui replie la barre la replie ; en sortir rend le choix de la personne.
    useEffect(() => {
        setForcee(replie ? false : null);
    }, [replie]);

    const { espace, base, org } = espaceDe(pathname);
    const entree = entreeActive(menuDe(espace), pathname, base);
    const fil: Miette[] =
        miettes ??
        [
            { libelle: org ?? t({ en: "Lab .mark", fr: "Labo .mark" }), href: base },
            ...(entree ? [{ libelle: t(entree.titre) }] : []),
        ];

    return (
        <SidebarProvider
            open={forcee ?? choix}
            onOpenChange={(ouverte) => {
                if (forcee !== null) setForcee(ouverte);
                else {
                    setChoix(ouverte);
                    garderBarre(ouverte);
                }
            }}
            className="bg-sidebar"
        >
            <SidebarStudio compteurs={compteurs} />
            <SidebarInset className="min-w-0 flex-1">
                {!sansEntete && (
                    <header className="sticky top-0 z-40 flex h-14 shrink-0 items-center gap-2 border-b bg-background px-4 sm:px-6">
                        <SidebarTrigger className="-ml-1" />
                        <nav
                            aria-label={t({ en: "Breadcrumb", fr: "Fil d'Ariane" })}
                            className={`flex min-w-0 items-center gap-1.5 text-sm ${milieu ? "shrink" : "flex-1"}`}
                        >
                            {fil.map((m, i) => (
                                <span key={i} className="flex min-w-0 items-center gap-1.5">
                                    {i > 0 && <ChevronRight className="size-3.5 shrink-0 text-muted-foreground" />}
                                    {m.href && i < fil.length - 1 ? (
                                        <Link href={m.href} className="truncate text-muted-foreground hover:font-medium hover:text-foreground">
                                            {m.libelle}
                                        </Link>
                                    ) : (
                                        <span className="truncate font-medium">{m.libelle}</span>
                                    )}
                                </span>
                            ))}
                        </nav>
                        {milieu && <div className="flex min-w-0 flex-1 items-center self-stretch">{milieu}</div>}
                        <div data-barre-actions="" className="flex items-center gap-2">
                            {actions}
                        </div>
                    </header>
                )}
                <div className="app-surface flex-1">{children}</div>
            </SidebarInset>
            <SidebarRail />
        </SidebarProvider>
    );
}

export { TitrePage } from "./titre-page";
