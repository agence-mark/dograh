import type { EtapeDePreparation } from "@/client/types.gen";

/** [.mark] U11 : les formes rendues par `/builder/publication` et `/builder/attaques` (voir `api/services/publication`, `attaques`). */

export type PositionControle = "eteint" | "previent" | "bloque";
export type StatutControle = "ok" | "alerte" | "echec" | "eteint";
export type CleControle =
    | "tests_obligatoires"
    | "bilan_du_prompt"
    | "liste_vocale"
    | "attaques"
    | "garde_fous"
    | "variables"
    | "briques"
    | "outils"
    | "sans_effet"
    | "sortie_d_impasse"
    | "deux_webhooks"
    | "annonce_ia";

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
    /** [.mark] Partie 3 (SA-L3a) : « Prêt à publier », la même liste que la carte des Réglages (`GET /workflow/{id}/preparation`). */
    lignes?: EtapeDePreparation[];
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

export type ClasseDAttaque = "a_tenu" | "a_cede" | "plausible" | "non_teste";
export type EtatDuTemoin = "normal" | "anormal" | "sans" | "non_juge";

export interface LigneDAttaque {
    id: string;
    technique: string | null;
    famille: string | null;
    /** `catalogue` (les 15 techniques), `conflit` (deux règles de l'agent qui se touchent) ou `public` (le jeu importé). */
    origine?: string | null;
    attaque: string;
    classe: ClasseDAttaque;
    temoin: EtatDuTemoin;
}

export interface RapportDAttaque {
    version: number | null;
    le: string;
    contrat: { profondeur: string; essais?: number | null; temoin?: boolean; jeu?: string; repetitions?: number };
    configuration: { regles: number; conflits: number };
    resume: { jouees: number; a_tenu: number; a_cede: number; plausibles: number; non_testees: number; non_couvertes: number; temoins_anormaux?: number };
    /** Sous-lot 4 : le jeu joué et le contrôle du juge (`ok` faux = il a vu une attaque dans une demande normale ; `null` = rien à conclure). */
    jeu?: { slug: string; mention?: string | null };
    controle_du_juge?: { ok: boolean | null; raison: string } | null;
    /** Une ligne par attaque jouée (l'onglet « Dernier rapport »). */
    lignes?: LigneDAttaque[];
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

/** [.mark] Partie 3, sous-lot 3 (D-4) : ce que rend `/builder/publication/{agent}/changements` (voir `api/services/publication/changements.py`). */
export type GenreDeChangement = "node_added" | "node_changed" | "node_removed" | "link_added" | "link_changed" | "link_removed" | "setting_changed";

export interface LigneDeChangement {
    genre: GenreDeChangement;
    ou: string;
    champ: string | null;
    avant: string;
    apres: string;
}

export interface VueDesChangements {
    version_brouillon: number | null;
    version_publiee: number | null;
    publiee_le: string | null;
    lignes: LigneDeChangement[];
    total: number;
}
