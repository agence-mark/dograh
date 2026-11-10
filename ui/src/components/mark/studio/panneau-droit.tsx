"use client";

/**
 * [.mark] Partie 3, sous-lot 19 : le panneau de droite de tout l'écran du fork (règle d'Evan, 04/11 ; maquette
 * `components/studio/panneau-onglets.tsx`). Modifier un objet = un onglet de ce panneau unique, fixé à droite sous la
 * barre du haut, qui POUSSE la page (ou passe par-dessus sans voile quand la page n'aurait plus sa largeur utile).
 *
 * - ouvert à 480 px, largeur selon le contenu (chaque fenêtre annonce la sienne, élargissement si un tableau déborde),
 *   70 % de l'écran au plus, redimensionnable par son bord gauche (souris et flèches du clavier) ;
 * - un objet s'ouvre en APERÇU (titre en italique) : le clic suivant le remplace, le double-clic l'épingle ;
 * - toute rangée d'onglets passe par `Defileur` (flèches), et le menu « ⋯ » liste tous les onglets ;
 * - Échap remonte d'un niveau s'il y a un détail empilé, sinon ferme l'onglet actif (avec la garde de la fenêtre).
 *
 * Les fenêtres elles-mêmes sont les `Dialog` de `components/ui/dialog.tsx` : hors de ce cadre, ou marquées `centree`,
 * elles restent centrées. Rien ici ne les connaît : elles s'inscrivent (`inscrire`) en s'ouvrant et se retirent en se fermant.
 */
import { MoreHorizontal, Pin, X } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

import { Defileur } from "./defileur";

export const LARGEUR_DEFAUT = 480;
/** La page ne doit jamais passer sous cette largeur utile : le menu se replie d'abord, puis le panneau passe par-dessus. */
export const LARGEUR_UTILE_MIN = 640;
const PART_MAX = 0.7;

export type OngletPanneau = {
    id: string;
    titre: string;
    /** Aperçu : le prochain objet ouvert le remplace. Le double-clic ou le clic sur la punaise l'épingle. */
    apercu: boolean;
    /** Ferme la fenêtre comme sa propre croix (donc avec sa garde de saisie non enregistrée). */
    fermer: () => void;
    /** Largeur (px) que la fenêtre annonce. */
    largeur?: number;
};
export type DetailEmpile = { id: string; racine: string; fermer: () => void };

