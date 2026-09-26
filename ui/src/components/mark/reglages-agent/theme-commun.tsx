"use client";

/**
 * [.mark] What every theme of the agent page shares: its props, how it tells
 * the navigation it is changed or blocked, and « show » for a setting that
 * another choice hides (convention E7).
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useUnsavedChanges } from "@/context/UnsavedChangesContext";
import type { WorkflowConfigurations } from "@/types/workflow-configurations";

import type { ErreurNommee } from "../ecran/Theme";
import { allerAuReglage } from "../ecran/useThemesOuverts";
import type { Texte } from "../langue/langue";
import type { Enregistrer } from "./enregistrement";

export interface ProprietesThemeAgent {
    /** The RESOLVED configuration, as the page handed it to every card. */
    resolue: WorkflowConfigurations;
    workflowName: string;
    onSave: Enregistrer;
    ouvert: boolean;
    onBasculer: () => void;
    /** Opens this theme (« show »). */
    ouvrir: () => void;
}

/** The themes in error, for the navigation's red dot. */
export const ContexteErreursThemes = createContext<(id: string, enErreur: boolean) => void>(() => undefined);

/** Registers the theme's orange dot (unsaved) and red dot (value to fix). */
export const useEtatTheme = (id: string, modifie: boolean, enErreur: boolean) => {
    useUnsavedChanges(id, modifie);
    const signaler = useContext(ContexteErreursThemes);
    useEffect(() => {
        signaler(id, enErreur);
    }, [id, enErreur, signaler]);
    useEffect(() => () => signaler(id, false), [id, signaler]);
};

export const NOTE_REVELE: Texte = {
    en: "Hidden for this agent by another setting: shown here only so its value can be fixed.",
    fr: "Masqué pour cet agent par un autre réglage : affiché ici seulement pour corriger sa valeur.",
};

/**
 * A setting hidden by another choice, but whose value blocks the save, is
 * REVEALED by « show »: the theme draws it anyway, with `NOTE_REVELE`, until
 * the page is left. Without this, the theme would be locked by a value nobody
 * can reach -- the dead end the Speech Tuning card already named.
 */
export const useRevelation = (ouvrir: () => void) => {
    const [reveles, setReveles] = useState<Set<string>>(() => new Set());
    const afficher = useCallback(
        (cle: string) => {
            setReveles((avant) => (avant.has(cle) ? avant : new Set(avant).add(cle)));
            ouvrir();
            allerAuReglage(cle);
        },
        [ouvrir],
    );
    /** Whether to draw the setting, and the note to show when it is only revealed. */
    const visible = (cle: string, condition: boolean): { affiche: boolean; note: Texte | null } =>
        condition ? { affiche: true, note: null } : reveles.has(cle) ? { affiche: true, note: NOTE_REVELE } : { affiche: false, note: null };
    return { afficher, visible };
};

/** Turns « key → message » into the named errors a theme shows (E7). */
export const nommerErreurs = (
    erreurs: Array<{ cle: string; libelle: Texte; message: Texte }>,
    t: (texte: Texte) => string,
    afficher: (cle: string) => void,
): ErreurNommee[] =>
    erreurs.map((erreur) => ({
        cle: erreur.cle,
        libelle: t(erreur.libelle),
        message: t(erreur.message),
        afficher: () => afficher(erreur.cle),
    }));

/** Two values the way the original cards compared them. */
export const differe = (a: unknown, b: unknown) => JSON.stringify(a) !== JSON.stringify(b);

/**
 * A theme's draft: what the screen shows, against what is saved.
 *
 * After a save, the page hands back the configuration AS THE SERVER STORED IT,
 * which can differ from what was sent (a list completed, a value normalized).
 * `resynchroniser` makes the draft follow it, so a theme never stays « changed »
 * on what the server just confirmed -- the defect the call record card fixed on
 * 24/09, applied to every theme. `extraireFn` is a module-level function.
 */
export const useBrouillon = <T,>(resolue: WorkflowConfigurations, extraireFn: (r: WorkflowConfigurations) => T) => {
    // eslint-disable-next-line react-hooks/exhaustive-deps
    const enregistre = useMemo(() => extraireFn(resolue), [resolue]);
    const [brouillon, setBrouillon] = useState<T>(() => extraireFn(resolue));
    const [aResynchroniser, setAResynchroniser] = useState(false);
    useEffect(() => {
        if (!aResynchroniser) return;
        setBrouillon(extraireFn(resolue));
        setAResynchroniser(false);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [aResynchroniser, resolue]);
    const resynchroniser = useCallback(() => setAResynchroniser(true), []);
    return { enregistre, brouillon, setBrouillon, resynchroniser };
};
