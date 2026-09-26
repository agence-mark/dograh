"use client";

/**
 * [.mark] The language of the screen: French or English, chosen by each user.
 *
 * Convention `reference/22-convention-ecran.md` § 4 (T1, T2), decisions D10 and
 * D12 of Evan (26/09/2026):
 *
 *   - the choice is a preference of each USER, kept by their browser, never a
 *     setting of the organization;
 *   - the application opens in FRENCH as long as the user has not chosen.
 *
 * Our screens (`components/mark/`) write every text in both languages, as a
 * `Texte` ({ en, fr }), and show it through `useLangue().t`. Dograh's own
 * screens are translated over the top by a dictionary (`TraductionDograh`),
 * never by editing their files.
 *
 * ⛔ Outside the provider (a component rendered alone, in a test), the
 * language is ENGLISH: the screen's texts were English before this chantier,
 * and the tests of every component written until then read them in English.
 * The French default of D12 is the provider's, which `app/layout.tsx` mounts
 * around the whole application.
 */
import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { TraductionDograh } from "./TraductionDograh";

export type Langue = "fr" | "en";

/** A text of our screens, written in both languages (convention T2). */
export interface Texte {
    en: string;
    fr: string;
}

/** Where the browser keeps the user's choice. */
export const CLE_LANGUE = "mark.langue";

/** The language when the user has not chosen (D12). */
export const LANGUE_PAR_DEFAUT: Langue = "fr";

interface ValeurLangue {
    langue: Langue;
    choisir: (langue: Langue) => void;
    /** The text in the current language. */
    t: (texte: Texte) => string;
}

const traduire = (langue: Langue) => (texte: Texte) => texte[langue];

const ContexteLangue = createContext<ValeurLangue>({
    langue: "en",
    choisir: () => undefined,
    t: traduire("en"),
});

/** The stored choice, or null when there is none or the storage is not reachable. */
export const lireLangueGardee = (): Langue | null => {
    try {
        const valeur = window.localStorage.getItem(CLE_LANGUE);
        return valeur === "fr" || valeur === "en" ? valeur : null;
    } catch {
        // Private window, blocked site data: the default applies.
        return null;
    }
};

const garderLangue = (langue: Langue) => {
    try {
        window.localStorage.setItem(CLE_LANGUE, langue);
    } catch {
        // Not kept: the choice still holds until the page is reloaded.
    }
};

export const FournisseurLangue = ({ children }: { children: ReactNode }) => {
    // The server render has no browser storage: it renders the default, and
    // the stored choice is read once mounted.
    const [langue, setLangue] = useState<Langue>(LANGUE_PAR_DEFAUT);

    useEffect(() => {
        const gardee = lireLangueGardee();
        if (gardee) setLangue(gardee);
    }, []);

    useEffect(() => {
        document.documentElement.lang = langue;
    }, [langue]);

    const choisir = useCallback((nouvelle: Langue) => {
        setLangue(nouvelle);
        garderLangue(nouvelle);
    }, []);

    const valeur = useMemo(() => ({ langue, choisir, t: traduire(langue) }), [langue, choisir]);

    return (
        <ContexteLangue.Provider value={valeur}>
            <TraductionDograh langue={langue} />
            {children}
        </ContexteLangue.Provider>
    );
};

export const useLangue = () => useContext(ContexteLangue);
