"use client";

/**
 * [.mark] Dograh's screens in French, over the top (chantier
 * reorganisation-ecran-reglages, step 8, convention T3 and T4).
 *
 * Dograh's files are never edited to translate. While the language is French,
 * this watches the page and swaps every text that is EXACTLY one of their
 * English texts (`dictionnaire-dograh.json`, keyed by `textes-dograh.ts`) for
 * its French: the text between tags, and the attributes a person reads
 * (placeholder, title, aria-label, alt). Back to English, every swap is undone.
 *
 * ⛔ Never translated (T4), whatever the dictionary says:
 *   - what a person typed: the value of a field is not a text of the page, and
 *     `input`, `textarea`, `[contenteditable]` are left alone;
 *   - code: `code`, `pre`, `kbd`;
 *   - the workflow editor's canvas (`.react-flow`);
 *   - a transcription or a message: Dograh draws them pre-wrapped
 *     (`.whitespace-pre-wrap`), and so does every multi-line content it shows;
 *   - anything under `[data-mark-pas-traduire]`.
 *
 * Its limit, said plainly: the match is on the WHOLE text. A name somebody
 * typed that is displayed on its own, outside those zones, and happens to be
 * exactly one of Dograh's English texts (an agent called « Settings ») is
 * shown in French. The data is never changed; only its display is.
 *
 * How it stays compatible with React: it only ever changes the VALUE of a text
 * node or of an attribute, never the tree, so React keeps finding its nodes.
 * When React writes the English back (a re-render), the watcher sees it and
 * swaps again.
 */
import { useEffect } from "react";

import dictionnaireBrut from "./dictionnaire-dograh.json";

export const ZONES_EXCLUES = [
    "input",
    "textarea",
    "[contenteditable]",
    "code",
    "pre",
    "kbd",
    "script",
    "style",
    ".react-flow",
    ".whitespace-pre-wrap",
    "[data-mark-pas-traduire]",
].join(", ");

export const ATTRIBUTS_TRADUITS = ["placeholder", "title", "aria-label", "alt"] as const;

/** The same normalization as `textes-dograh.ts` (which cannot be imported by the page). */
const normaliser = (texte: string) => texte.replace(/[\s ]+/g, " ").trim();

export type Dictionnaire = Record<string, string>;

const DICTIONNAIRE = dictionnaireBrut as Dictionnaire;

/**
 * The translator on its own, for the page and for the tests. `demarrer` swaps
 * what is there and watches what comes; `arreter` stops and puts the English back.
 */
export const creerTraducteur = (racine: HTMLElement, dictionnaire: Dictionnaire) => {
    // What was there before a swap, and what we wrote, per node.
    const textes = new Map<Text, { anglais: string; ecrit: string }>();
    const attributs = new Map<Element, Map<string, { anglais: string; ecrit: string }>>();
    let observateur: MutationObserver | null = null;

    const exclu = (element: Element | null) => !element || element.closest(ZONES_EXCLUES) !== null;

    const traduction = (valeur: string): string | null => {
        const cle = normaliser(valeur);
        const francais = cle ? dictionnaire[cle] : undefined;
        if (!francais) return null;
        // The spaces around the text are the layout's: they stay.
        const debut = valeur.match(/^[\s ]*/)?.[0] ?? "";
        const fin = valeur.match(/[\s ]*$/)?.[0] ?? "";
        return `${debut}${francais}${fin}`;
    };

    const traduireTexte = (noeud: Text) => {
        const valeur = noeud.nodeValue ?? "";
        const connu = textes.get(noeud);
        if (connu && valeur === connu.ecrit) return;
        if (exclu(noeud.parentElement)) return;
        const francais = traduction(valeur);
        if (francais === null) {
            textes.delete(noeud);
            return;
        }
        textes.set(noeud, { anglais: valeur, ecrit: francais });
        noeud.nodeValue = francais;
    };

    const traduireAttributs = (element: Element) => {
        if (exclu(element.parentElement) && !element.matches("input, textarea")) return;
        if (element.closest(".react-flow, [data-mark-pas-traduire]")) return;
        for (const nom of ATTRIBUTS_TRADUITS) {
            const valeur = element.getAttribute(nom);
            if (valeur === null) continue;
            const deja = attributs.get(element)?.get(nom);
            if (deja && valeur === deja.ecrit) continue;
            const francais = traduction(valeur);
            if (francais === null) continue;
            if (!attributs.has(element)) attributs.set(element, new Map());
            attributs.get(element)!.set(nom, { anglais: valeur, ecrit: francais });
            element.setAttribute(nom, francais);
        }
    };

    const parcourir = (depart: Node) => {
        if (depart.nodeType === Node.TEXT_NODE) {
            traduireTexte(depart as Text);
            return;
        }
        if (depart.nodeType !== Node.ELEMENT_NODE) return;
        const element = depart as Element;
        traduireAttributs(element);
        const marcheur = document.createTreeWalker(element, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
        for (let noeud = marcheur.nextNode(); noeud; noeud = marcheur.nextNode()) {
            if (noeud.nodeType === Node.TEXT_NODE) traduireTexte(noeud as Text);
            else traduireAttributs(noeud as Element);
        }
    };

    const demarrer = () => {
        parcourir(racine);
        observateur = new MutationObserver((mutations) => {
            for (const mutation of mutations) {
                if (mutation.type === "childList") mutation.addedNodes.forEach(parcourir);
                else if (mutation.type === "characterData") traduireTexte(mutation.target as Text);
                else if (mutation.type === "attributes") traduireAttributs(mutation.target as Element);
            }
        });
        observateur.observe(racine, {
            childList: true,
            subtree: true,
            characterData: true,
            attributes: true,
            attributeFilter: [...ATTRIBUTS_TRADUITS],
        });
    };

    const arreter = () => {
        observateur?.disconnect();
        observateur = null;
        for (const [noeud, { anglais, ecrit }] of textes) {
            // React may have written a new text since: only our own is undone.
            if (noeud.nodeValue === ecrit) noeud.nodeValue = anglais;
        }
        for (const [element, parNom] of attributs) {
            for (const [nom, { anglais, ecrit }] of parNom) {
                if (element.getAttribute(nom) === ecrit) element.setAttribute(nom, anglais);
            }
        }
        textes.clear();
        attributs.clear();
    };

    return { demarrer, arreter };
};

/** Mounted once, by the language provider (which hands it the language). */
export const TraductionDograh = ({ langue }: { langue: "fr" | "en" }) => {
    useEffect(() => {
        if (langue !== "fr" || typeof document === "undefined") return;
        const traducteur = creerTraducteur(document.body, DICTIONNAIRE);
        traducteur.demarrer();
        return traducteur.arreter;
    }, [langue]);
    return null;
};
