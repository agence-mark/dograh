"use client";

/**
 * [.mark] V5 : l'aperçu cliquable de l'éditeur du widget (maquette `editeur-widget.tsx`).
 *
 * Ce n'est PAS une image ni une copie du rendu : c'est le vrai widget du fork (`/embed/dograh-widget.js`,
 * `window.MarkWidget.apercu`) monté dans un faux site, étape par étape, à la taille d'un ordinateur ou d'un téléphone
 * puis réduit pour tenir. Il n'ouvre aucune conversation, ne fait aucune requête, ne contacte aucun domaine : le script
 * est celui de notre origine. En édition un clic choisit l'élément (repère `data-zone`) au lieu de l'actionner.
 */
import { MousePointerClick } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useLangue } from "@/components/mark/langue/langue";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";

import { type Apparence, COULEURS, couleursResolues,type EtatWidget } from "./editeur-donnees";

const LARGEUR_TELEPHONE = 360;
const HAUTEUR_TELEPHONE = 720;
const BORD_TELEPHONE = 6;
// Ordinateur : un bout de page assez grand pour la fenêtre la plus haute (l'avis complet). Téléphone : un écran de 360 × 720.
const ECRANS = {
    ordinateur: { l: 780, h: 640, max: 1 },
    telephone: { l: LARGEUR_TELEPHONE + 2 * BORD_TELEPHONE, h: HAUTEUR_TELEPHONE + 2 * BORD_TELEPHONE, max: 0.75 },
};
export type Ecran = keyof typeof ECRANS;

type Cadre = { x: number; y: number; l: number; h: number };
type Instance = { detruire: () => void; majApercu: (o: Record<string, unknown>) => void; element: HTMLElement; racine: ShadowRoot };
type MarkWidgetGlobal = { apercu: (conteneur: HTMLElement, options: Record<string, unknown>) => Instance };

export const ADRESSE_DU_SCRIPT = "/embed/dograh-widget.js";

/** Charge le script du widget (notre origine) une seule fois ; `pret` quand `window.MarkWidget` existe. */
export function useScriptDuWidget(): boolean {
    const [pret, setPret] = useState(() => typeof window !== "undefined" && !!(window as unknown as { MarkWidget?: unknown }).MarkWidget);
    useEffect(() => {
        if (pret) return;
        const existe = () => !!(window as unknown as { MarkWidget?: unknown }).MarkWidget;
        if (existe()) {
            setPret(true);
            return;
        }
        const s = document.createElement("script");
        s.src = ADRESSE_DU_SCRIPT;
        s.async = true;
        s.onload = () => setPret(existe());
        document.head.appendChild(s);
    }, [pret]);
    return pret;
}

/** Les couleurs résolues, nommées comme le widget les lit (clés du serveur). */
export function couleursDuWidget(ap: Apparence): Record<string, string> {
    const r = couleursResolues(ap);
    const sortie: Record<string, string> = {};
    for (const [cle, cleServeur] of Object.entries(COULEURS)) {
        if (cle !== "fenetreTexte") sortie[cleServeur] = r[cle as keyof typeof COULEURS];
    }
    return sortie;
}

