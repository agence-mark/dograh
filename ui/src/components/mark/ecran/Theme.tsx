"use client";

/**
 * [.mark] A THEME of a settings page: the one thing that folds (convention E1).
 *
 * Chantier reorganisation-ecran-reglages. A settings page is a column of
 * themes. Folded, a theme shows its title, a summary of its key values (E3) and
 * two dots: orange for a change not saved yet, red for a value that cannot be
 * saved. Open, it shows ALL its settings, separated by `Intertitre` -- nothing
 * folds inside a theme (E1).
 *
 * Its button (E6) saves the theme. A value out of range blocks it and is NAMED
 * next to it, with « show » that brings the setting on screen even when another
 * choice hides it (E7): a theme locked by a value nobody can see is a dead end.
 *
 * Three themes keep the buttons they had, because they save elsewhere or at
 * once (Services, the trade vocabulary, Developers): they pass no `enregistrement`.
 */
import { ChevronDown, type LucideIcon, Search, X } from "lucide-react";
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { useFormeMaquette } from "./forme-maquette";
import { THEMES_COMMUNS_EN_LECTURE, useGroupe, ZoneCommune } from "../groupe/contexte-groupe";
import { type Texte, useLangue } from "../langue/langue";
import { FenetreParente } from "../studio/fenetre-parente";
import { Info } from "../studio/marques";
import { ContexteLigneMaquette } from "./ChampReglage";

export interface ErreurNommee {
    /** The technical name of the setting (convention E5). */
    cle: string;
    /** Its readable label, already in the current language. */
    libelle: string;
    /** Why it cannot be saved, already in the current language. */
    message: string;
    /** Opens the theme (and the sub-menu) on the setting, shown even if hidden. */
    afficher: () => void;
}

export interface EnregistrementTheme {
    onEnregistrer: () => void;
    enCours: boolean;
    /**
     * The organization's cards were saveable untouched (their PUT replaces the
     * whole row): their themes keep that. The agent's were not.
     */
    actifSansModification?: boolean;
}

export interface ProprietesTheme {
    id: string;
    icone: LucideIcon;
    titre: Texte;
    description: Texte;
    /** Key values shown while folded, already in the current language (E3). */
    resume: Array<string | null | undefined | false>;
    ouvert: boolean;
    onBasculer: () => void;
    modifie: boolean;
    erreurs: ErreurNommee[];
    /** Absent: the theme keeps the buttons of what it contains (E6 exceptions). */
    enregistrement?: EnregistrementTheme;
    /**
     * [.mark] U2 bis / U2 (E116) : le thème posé À PLAT dans un sous-onglet de page (Entreprise, Base et
     * automatisations) : ni carte ni repli, un titre avec son « ! » (la description), tout son contenu, le même
     * bouton d'enregistrement en pied. Les pastilles de changement restent à côté du titre.
     */
    plat?: boolean;
    /** [.mark] K4 : posé à plat SANS son titre (la page porte déjà son intertitre, comme « Base et automatisations »). */
    sansTitre?: boolean;
    /**
     * [.mark] K1b : les lignes en lecture de la section (libellé, valeur) quand la page montre ses thèmes en lignes avec
     * un bouton « Modifier » (`ContexteLignes`). Les valeurs viennent de ce que le thème sait déjà ; jamais inventées.
     */
    lignes?: LigneLue[];
    children: ReactNode;
}

export type LigneLue = { libelle: Texte; valeur: ReactNode };

/**
 * [.mark] U4 (E42, E44) : l'onglet Réglages d'un agent montre ses thèmes EN CARTES ; une carte ouvre la fenêtre du
 * thème (en-tête et pied fixes, corps blanc qui défile). Une page qui fournit ce contexte passe tous ses thèmes en
 * cartes ; sans lui, un thème garde son repli d'avant (Entreprise, Base, Réglages de l'organisation).
 */
export interface ValeurCartes {
    /** « Annuler » : le thème oublie son brouillon et la fenêtre se ferme. */
    annuler: (id: string) => void;
    /** Le niveau du thème (Essentiel, Avancé, Moteur), dit sur la carte. */
    niveaux?: Record<string, Texte>;
    /** Le nombre de réglages propres à l'agent, par thème (E38). */
    propres?: Record<string, number>;
}
export const ContexteCartes = createContext<ValeurCartes | null>(null);