export function useEtatPanneau() {
    const [onglets, setOnglets] = useState<OngletPanneau[]>([]);
    const [details, setDetails] = useState<DetailEmpile[]>([]);
    const [actifBrut, setActif] = useState<string | null>(null);
    const [corps, setCorps] = useState<HTMLElement | null>(null);
    const [choisie, setChoisie] = useState<number | null>(null);
    const [besoin, setBesoin] = useState(0);
    const ref = useRef(onglets);
    ref.current = onglets;
    const refDetails = useRef(details);
    refDetails.current = details;

    const courant = onglets.find((o) => o.id === actifBrut) ?? onglets[0];
    const actif = courant?.id ?? null;
    const refActif = useRef(actif);
    refActif.current = actif;

    const inscrire = useCallback((o: OngletPanneau) => {
        // Un nouvel aperçu remplace l'ancien : on le ferme par sa propre porte, la fenêtre se retire d'elle-même.
        if (o.apercu) ref.current.filter((x) => x.apercu && x.id !== o.id).forEach((x) => setTimeout(x.fermer, 0));
        setOnglets((l) => (l.some((x) => x.id === o.id) ? l.map((x) => (x.id === o.id ? o : x)) : [...l, o]));
        setActif(o.id);
    }, []);
    const retirer = useCallback((id: string) => {
        const liste = ref.current;
        const i = liste.findIndex((x) => x.id === id);
        if (i < 0) return;
        const reste = liste.filter((x) => x.id !== id);
        setOnglets(reste);
        setActif((a) => (a === id ? (reste[Math.max(0, i - 1)]?.id ?? null) : a));
    }, []);
    const majTitre = useCallback(
        (id: string, titre: string) => setOnglets((l) => (l.some((x) => x.id === id && x.titre !== titre) ? l.map((x) => (x.id === id ? { ...x, titre } : x)) : l)),
        [],
    );
    const epingler = useCallback(
        (id: string) => setOnglets((l) => (l.some((x) => x.id === id && x.apercu) ? l.map((x) => (x.id === id ? { ...x, apercu: false } : x)) : l)),
        [],
    );
    const inscrireDetail = useCallback((d: DetailEmpile) => setDetails((l) => [...l.filter((x) => x.id !== d.id), d]), []);
    const retirerDetail = useCallback((id: string) => setDetails((l) => (l.some((x) => x.id === id) ? l.filter((x) => x.id !== id) : l)), []);
    const toutFermer = useCallback(() => ref.current.forEach((x) => x.fermer()), []);
    /** Échap : le détail du dessus remonte d'un niveau ; sinon l'onglet actif se ferme. */
    const echap = useCallback(() => {
        const a = refActif.current;
        const haut = [...refDetails.current].reverse().find((d) => d.racine === a);
        if (haut) return haut.fermer();
        (ref.current.find((x) => x.id === a) ?? ref.current[0])?.fermer();
    }, []);

    const voulu = Math.max(courant?.largeur ?? LARGEUR_DEFAUT, besoin, LARGEUR_DEFAUT);
    const largeur = Math.max(voulu, choisie ?? 0);
    return {
        onglets, details, actif, setActif, corps, poserCorps: setCorps,
        inscrire, retirer, majTitre, epingler, inscrireDetail, retirerDetail, toutFermer, echap,
        voulu, largeur, setChoisie, setBesoin,
    };
}
export type EtatPanneau = ReturnType<typeof useEtatPanneau>;

export const ContextePanneau = createContext<EtatPanneau | null>(null);
/**
 * La place (px) que le panneau prend à droite du cadre quand il POUSSE la page ; 0 s'il est fermé ou par-dessus. Les panneaux
 * flottants de l'éditeur (builder, essai) s'y décalent au lieu de recouvrir le panneau.
 */
export const DecalagePanneau = createContext(0);
export const useDecalagePanneau = () => useContext(DecalagePanneau);
export const usePanneau = () => useContext(ContextePanneau);

/**
 * Largeur annoncée par une fenêtre : sa classe `sm:max-w-*` lue comme un besoin de place, ramenée à ce que le panneau offre
 * (une fenêtre centrée de 896 px n'a pas besoin de 896 px dans un panneau : 640 suffisent, la page garde sa place).
 */
const LARGEURS: Record<string, number> = { sm: 480, md: 480, lg: 480, xl: 480, "2xl": 520, "3xl": 600, "4xl": 640, "5xl": 720, "6xl": 800 };
export function largeurAnnoncee(classes?: string): number | undefined {
    const m = /(?:^|\s)(?:sm:|md:|lg:)?max-w-(sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl)(?:\s|$)/.exec(classes ?? "");
    return m ? LARGEURS[m[1]] : undefined;
}

/** La place que prend la barre latérale (dépliée, repliée en icônes) : pour savoir si la page garde sa largeur utile. */
const MENU_DEPLIE = 256;
const MENU_REPLIE = 48;
export type Adaptation = { replierMenu: boolean; dessus: boolean; largeurAffichee: number };
/**
 * Règle du panneau responsive (Evan, 05 § 7) : largeur utile minimale par page ; si elle manque, le menu se replie d'abord ;
 * si elle manque encore, le panneau passe PAR-DESSUS la page, sans voile. Jamais sous 480 px, jamais plus de 70 %.
 */