export function ApercuWidget({
    apparence,
    modes,
    etat,
    ecran,
    microRefuse,
    noteBasse,
    zone,
    onChoisir,
    contenu,
}: {
    apparence: Apparence;
    modes: "voix_et_ecrit" | "voix";
    etat: EtatWidget;
    ecran: Ecran;
    microRefuse: boolean;
    noteBasse: boolean;
    zone: string | null;
    onChoisir: (zone: string | null) => void;
    /** Le contenu de la bulle d'un élément choisi. */
    contenu: ReactNode;
}) {
    const { t } = useLangue();
    const pret = useScriptDuWidget();
    const scene = useRef<HTMLDivElement>(null);
    const montage = useRef<HTMLDivElement>(null);
    const cadre = useRef<HTMLDivElement>(null);
    const place = useRef<HTMLDivElement>(null);
    const instance = useRef<Instance | null>(null);
    const choisi = useRef<Element | null>(null);
    const [dispo, setDispo] = useState({ l: 0, h: 0 });
    const [survol, setSurvol] = useState<Cadre | null>(null);
    const [cadreZone, setCadreZone] = useState<Cadre | null>(null);
    const telephone = ecran === "telephone";
    const base = ECRANS[ecran];

    useLayoutEffect(() => {
        const el = place.current;
        if (!el) return;
        const o = new ResizeObserver(([e]) => setDispo({ l: e.contentRect.width, h: e.contentRect.height }));
        o.observe(el);
        return () => o.disconnect();
    }, []);

    const options = useCallback(
        () => ({
            apparence,
            couleurs: couleursDuWidget(apparence),
            etat,
            etoiles: etat === "avis" ? (noteBasse ? 2 : 5) : undefined,
            microRefuse,
            modes,
        }),
        [apparence, etat, noteBasse, microRefuse, modes],
    );

    // Le widget est monté à nouveau quand la taille d'écran change (il mesure sa largeur à la création) ; sinon il se met à jour.
    useEffect(() => {
        if (!pret || !montage.current) return;
        const global = (window as unknown as { MarkWidget: MarkWidgetGlobal }).MarkWidget;
        instance.current = global.apercu(montage.current, { ...options(), largeurCadre: telephone ? LARGEUR_TELEPHONE : undefined });
        return () => {
            instance.current?.detruire();
            instance.current = null;
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [pret, ecran]);
    useEffect(() => {
        instance.current?.majApercu(options());
    }, [options]);

    const cadreDe = (el: Element): Cadre => {
        const a = el.getBoundingClientRect();
        const b = cadre.current!.getBoundingClientRect();
        return { x: a.left - b.left, y: a.top - b.top, l: a.width, h: a.height };
    };
    // Le widget vit dans un shadow DOM : la cible réelle est le premier élément du chemin composé.
    const zoneSous = (e: Event): Element | null => {
        const cible = e.composedPath()[0] as Element | undefined;
        const el = cible?.closest?.("[data-zone]") ?? null;
        return el && instance.current?.racine.contains(el) ? el : null;
    };

    // L'élément choisi garde son contour quand le widget se redessine (texte plus long, autre couleur).
    useLayoutEffect(() => {
        if (!zone) {
            setCadreZone(null);
            return;
        }
        const mesurer = () => {
            const el = choisi.current?.isConnected ? choisi.current : instance.current?.racine.querySelector(`[data-zone="${zone}"]`);
            setCadreZone(el ? cadreDe(el) : null);
        };
        mesurer();
        // Le widget entre avec une petite animation (0,3 s) : on remesure une fois qu'il est posé.
        const minuteur = setTimeout(mesurer, 350);
        return () => clearTimeout(minuteur);
    }, [zone, apparence, etat, ecran, microRefuse, noteBasse, modes, pret]);

    const echelle = dispo.h ? Math.min(base.max, dispo.l / base.l, (dispo.h - 28) / base.h) : 0;

    return (
        <div ref={place} className="flex h-full min-h-0 min-w-0 flex-col items-center" data-testid="apercu-widget">
            <Popover open={!!zone && !!contenu && !!cadreZone} onOpenChange={(o) => !o && onChoisir(null)}>
                <div
                    ref={cadre}
                    className="relative mx-auto"
                    style={{ width: base.l * echelle, height: base.h * echelle, visibility: echelle ? "visible" : "hidden" }}
                    // En édition, un clic choisit l'élément au lieu de l'actionner (le widget ne change pas d'étape).
                    onClickCapture={(e) => {
                        if (!scene.current?.contains(e.target as Node)) return;
                        e.preventDefault();
                        e.stopPropagation();
                        const el = zoneSous(e.nativeEvent);
                        choisi.current = el;
                        onChoisir(el ? el.getAttribute("data-zone") : null);
                    }}
                    onMouseDownCapture={(e) => scene.current?.contains(e.target as Node) && e.preventDefault()}
                    onMouseMove={(e) => {
                        const el = zoneSous(e.nativeEvent);
                        setSurvol(el ? cadreDe(el) : null);
                    }}
                    onMouseLeave={() => setSurvol(null)}
                >
                    <div
                        ref={scene}
                        className={`relative overflow-hidden bg-muted ${telephone ? "rounded-[40px] border-foreground" : "rounded-2xl border-border"}`}
                        style={{
                            width: base.l,
                            height: base.h,
                            borderWidth: telephone ? BORD_TELEPHONE : 1,
                            transform: `scale(${echelle})`,
                            transformOrigin: "top left",
                        }}
                    >
                        {/* Le site simulé : des blocs gris, aucune donnée. */}
                        <div className="pointer-events-none space-y-3 p-5 pt-12">
                            <div className="h-4 w-40 rounded bg-border" />
                            <div className="h-8 w-64 max-w-full rounded bg-border/80" />
                            <div className="h-3 w-56 max-w-full rounded bg-border/60" />
                            <div className="h-3 w-48 max-w-full rounded bg-border/60" />
                            <div className="h-32 rounded-xl bg-border/40" />
                        </div>
                        <div ref={montage} className="absolute inset-0" />
                    </div>
                    {survol && (
                        <div
                            className="pointer-events-none absolute z-[60] rounded-lg border-2 border-dashed border-primary/70"
                            style={{ left: survol.x - 3, top: survol.y - 3, width: survol.l + 6, height: survol.h + 6 }}
                        />
                    )}
                    {cadreZone && (
                        <div
                            className="pointer-events-none absolute z-[60] rounded-lg border-2 border-primary"
                            style={{ left: cadreZone.x - 3, top: cadreZone.y - 3, width: cadreZone.l + 6, height: cadreZone.h + 6 }}
                        />
                    )}
                    <PopoverAnchor asChild>
                        <div
                            className="pointer-events-none absolute"
                            style={cadreZone ? { left: cadreZone.x, top: cadreZone.y, width: cadreZone.l, height: cadreZone.h } : { left: 0, top: 0 }}
                        />
                    </PopoverAnchor>
                </div>
                {contenu && (
                    <PopoverContent side="left" align="center" sideOffset={14} collisionPadding={12} sticky="always" className="w-96 space-y-4" onOpenAutoFocus={(e) => e.preventDefault()}>
                        {contenu}
                    </PopoverContent>
                )}
            </Popover>
            <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <MousePointerClick className="size-3.5" />
                {t({ fr: "Cliquez sur un élément du widget pour changer sa couleur ou son texte", en: "Click an element of the widget to change its colour or text" })}
            </p>
        </div>
    );
}