/**
 * [.mark] K1b (décision d'Evan, 04/11, comme la maquette) : une page qui fournit ce contexte montre chaque thème en
 * LIGNES EN LECTURE avec un bouton « Modifier » ; le bouton ouvre la fenêtre du thème (celle des cartes), qui porte
 * tous ses réglages et son enregistrement : aucune fonction en moins.
 */
export const ContexteLignes = createContext<{ annuler: (id: string) => void } | null>(null);

export const TEXTES_THEME = {
    modifie: { en: "Unsaved changes", fr: "Modifications non enregistrées" },
    enErreur: { en: "A value cannot be saved", fr: "Une valeur ne peut pas être enregistrée" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    enregistrement: { en: "Saving...", fr: "Enregistrement..." },
    afficher: { en: "show", fr: "afficher" },
    aCorriger: { en: "To fix before saving:", fr: "À corriger avant d'enregistrer :" },
    annuler: { en: "Cancel", fr: "Annuler" },
    propres: { en: "own to the agent", fr: "propres à l'agent" },
} satisfies Record<string, Texte>;

export const Pastilles = ({ modifie, enErreur }: { modifie: boolean; enErreur: boolean }) => {
    const { t } = useLangue();
    return (
        <>
            {modifie && (
                <span
                    role="img"
                    aria-label={t(TEXTES_THEME.modifie)}
                    title={t(TEXTES_THEME.modifie)}
                    data-pastille="modifie"
                    className="h-2 w-2 shrink-0 rounded-full bg-(--acc)"
                />
            )}
            {enErreur && (
                <span
                    role="img"
                    aria-label={t(TEXTES_THEME.enErreur)}
                    title={t(TEXTES_THEME.enErreur)}
                    data-pastille="erreur"
                    className="h-2 w-2 shrink-0 rounded-full bg-destructive"
                />
            )}
        </>
    );
};

/**
 * [.mark] La fenêtre d'un thème : centrée, en-tête et pied fixes, corps blanc qui défile (E42, E55). Posée DANS la carte
 * (et non dans un portail) : le contenu du thème reste un descendant de son thème, comme avant (liens « afficher »,
 * tests, ancres). Echap ou un clic sur le fond la ferme ; une fenêtre ouverte depuis elle prend sa taille (E71).
 */
const TAILLE_FENETRE_THEME = "sm:max-w-3xl h-[86vh]";
const FenetreDuTheme = ({ id, onFermer, children }: { id: string; onFermer: () => void; children: ReactNode }) => {
    const { t } = useLangue();
    useEffect(() => {
        const surTouche = (e: KeyboardEvent) => {
            // Une fenêtre ouverte depuis celle-ci (portail Radix) garde l'Echap pour elle-même.
            if (e.key === "Escape" && !e.defaultPrevented && !document.querySelector("[data-slot='dialog-content']")) onFermer();
        };
        document.addEventListener("keydown", surTouche);
        return () => document.removeEventListener("keydown", surTouche);
    }, [onFermer]);
    return (
        <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
            data-fond-fenetre
            onMouseDown={(e) => e.target === e.currentTarget && onFermer()}
        >
            <div
                role="dialog"
                aria-modal="true"
                aria-labelledby={`${id}-titre`}
                data-fenetre-theme={id}
                className="relative flex h-[86vh] w-full flex-col overflow-hidden rounded-lg border bg-background shadow-lg sm:max-w-3xl"
            >
                <FenetreParente.Provider value={{ classe: TAILLE_FENETRE_THEME }}>{children}</FenetreParente.Provider>
                <button
                    type="button"
                    aria-label={t({ en: "Close", fr: "Fermer" })}
                    onClick={onFermer}
                    className="absolute top-4 right-4 cursor-pointer rounded-xs p-1 text-muted-foreground hover:text-foreground"
                >
                    <X className="size-4" />
                </button>
            </div>
        </div>
    );
};

export const Theme = ({
    id,
    icone: Icone,
    titre,
    description,
    resume,
    ouvert,
    onBasculer,
    modifie,
    erreurs,
    enregistrement,
    plat = false,
    sansTitre = false,
    lignes,
    children,
}: ProprietesTheme) => {
    const { t } = useLangue();
    // [.mark] K3 : la recherche de la fenêtre (maquette : « Chercher dans <thème> ») et le corps qu'elle filtre.
    const [filtre, setFiltre] = useState("");
    const [aucun, setAucun] = useState(false);
    const corps = useRef<HTMLDivElement>(null);
    // Chaque réglage se retrouve par son libellé ou son nom technique ; un groupe sans réglage visible se replie.
    useEffect(() => {
        const racine = corps.current;
        if (!racine) return;
        const q = filtre.trim().toLowerCase();
        let visibles = 0;
        racine.querySelectorAll<HTMLElement>("[data-reglage]").forEach((el) => {
            const trouve = q === "" || (el.textContent ?? "").toLowerCase().includes(q) || (el.dataset.reglage ?? "").toLowerCase().includes(q);
            el.hidden = !trouve;
            if (trouve) visibles += 1;
        });
        racine.querySelectorAll<HTMLElement>("[data-groupe]").forEach((groupe) => {
            groupe.hidden = q !== "" && !groupe.querySelector("[data-reglage]:not([hidden])");
        });
        setAucun(q !== "" && visibles === 0);
    });
    useEffect(() => {
        if (!ouvert) setFiltre("");
    }, [ouvert]);
    // [.mark] K4b : les pages de la maquette espacent leurs blocs de 40 px (un thème posé à plat y est une colonne de blocs).
    const maquette = useFormeMaquette();
    // [.mark] Lot 12 (A10) : chez un spécialisé, les thèmes communs viennent du principal : en
    // lecture, avec un bandeau, et sans bouton d'enregistrement (rien à enregistrer ici).
    const { specialiseDe } = useGroupe();
    const enLecture = specialiseDe !== null && THEMES_COMMUNS_EN_LECTURE.includes(id);
    const idContenu = `${id}-contenu`;
    const puces = resume.filter((valeur): valeur is string => Boolean(valeur));
    const bloque =
        !enregistrement
        || enregistrement.enCours
        || erreurs.length > 0
        || (!modifie && !enregistrement.actifSansModification);

    const pied =
        enregistrement && !enLecture ? (
            <div className="flex flex-wrap items-center justify-end gap-3 border-t pt-4">
                {erreurs.length > 0 && (
                    <div role="alert" className="mr-auto space-y-1 text-xs text-destructive">
                        <p>{t(TEXTES_THEME.aCorriger)}</p>
                        <ul className="space-y-0.5">
                            {erreurs.map((erreur) => (
                                <li key={erreur.cle} data-erreur={erreur.cle}>
                                    <span className="font-medium">{erreur.libelle}</span>{" "}
                                    <code className="text-[11px] opacity-70">{erreur.cle}</code> : {erreur.message}{" "}
                                    <button type="button" className="underline" onClick={erreur.afficher}>
                                        {t(TEXTES_THEME.afficher)}
                                    </button>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
                {erreurs.length === 0 && modifie && (
                    <span className="text-xs text-muted-foreground">{t(TEXTES_THEME.modifie)}</span>
                )}
                <Button
                    type="button"
                    aria-label={`${t(TEXTES_THEME.enregistrer)} ${t(titre)}`}
                    onClick={enregistrement.onEnregistrer}
                    disabled={bloque}
                >
                    {enregistrement.enCours ? t(TEXTES_THEME.enregistrement) : t(TEXTES_THEME.enregistrer)}
                </Button>
            </div>
        ) : null;

    const cartes = useContext(ContexteCartes);
    const enLignes = useContext(ContexteLignes);
    const annuler = (cartes ?? enLignes)?.annuler ?? (() => undefined);
    // [.mark] K3 : dans l'onglet Réglages d'un agent, la fenêtre prend la forme de la maquette (`reglages-fenetre.tsx`) :
    // pastille d'icône, titre, résumé, recherche dans le thème ; pied « Aucune modification » / Annuler / Enregistrer.
    const dansAgent = cartes !== null;
    const pastillesTitre = <Pastilles modifie={modifie} enErreur={erreurs.length > 0} />;
    const fenetre = ouvert ? (
        <FenetreDuTheme id={id} onFermer={onBasculer}>
            {dansAgent ? (
                <div className="shrink-0 space-y-3 border-b px-6 pt-5 pr-12 pb-4">
                    <div className="flex items-center gap-3">
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-muted">
                            <Icone className="size-5" />
                        </span>
                        <div className="min-w-0 flex-1">
                            <h2 id={`${id}-titre`} className="flex items-center gap-2 text-lg leading-none font-semibold">
                                {t(titre)}
                                {pastillesTitre}
                            </h2>
                            <p className="mt-1 truncate text-sm text-muted-foreground">{t(description)}</p>
                        </div>
                    </div>
                    <div className="relative w-full max-w-72">
                        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                            value={filtre}
                            onChange={(e) => setFiltre(e.target.value)}
                            aria-label={`${t({ en: "Search in", fr: "Chercher dans" })} ${t(titre)}`}
                            placeholder={`${t({ en: "Search in", fr: "Chercher dans" })} ${t(titre)}`}
                            className="h-8 border-transparent bg-muted/50 pl-8 shadow-none focus-visible:bg-background"
                        />
                    </div>
                </div>
            ) : (
                <div className="shrink-0 border-b px-6 pt-5 pr-12 pb-4">
                    <h2 id={`${id}-titre`} className="flex items-center gap-2 text-lg leading-none font-semibold">
                        {t(titre)}
                        <Info>{t(description)}</Info>
                        {pastillesTitre}
                    </h2>
                </div>
            )}
            <div ref={corps} className={cn("min-h-0 flex-1 overflow-y-auto bg-background px-6 py-5", dansAgent ? "space-y-8" : "space-y-6")}>
                <ContexteLigneMaquette.Provider value={dansAgent}>
                    {enLecture ? <ZoneCommune>{children}</ZoneCommune> : children}
                </ContexteLigneMaquette.Provider>
                {aucun && <p className="py-16 text-center text-sm text-muted-foreground">{t({ en: "No setting.", fr: "Aucun réglage." })}</p>}
            </div>
            {enregistrement && !enLecture && (
                <div className="flex flex-wrap items-center justify-end gap-3 border-t px-6 py-3" data-pied-fenetre>
                    {erreurs.length > 0 && (
                        <div role="alert" className="mr-auto space-y-1 text-xs text-destructive">
                            <p>{t(TEXTES_THEME.aCorriger)}</p>
                            <ul className="space-y-0.5">
                                {erreurs.map((erreur) => (
                                    <li key={erreur.cle} data-erreur={erreur.cle}>
                                        <span className="font-medium">{erreur.libelle}</span>{" "}
                                        <code className="text-[11px] opacity-70">{erreur.cle}</code> : {erreur.message}{" "}
                                        <button type="button" className="cursor-pointer hover:font-semibold" onClick={erreur.afficher}>
                                            {t(TEXTES_THEME.afficher)}
                                        </button>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}
                    {erreurs.length === 0 && modifie && (
                        <span className={cn("mr-auto text-muted-foreground", dansAgent ? "text-sm" : "text-xs")}>{t(TEXTES_THEME.modifie)}</span>
                    )}
                    {erreurs.length === 0 && !modifie && dansAgent && (
                        <span className="mr-auto text-sm text-muted-foreground">{t({ en: "No change", fr: "Aucune modification" })}</span>
                    )}
                    <Button type="button" variant={dansAgent ? "outline" : "ghost"} onClick={() => annuler(id)}>
                        {t(TEXTES_THEME.annuler)}
                    </Button>
                    <Button
                        type="button"
                        aria-label={`${t(TEXTES_THEME.enregistrer)} ${t(titre)}`}
                        onClick={enregistrement.onEnregistrer}
                        disabled={bloque}
                    >
                        {enregistrement.enCours
                            ? t(TEXTES_THEME.enregistrement)
                            : dansAgent
                              ? t({ en: "Save the draft", fr: "Enregistrer le brouillon" })
                              : t(TEXTES_THEME.enregistrer)}
                    </Button>
                </div>
            )}
        </FenetreDuTheme>
    ) : null;

    if (enLignes && !plat && !cartes) {
        // [.mark] K1b : comme la maquette, un titre, « Modifier », puis les lignes en lecture (libellé gris, valeur).
        return (
            <section id={id} data-theme={id} data-lignes className="scroll-mt-20">
                <div className="flex items-center gap-2">
                    <h2 className="flex flex-1 items-center gap-1.5 text-base font-semibold">
                        {t(titre)}
                        <Info>{t(description)}</Info>
                        <Pastilles modifie={modifie} enErreur={erreurs.length > 0} />
                    </h2>
                    <Button type="button" variant="outline" size="sm" aria-haspopup="dialog" aria-expanded={ouvert} onClick={onBasculer}>
                        {t({ en: "Edit", fr: "Modifier" })}
                    </Button>
                </div>
                <div className="mt-4 divide-y border-t">
                    {(lignes ?? []).map((ligne, i) => (
                        <div key={i} className="flex items-center gap-3 py-3 text-sm">
                            <span className="w-64 shrink-0 text-muted-foreground">{t(ligne.libelle)}</span>
                            <span className="min-w-0 flex-1">{ligne.valeur}</span>
                        </div>
                    ))}
                </div>
                {fenetre}
            </section>
        );
    }

    if (cartes && !plat) {
        const propres = cartes.propres?.[id] ?? 0;
        const niveau = cartes.niveaux?.[id];
        return (
            <section id={id} data-theme={id} data-carte className="scroll-mt-20">
                <button
                    type="button"
                    aria-haspopup="dialog"
                    aria-expanded={ouvert}
                    onClick={onBasculer}
                    className="flex h-full w-full cursor-pointer flex-col rounded-xl border bg-card p-4 text-left transition-shadow hover:shadow-md"
                >
                    <Icone className="mb-3 size-4 text-muted-foreground" />
                    <span className="flex items-center gap-2">
                        <span className="text-sm font-medium">{t(titre)}</span>
                        <Pastilles modifie={modifie} enErreur={erreurs.length > 0} />
                    </span>
                    <span className="line-clamp-2 block text-xs text-muted-foreground">{t(description)}</span>
                    {propres > 0 && (
                        <span className="block pt-2 text-[11px] text-muted-foreground" data-propres={propres} data-niveau-carte={niveau ? t(niveau) : undefined}>
                            {`${propres} ${t(TEXTES_THEME.propres)}`}
                        </span>
                    )}
                </button>
                {fenetre}
            </section>
        );
    }

    if (plat) {
        return (
            <section id={id} data-theme={id} data-plat className={maquette ? "space-y-10" : "space-y-6"}>
                {sansTitre ? (
                    // [.mark] K4b : aucune boîte d'en-tête (même vide, elle ferait ajouter 40 px au bloc suivant) : le titre est le nom de la section.
                    <h2 className="sr-only">{t(titre)}</h2>
                ) : (
                    <div className="flex items-center gap-2">
                        <h2 className="text-base font-semibold">{t(titre)}</h2>
                        <Info>{t(description)}</Info>
                        <Pastilles modifie={modifie} enErreur={erreurs.length > 0} />
                    </div>
                )}
                <div className={maquette ? "space-y-10" : "space-y-6"}>{enLecture ? <ZoneCommune>{children}</ZoneCommune> : children}</div>
                {pied}
            </section>
        );
    }

    return (
        <section id={id} data-theme={id} className="scroll-mt-20 rounded-lg border bg-card">
            <button
                type="button"
                aria-expanded={ouvert}
                aria-controls={idContenu}
                onClick={onBasculer}
                className="flex w-full items-start gap-3 px-5 py-4 text-left"
            >
                <Icone className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 space-y-1">
                    <span className="flex items-center gap-2">
                        <span className="text-base font-semibold">{t(titre)}</span>
                        <Pastilles modifie={modifie} enErreur={erreurs.length > 0} />
                    </span>
                    <span className="block text-sm text-muted-foreground">{t(description)}</span>
                    {!ouvert && puces.length > 0 && (
                        <span className="flex flex-wrap gap-1.5 pt-1" data-resume={id}>
                            {puces.map((puce, i) => (
                                <span key={i} className="rounded-md border bg-muted/40 px-2 py-0.5 text-xs text-muted-foreground">
                                    {puce}
                                </span>
                            ))}
                        </span>
                    )}
                </span>
                <ChevronDown
                    className={cn("mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform", ouvert && "rotate-180")}
                />
            </button>

            {ouvert && (
                <div id={idContenu} className="space-y-6 border-t px-5 py-5">
                    {enLecture ? <ZoneCommune>{children}</ZoneCommune> : children}

                    {pied}
                </div>
            )}
        </section>
    );
};
