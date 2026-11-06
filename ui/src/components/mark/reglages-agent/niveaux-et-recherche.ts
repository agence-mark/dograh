/**
 * [.mark] U4 (E38) : les 11 thèmes de l'agent en trois niveaux, la recherche dans tous les réglages, le décompte des
 * réglages propres à l'agent.
 *
 * - Essentiel : Agent, Établissement, Voix, Phrases, Données de l'appel, Sécurité, Qualité (SE-9, A-4) ;
 * - Avancé : Briques, Écoute, Modules, Tour de parole, Rythme de l'appel ;
 * - Moteur : Interventions du moteur, visible au Labo seulement (un client ne règle pas notre code).
 *
 * Rien n'est recopié : les clés viennent de `inventaire-agent.ts` (la preuve qu'aucune clé ne se perd), les libellés de
 * `catalogue.tsx`. Une clé sans libellé au catalogue (réglage composé) se cherche par son nom technique.
 */
import { espaceDeAdresse, espaceRetenu } from "@/lib/espaceCourant";

import type { Texte } from "../langue/langue";
import { CATALOGUE } from "./catalogue";
import { INVENTAIRE_AGENT } from "./inventaire-agent";

export type NiveauReglages = "essentiel" | "avance" | "moteur";

export const NIVEAUX_REGLAGES: Array<{ id: NiveauReglages; titre: Texte; themes: string[]; laboSeulement?: boolean }> = [
    { id: "essentiel", titre: { en: "Essential", fr: "Essentiel" }, themes: ["agent", "etablissement", "voix", "phrases", "donnees", "securite", "qualite"] },
    { id: "avance", titre: { en: "Advanced", fr: "Avancé" }, themes: ["briques", "ecoute", "modules", "tour", "rythme"] },
    { id: "moteur", titre: { en: "Engine", fr: "Moteur" }, themes: ["interventions"], laboSeulement: true },
];

/** Le niveau de chaque thème, dit sur sa carte. */
export const NIVEAU_DU_THEME: Record<string, Texte> = Object.fromEntries(
    NIVEAUX_REGLAGES.flatMap((n) => n.themes.map((t) => [t, n.titre])),
);

/** Vrai quand l'onglet est dans l'espace d'un CLIENT : le niveau Moteur n'y est pas montré. Inconnu : montré (équipe). */
export const dansUnEspaceClient = (pathname: string): boolean => {
    const espace = espaceDeAdresse(pathname) ?? espaceRetenu();
    return typeof espace === "number";
};

/** Les thèmes que l'inventaire range dans chaque thème : `theme -> clés`. */
export const CLES_PAR_THEME: Record<string, string[]> = (() => {
    const par: Record<string, string[]> = {};
    for (const [cle, entree] of Object.entries(INVENTAIRE_AGENT)) {
        if ("horsEcran" in entree) continue;
        (par[entree.theme] ??= []).push(cle);
    }
    return par;
})();

export const propresParTheme = (propre: (cle: string) => boolean): Record<string, number> =>
    Object.fromEntries(Object.entries(CLES_PAR_THEME).map(([theme, cles]) => [theme, cles.filter(propre).length]));

export interface ResultatRecherche {
    cle: string;
    theme: string;
    libelle: Texte | null;
}

const normaliser = (texte: string) =>
    texte
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .toLowerCase();

/** Cherche dans les 130 clés : nom technique ou libellé (les deux langues). `themesVisibles` écarte ceux qu'on ne montre pas. */
export const chercherReglages = (requete: string, themesVisibles: ReadonlySet<string>, max = 30): ResultatRecherche[] => {
    const visee = normaliser(requete.trim());
    if (visee.length < 2) return [];
    const trouves: ResultatRecherche[] = [];
    for (const [theme, cles] of Object.entries(CLES_PAR_THEME)) {
        if (!themesVisibles.has(theme)) continue;
        for (const cle of cles) {
            const definition = (CATALOGUE as Record<string, { libelle?: Texte }>)[cle];
            const libelle = definition?.libelle ?? null;
            const meule = normaliser(`${cle} ${libelle?.fr ?? ""} ${libelle?.en ?? ""}`);
            if (meule.includes(visee)) trouves.push({ cle, theme, libelle });
        }
    }
    return trouves.sort((a, b) => a.cle.localeCompare(b.cle)).slice(0, max);
};
