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
import { ChevronDown, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { type Texte, useLangue } from "../langue/langue";

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
    children: ReactNode;
}

export const TEXTES_THEME = {
    modifie: { en: "Unsaved changes", fr: "Modifications non enregistrées" },
    enErreur: { en: "A value cannot be saved", fr: "Une valeur ne peut pas être enregistrée" },
    enregistrer: { en: "Save", fr: "Enregistrer" },
    enregistrement: { en: "Saving...", fr: "Enregistrement..." },
    afficher: { en: "show", fr: "afficher" },
    aCorriger: { en: "To fix before saving:", fr: "À corriger avant d'enregistrer :" },
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
                    className="h-2 w-2 shrink-0 rounded-full bg-orange-500"
                />
            )}
            {enErreur && (
                <span
                    role="img"
                    aria-label={t(TEXTES_THEME.enErreur)}
                    title={t(TEXTES_THEME.enErreur)}
                    data-pastille="erreur"
                    className="h-2 w-2 shrink-0 rounded-full bg-red-500"
                />
            )}
        </>
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
    children,
}: ProprietesTheme) => {
    const { t } = useLangue();
    const idContenu = `${id}-contenu`;
    const puces = resume.filter((valeur): valeur is string => Boolean(valeur));
    const bloque =
        !enregistrement
        || enregistrement.enCours
        || erreurs.length > 0
        || (!modifie && !enregistrement.actifSansModification);

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
                    {children}

                    {enregistrement && (
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
                    )}
                </div>
            )}
        </section>
    );
};
