"use client";

/**
 * [.mark] Le cadre commun du studio (E1, E5) : barre latérale à gauche, barre du haut (fil d'Ariane, barre d'actions),
 * contenu. Même cadre que la maquette (K1) : un panneau arrondi et bordé dans la page, qui défile à l'intérieur.
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
import { createContext, useContext, useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { useLangue } from "@/components/mark/langue/langue";
import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";

import { entreeActive, espaceDe, menuDe } from "./navigation-studio";
import { useNomEspace } from "./nom-espace";
import { type CompteurMenu, SidebarStudio } from "./sidebar-studio";

export type Miette = { libelle: string; href?: string };

/**
 * K2 : la barre du haut d'une page d'agent est posée par la page, dans trois emplacements du cadre (le nom, ce qui suit
 * le nom, les actions). La page garde son état (version, essai, publication) et le cadre garde sa barre : un portail,
 * jamais une seconde barre.
 */
type Emplacements = {
    nom: HTMLElement | null;
    milieu: HTMLElement | null;
    actions: HTMLElement | null;
    declarer: (personnalisee: boolean) => void;
};
const EnteteContexte = createContext<Emplacements | null>(null);

/** Pose le contenu de la barre du haut du cadre : `nom` à la place du fil d'Ariane, `milieu` après lui, `actions` à droite. */
export function EnteteStudio({ nom, milieu, actions }: { nom?: React.ReactNode; milieu?: React.ReactNode; actions?: React.ReactNode }) {
    const ctx = useContext(EnteteContexte);
    const declarer = ctx?.declarer;
    useEffect(() => {
        declarer?.(true);
        return () => declarer?.(false);
    }, [declarer]);
    if (!ctx) return null;
    return (
        <>
            {nom && ctx.nom && createPortal(nom, ctx.nom)}
            {milieu && ctx.milieu && createPortal(milieu, ctx.milieu)}
            {actions && ctx.actions && createPortal(actions, ctx.actions)}
        </>
    );
}

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
    const [elNom, setElNom] = useState<HTMLElement | null>(null);
    const [elMilieu, setElMilieu] = useState<HTMLElement | null>(null);
    const [elActions, setElActions] = useState<HTMLElement | null>(null);
    const [personnalisee, setPersonnalisee] = useState(false);

    useEffect(() => {
        setChoix(lireBarre());
    }, []);

    // Entrer dans une page qui replie la barre la replie ; en sortir rend le choix de la personne.
    useEffect(() => {
        setForcee(replie ? false : null);
    }, [replie]);

    const { espace, base, org } = espaceDe(pathname);
    const nomEspace = useNomEspace(espace, org);
    const entree = entreeActive(menuDe(espace), pathname, base);
    const fil: Miette[] =
        miettes ??
        [
            { libelle: nomEspace ?? (org ? "" : "Labo"), href: base },
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
            <EnteteContexte.Provider value={{ nom: elNom, milieu: elMilieu, actions: elActions, declarer: setPersonnalisee }}>
            <SidebarStudio compteurs={compteurs} />
            <div className="h-svh w-full overflow-hidden lg:py-2 lg:pr-2">
                <div className="relative flex h-full w-full overflow-hidden bg-background lg:rounded-xl lg:border">
                    <div className="flex min-w-0 flex-1 flex-col">
                        {!sansEntete && (
                            <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4 sm:px-6">
                                <SidebarTrigger className="-ml-1" />
                                <div ref={setElNom} className="contents" />
                                <nav
                                    aria-label={t({ en: "Breadcrumb", fr: "Fil d'Ariane" })}
                                    hidden={personnalisee}
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
                                <div className={`min-w-0 items-center self-stretch ${milieu || personnalisee ? "flex flex-1" : "hidden"}`}>
                                    {milieu}
                                    <div ref={setElMilieu} className="contents" />
                                </div>
                                <div data-barre-actions="" className="flex items-center gap-2">
                                    {actions}
                                    <div ref={setElActions} className="contents" />
                                </div>
                            </header>
                        )}
                        <main className="flex-1 overflow-auto">{children}</main>
                    </div>
                </div>
            </div>
            </EnteteContexte.Provider>
        </SidebarProvider>
    );
}

/** Le contenu d'une page de la maquette : colonne de 6xl, marges et espacement des blocs (`ShellStudio` de la maquette). */
export function PageStudio({ children }: { children: React.ReactNode }) {
    return <div className="mx-auto w-full max-w-6xl space-y-10 px-4 py-8 sm:px-8">{children}</div>;
}

export { TitrePage } from "./titre-page";
