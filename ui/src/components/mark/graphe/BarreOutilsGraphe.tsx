"use client";

/**
 * [.mark] Partie 3, sous-lot 20 : la barre d'outils du haut du graphe, façon ElevenLabs (maquette `canevas.tsx`) : annuler,
 * rétablir, réorganiser, aimanter à la grille, carte miniature, statistiques des vrais appels, recherche d'une étape,
 * « empêcher les boucles ». Les gestes viennent de l'éditeur (historique du brouillon, placement, React Flow) : cette barre
 * ne compte rien et ne place rien elle-même. En lecture seule (version passée), seuls les repères restent.
 */
import { BarChart3, Grid3x3, Map as CarteIcone, Redo2, Repeat, Search, Undo2, Wand2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { type Texte, useLangue } from "@/components/mark/langue/langue";
import { Input } from "@/components/ui/input";

const T = {
    annuler: { en: "Undo", fr: "Annuler" },
    retablir: { en: "Redo", fr: "Rétablir" },
    reorganiser: { en: "Tidy up the steps", fr: "Réorganiser les étapes" },
    aimant: { en: "Snap to the grid", fr: "Aimanter à la grille" },
    carte: { en: "Mini map", fr: "Carte miniature" },
    stats: { en: "Statistics of the real calls", fr: "Statistiques des vrais appels" },
    statsLecture: (n: number): Texte => ({ en: `Share of the last ${n} calls that went through each step`, fr: `Part des ${n} derniers appels qui ont traversé chaque étape` }),
    statsChargement: { en: "Reading the calls…", fr: "Lecture des appels…" },
    rechercher: { en: "Search a step", fr: "Rechercher une étape" },
    fermerRecherche: { en: "Close the search", fr: "Fermer la recherche" },
    aucune: { en: "No step found", fr: "Aucune étape trouvée" },
    boucles: { en: "Forbid loops between steps", fr: "Empêcher les boucles entre les étapes" },
    boucleLecture: (n: number): Texte => ({
        en: `${n} transition${n > 1 ? "s" : ""} close a loop`,
        fr: `${n} transition${n > 1 ? "s" : ""} ferme${n > 1 ? "nt" : ""} une boucle`,
    }),
} satisfies Record<string, Texte | ((n: number) => Texte)>;

export type EtapeCherchable = { id: string; nom: string; type: string };

/** La recherche d'une étape par son nom ou son type : insensible à la casse et aux accents. */
export const plie = (s: string) => s.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();
export function chercherLesEtapes(etapes: EtapeCherchable[], saisie: string): EtapeCherchable[] {
    const q = plie(saisie.trim());
    if (!q) return [];
    return etapes.filter((e) => plie(e.nom).includes(q) || plie(e.type).includes(q));
}

export interface BarreOutilsGraphe {
    lectureSeule: boolean;
    peutAnnuler: boolean;
    peutRetablir: boolean;
    onAnnuler: () => void;
    onRetablir: () => void;
    onReorganiser: () => void;
    aimant: boolean;
    onAimant: () => void;
    carte: boolean;
    onCarte: () => void;
    stats: boolean;
    onStats: () => void;
    /** Nombre d'appels lus pour les statistiques ; `null` tant qu'ils se chargent. */
    appelsLus: number | null;
    boucles: boolean;
    onBoucles: () => void;
    /** Le nombre de transitions qui ferment une boucle (dit seulement quand le réglage est allumé). */
    enBoucle: number;
    etapes: EtapeCherchable[];
    onChoisirEtape: (id: string) => void;
}

export function BarreOutilsGraphe(p: BarreOutilsGraphe) {
    const { t } = useLangue();
    const [recherche, setRecherche] = useState<string | null>(null);
    const trouvees = useMemo(() => chercherLesEtapes(p.etapes, recherche ?? "").slice(0, 8), [p.etapes, recherche]);
    useEffect(() => {
        if (recherche === null) return;
        const echap = (e: KeyboardEvent) => {
            if (e.key === "Escape") setRecherche(null);
        };
        window.addEventListener("keydown", echap);
        return () => window.removeEventListener("keydown", echap);
    }, [recherche]);
    const outil =
        "inline-flex size-8 cursor-pointer items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:cursor-default disabled:opacity-40";
    const actif = "bg-muted text-foreground";
    return (
        <div className="absolute top-3 left-4 z-20" data-barre-outils-graphe>
            <div className="flex items-center gap-0.5 rounded-xl border bg-card p-1 shadow-sm">
                {!p.lectureSeule && (
                    <>
                        <button type="button" className={outil} aria-label={t(T.annuler)} title={t(T.annuler)} disabled={!p.peutAnnuler} onClick={p.onAnnuler}>
                            <Undo2 className="size-4" />
                        </button>
                        <button type="button" className={outil} aria-label={t(T.retablir)} title={t(T.retablir)} disabled={!p.peutRetablir} onClick={p.onRetablir}>
                            <Redo2 className="size-4" />
                        </button>
                        <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                        <button type="button" className={outil} aria-label={t(T.reorganiser)} title={t(T.reorganiser)} onClick={p.onReorganiser}>
                            <Wand2 className="size-4" />
                        </button>
                        <button type="button" className={`${outil} ${p.aimant ? actif : ""}`} aria-pressed={p.aimant} aria-label={t(T.aimant)} title={t(T.aimant)} onClick={p.onAimant}>
                            <Grid3x3 className="size-4" />
                        </button>
                    </>
                )}
                <button type="button" className={`${outil} ${p.carte ? actif : ""}`} aria-pressed={p.carte} aria-label={t(T.carte)} title={t(T.carte)} onClick={p.onCarte}>
                    <CarteIcone className="size-4" />
                </button>
                <button
                    type="button"
                    className={`${outil} ${p.stats ? actif : ""}`}
                    aria-pressed={p.stats}
                    aria-label={t(T.stats)}
                    title={p.stats ? (p.appelsLus === null ? t(T.statsChargement) : t(T.statsLecture(p.appelsLus))) : t(T.stats)}
                    onClick={p.onStats}
                >
                    <BarChart3 className="size-4" />
                </button>
                {!p.lectureSeule && (
                    <button
                        type="button"
                        className={`${outil} ${p.boucles ? actif : ""}`}
                        aria-pressed={p.boucles}
                        aria-label={t(T.boucles)}
                        title={p.boucles && p.enBoucle > 0 ? `${t(T.boucles)} · ${t(T.boucleLecture(p.enBoucle))}` : t(T.boucles)}
                        onClick={p.onBoucles}
                    >
                        <Repeat className="size-4" />
                    </button>
                )}
                {recherche === null ? (
                    <button type="button" className={outil} aria-label={t(T.rechercher)} title={t(T.rechercher)} onClick={() => setRecherche("")}>
                        <Search className="size-4" />
                    </button>
                ) : (
                    <span className="flex items-center gap-1 pl-1">
                        <Search className="size-3.5 text-muted-foreground" aria-hidden />
                        <Input
                            autoFocus
                            value={recherche}
                            aria-label={t(T.rechercher)}
                            placeholder={t(T.rechercher)}
                            onChange={(e) => setRecherche(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === "Enter" && trouvees[0]) {
                                    p.onChoisirEtape(trouvees[0].id);
                                    setRecherche(null);
                                }
                            }}
                            className="h-7 w-44 border-transparent px-1 shadow-none"
                        />
                        <button type="button" className={outil} aria-label={t(T.fermerRecherche)} onClick={() => setRecherche(null)}>
                            <X className="size-3.5" />
                        </button>
                    </span>
                )}
            </div>
            {recherche !== null && recherche.trim() !== "" && (
                <ul role="listbox" aria-label={t(T.rechercher)} className="mt-1 w-72 rounded-xl border bg-card p-1 text-sm shadow-sm" data-resultats-recherche>
                    {trouvees.length === 0 && <li className="px-2 py-1.5 text-muted-foreground">{t(T.aucune)}</li>}
                    {trouvees.map((e) => (
                        <li key={e.id} role="option" aria-selected={false}>
                            <button
                                type="button"
                                className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted hover:font-medium"
                                onClick={() => {
                                    p.onChoisirEtape(e.id);
                                    setRecherche(null);
                                }}
                            >
                                <span className="truncate">{e.nom}</span>
                                <span className="shrink-0 text-xs text-muted-foreground">{e.type}</span>
                            </button>
                        </li>
                    ))}
                </ul>
            )}
        </div>
    );
}