export function adapter(largeurEcran: number, largeur: number, menuDeplie: boolean): Adaptation {
    const largeurAffichee = Math.max(LARGEUR_DEFAUT, Math.min(largeur, Math.round(largeurEcran * PART_MAX)));
    const utile = (menu: number) => largeurEcran - menu - largeurAffichee - 16;
    if (utile(menuDeplie ? MENU_DEPLIE : MENU_REPLIE) >= LARGEUR_UTILE_MIN) return { replierMenu: false, dessus: false, largeurAffichee };
    if (utile(MENU_REPLIE) >= LARGEUR_UTILE_MIN) return { replierMenu: true, dessus: false, largeurAffichee };
    return { replierMenu: true, dessus: true, largeurAffichee };
}

export function PanneauDroit({ etat, dessus, largeurAffichee }: { etat: EtatPanneau; dessus: boolean; largeurAffichee: number }) {
    const { t } = useLangue();
    const { onglets, actif, setActif, epingler, toutFermer, poserCorps, voulu, largeur, setChoisie, setBesoin } = etat;
    const zone = useRef<HTMLDivElement | null>(null);
    const ouvert = onglets.length > 0;

    // Élargissement si un tableau ou un bloc déborde de l'onglet actif (jamais plus de 70 % de l'écran).
    useEffect(() => {
        const el = zone.current;
        if (!el || !ouvert || typeof ResizeObserver === "undefined") return;
        const mesurer = () => {
            let max = 0;
            el.querySelectorAll<HTMLElement>("table, pre, [data-largeur-min]").forEach((x) => {
                const parent = x.parentElement;
                if (parent && x.scrollWidth > parent.clientWidth + 2) max = Math.max(max, x.scrollWidth - parent.clientWidth);
            });
            setBesoin(max ? Math.min(Math.round(window.innerWidth * PART_MAX), el.clientWidth + max + 8) : 0);
        };
        mesurer();
        const ro = new ResizeObserver(mesurer);
        ro.observe(el);
        return () => ro.disconnect();
    }, [actif, ouvert, setBesoin]);

    const bornes = (l: number) => Math.min(Math.round(window.innerWidth * PART_MAX), Math.max(voulu, l));
    const tirer = (e: React.MouseEvent) => {
        e.preventDefault();
        const x0 = e.clientX;
        const l0 = largeur;
        const bouger = (m: MouseEvent) => setChoisie(bornes(l0 + (x0 - m.clientX)));
        const lacher = () => {
            window.removeEventListener("mousemove", bouger);
            window.removeEventListener("mouseup", lacher);
            document.body.style.cursor = "";
        };
        document.body.style.cursor = "col-resize";
        window.addEventListener("mousemove", bouger);
        window.addEventListener("mouseup", lacher);
    };

    const libelle = (o: OngletPanneau) => o.titre || t({ en: "Window", fr: "Fenêtre" });
    return (
        <aside
            data-panneau-droit=""
            data-dessus={dessus ? "" : undefined}
            aria-label={t({ en: "Side panel", fr: "Panneau de droite" })}
            hidden={!ouvert}
            style={{ width: `min(${largeurAffichee}px, 70vw)` }}
            className={`min-h-0 shrink-0 flex-col rounded-xl border border-border/60 bg-card shadow-md ${
                dessus ? "absolute top-2 right-2 bottom-2 z-30 shadow-2xl" : "relative my-2 mr-2"
            } ${ouvert ? "flex" : "hidden"}`}
        >
            <div
                role="separator"
                tabIndex={0}
                aria-orientation="vertical"
                aria-label={t({ en: "Panel width", fr: "Largeur du panneau" })}
                aria-valuenow={largeur}
                onMouseDown={tirer}
                onKeyDown={(e) => {
                    if (e.key.endsWith("Left")) setChoisie(bornes(largeur + 24));
                    else if (e.key.endsWith("Right")) setChoisie(bornes(largeur - 24));
                    else return;
                    e.preventDefault();
                }}
                className="group absolute top-0 bottom-0 -left-2 z-10 flex w-3 cursor-col-resize items-center justify-center focus-visible:outline-none"
            >
                <span className="h-10 w-1 rounded-full bg-foreground/10 opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" />
            </div>
            <div className="flex shrink-0 items-center gap-1 px-2 pt-2 pb-1">
                <Defileur className="flex-1" interieur="gap-1 py-0.5">
                    {onglets.map((o) => (
                        <div
                            key={o.id}
                            role="tab"
                            aria-selected={o.id === actif}
                            tabIndex={0}
                            onClick={() => setActif(o.id)}
                            onDoubleClick={() => epingler(o.id)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter") setActif(o.id);
                            }}
                            title={o.apercu ? t({ en: "Preview: double-click to pin", fr: "Aperçu : double-clic pour épingler" }) : libelle(o)}
                            data-testid="onglet-du-panneau"
                            className={`group flex h-8 shrink-0 cursor-pointer items-center gap-1.5 rounded-lg pr-1 pl-2.5 text-sm transition-colors select-none ${
                                o.id === actif ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:font-medium hover:text-foreground"
                            }`}
                        >
                            <span className={`max-w-56 truncate ${o.apercu ? "italic" : ""}`}>{libelle(o)}</span>
                            <button
                                type="button"
                                aria-label={t({ en: "Close tab", fr: "Fermer l'onglet" })}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    o.fermer();
                                }}
                                className={`cursor-pointer rounded-md p-0.5 hover:bg-foreground/5 ${o.id === actif ? "opacity-70" : "opacity-0 group-hover:opacity-70 focus-visible:opacity-70"}`}
                            >
                                <X className="size-3.5" />
                            </button>
                        </div>
                    ))}
                </Defileur>
                <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="size-8 shrink-0" aria-label={t({ en: "All open tabs", fr: "Tous les onglets ouverts" })}>
                            <MoreHorizontal className="size-4" />
                        </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-64">
                        <DropdownMenuLabel className="text-xs text-muted-foreground">
                            {t({ en: "Open", fr: "Ouverts" })} ({onglets.length})
                        </DropdownMenuLabel>
                        {onglets.map((o) => (
                            <DropdownMenuItem key={o.id} onClick={() => setActif(o.id)} className="cursor-pointer gap-2">
                                <span className={`truncate ${o.apercu ? "italic" : ""}`}>{libelle(o)}</span>
                                {!o.apercu && <Pin className="ml-auto size-3 text-muted-foreground" />}
                            </DropdownMenuItem>
                        ))}
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="cursor-pointer" onClick={toutFermer}>
                            {t({ en: "Close all", fr: "Tout fermer" })}
                        </DropdownMenuItem>
                    </DropdownMenuContent>
                </DropdownMenu>
            </div>
            <div
                ref={(el) => {
                    zone.current = el;
                    poserCorps(el);
                }}
                data-corps-panneau=""
                className="relative min-h-0 flex-1 overflow-hidden rounded-b-xl"
            />
        </aside>
    );
}

/** Ce que le cadre tire de l'état : replier le menu, passer par-dessus, la largeur à afficher. */
export function useAdaptationPanneau(etat: EtatPanneau, menuDeplie: boolean): Adaptation {
    const [ecran, setEcran] = useState(typeof window === "undefined" ? 1920 : window.innerWidth);
    useEffect(() => {
        const maj = () => setEcran(window.innerWidth);
        window.addEventListener("resize", maj);
        return () => window.removeEventListener("resize", maj);
    }, []);
    const ouvert = etat.onglets.length > 0;
    return useMemo(
        () => (ouvert ? adapter(ecran, etat.largeur, menuDeplie) : { replierMenu: false, dessus: false, largeurAffichee: LARGEUR_DEFAUT }),
        [ouvert, ecran, etat.largeur, menuDeplie],
    );
}
