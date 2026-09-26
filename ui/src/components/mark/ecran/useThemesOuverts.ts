"use client";

/**
 * [.mark] Which themes of a page are open, and « show » (convention E7).
 *
 * `afficher` opens the theme, then -- once it has rendered -- brings the
 * setting on screen and puts the cursor in it. The page decides separately
 * whether a setting hidden by another choice must be revealed; this only
 * opens and scrolls.
 */
import { useCallback, useState } from "react";

export const allerAuReglage = (cle: string) => {
    // Twice a frame: the theme renders its content on the next one.
    const aller = () => {
        const bloc = document.getElementById(`reglage-${cle}`);
        if (!bloc) return false;
        bloc.scrollIntoView?.({ block: "center", behavior: "smooth" });
        bloc.querySelector<HTMLElement>("input, textarea, select, button[role='switch']")?.focus({ preventScroll: true });
        return true;
    };
    setTimeout(() => {
        if (!aller()) setTimeout(aller, 50);
    }, 0);
};

export const allerAuTheme = (id: string) => {
    setTimeout(() => document.getElementById(id)?.scrollIntoView?.({ block: "start", behavior: "smooth" }), 0);
};

export const useThemesOuverts = (initiaux: string[] = []) => {
    const [ouverts, setOuverts] = useState<Set<string>>(() => new Set(initiaux));

    const basculer = useCallback((id: string) => {
        setOuverts((avant) => {
            const apres = new Set(avant);
            if (apres.has(id)) apres.delete(id);
            else apres.add(id);
            return apres;
        });
    }, []);

    const ouvrir = useCallback((id: string) => {
        setOuverts((avant) => (avant.has(id) ? avant : new Set(avant).add(id)));
    }, []);

    const afficher = useCallback(
        (theme: string, cle: string) => {
            ouvrir(theme);
            allerAuReglage(cle);
        },
        [ouvrir],
    );

    const choisir = useCallback(
        (theme: string) => {
            ouvrir(theme);
            allerAuTheme(theme);
        },
        [ouvrir],
    );

    return { estOuvert: (id: string) => ouverts.has(id), basculer, ouvrir, afficher, choisir };
};
