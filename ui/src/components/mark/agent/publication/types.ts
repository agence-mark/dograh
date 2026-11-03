/** [.mark] U11 : les formes rendues par `/builder/publication` et `/builder/attaques` (voir `api/services/publication`, `attaques`). */

export type PositionControle = "eteint" | "previent" | "bloque";
export type StatutControle = "ok" | "alerte" | "echec" | "eteint";
export type CleControle = "tests_obligatoires" | "bilan_du_prompt" | "liste_vocale" | "attaques" | "garde_fous";

export interface ControleDePublication {
    cle: CleControle;
    libelle: string;
    position: PositionControle;
    statut: StatutControle;
    problemes: string[];
}

export interface PointDeLaListeVocale {
    id: string;
    libelle: string;
    statut: "ok" | "ecart" | "sans_equivalent";
    raison: string;
    ecarts: Array<{ reglage: string; actuel: unknown; attendu: string }>;
    corrections: Record<string, unknown> | null;
    corrige_seul: boolean;
}

export interface VueDePublication {
    ok?: boolean;
    version: number | null;
    controles: ControleDePublication[];
    bloque: boolean;
    liste_vocale: PointDeLaListeVocale[];
    deploiement_actif: boolean;
    forcable: boolean;
}

export type Gravite = "critique" | "haute" | "moyenne" | "basse";

export interface DefautDAttaque {
    id: string;
    technique: string | null;
    origine: string | null;
    confirme: boolean;
    gravite: Gravite | null;
    couche: "prompt" | "plateforme" | "inconnue" | null;
    raison: string | null;
    reponse: string | null;
}

export interface RapportDAttaque {
    version: number | null;
    le: string;
    contrat: { profondeur: string };
    configuration: { regles: number; conflits: number };
    resume: { jouees: number; a_tenu: number; a_cede: number; plausibles: number; non_testees: number; non_couvertes: number };
    defauts: DefautDAttaque[];
    a_tenu: string[];
    non_testees: Array<{ id: string; raison: string | null }>;
    non_couvert: string[];
    rejeu: null | {
        le: string;
        echecs_rejoues: number;
        echantillon_rejoue: number;
        corriges: string[];
        encore_cedes: string[];
        regressions: string[];
        non_concluants: string[];
    };
}
