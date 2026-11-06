/**
 * [.mark] builder-agent-vocal (lot 6): the shapes the « Tests and corrections » page reads from `/builder/tests`.
 * The routes answer plain objects (their schemas are written here, once).
 */

export type StatutDeTest = "ok" | "echec" | "erreur";

export interface ResumeDeTest {
    slug: string;
    nom: string;
    obligatoire: boolean;
    dossier: string;
    origine: string | null;
    genre: "conversation" | "replique";
    avec_environnement?: boolean;
    description?: string;
    modifie_le?: string | null;
    criteres: number;
    derniere: null | { le: string; version: number | null; statut: StatutDeTest; reussis: number; total: number };
}

export interface CritereResultat {
    critere: Record<string, unknown> & { type: string };
    reussi: boolean;
    detail: string;
    /** B40: the agent's reply at fault (from 0). */
    rang: number | null;
    raison: string | null;
}

export interface EssaiResultat {
    numero: number;
    reussi: boolean;
    erreur?: string;
    criteres: CritereResultat[];
    lignes: [string, string][];
    run_id?: number | null;
}

export interface AvisDuJuge {
    question: string;
    ok: boolean | null;
    serre: boolean;
    passes: number;
    raison: string;
}

export interface Execution {
    le: string;
    version: number | null;
    statut: StatutDeTest;
    reussis: number;
    total: number;
    essais: EssaiResultat[];
    juge: { bloquant: false; avis: AvisDuJuge[]; erreur?: string } | null;
}

export interface TestComplet {
    slug: string;
    nom: string;
    description?: string;
    obligatoire: boolean;
    dossier: string;
    origine: string | null;
    criteres: Array<Record<string, unknown> & { type: string }>;
    replique?: string;
    historique?: Array<{ role: string; texte: string }>;
    scenario?: { but: string; personnage?: string | null; ouverture?: string; tours_max?: number | null };
    source?: Record<string, unknown>;
    /** What the test fixes around the conversation (sub-lot 5), as the server keeps it. */
    environnement?: EnvironnementServeur;
}

/** The environment of a test as the server keeps it (`tests_rejouables/environnement.py`). */
export interface EnvironnementServeur {
    date?: string;
    heure?: string;
    numero?: string;
    masque?: boolean;
    variables?: Record<string, string>;
    simulations?: Array<{ outil: string; appels: Array<{ sorte: SorteDeReponse; corps: unknown }> }>;
}

export type SorteDeReponse = "reponse" | "erreur" | "delai" | "refus";

export interface Diagnostic {
    cause: "agent" | "test" | "execution";
    raison: string;
    accord_requis: boolean;
}

export interface EchecDeSuite {
    test: string;
    nom: string;
    obligatoire: boolean;
    essai: number;
    critere: (Record<string, unknown> & { type: string }) | null;
    raison: string;
    rang: number | null;
    replique: string | null;
    diagnostic: Diagnostic;
}

export interface ResultatDeSuite {
    ok: boolean;
    total: number;
    reussis?: number;
    echecs: EchecDeSuite[];
    elements?: Array<{ statut: string; message: string; test?: string }>;
    refus?: boolean;
    partiel?: boolean;
    suite_complete?: boolean;
    disponible?: boolean;
    message?: string;
}

export interface ErreurDeControle {
    code: string;
    gravite: "bloquant" | "avertissement";
    message: string;
    etape: string | null;
    extrait: string | null;
}

export interface EtatDePublication {
    brouillon: boolean;
    version?: number;
    suivi?: boolean;
    bloque: boolean;
    controle: null | { ok: boolean; bloquants: ErreurDeControle[]; avertissements: ErreurDeControle[] };
    tests_obligatoires: Array<{ slug: string; nom: string; raison: string }>;
}

export interface Correction {
    id: string;
    le: string;
    version: number | null;
    vert: boolean;
    resume: string;
    restaure_de: string | null;
    retour_possible: boolean;
}

export interface AgentDeRecette {
    organisation: number;
    agent: number;
    version: number | null;
    a_jour: boolean;
}

/** What the test window reads from the agent and the library (`/builder/tests/<agent>/ressources`): no list is written in the screen. */
export interface RessourcesDeTest {
    etapes: string[];
    outils: string[];
    issues: string[];
    champs: string[];
    personnages: Array<{ slug: string; titre: string }>;
    scenarios_types: Array<{ slug: string; titre: string; statut: string }>;
}

/** A kept run of any test (`/builder/tests/<agent>/executions`). */
export interface ExecutionPassee {
    test: string;
    nom: string;
    obligatoire: boolean;
    le: string;
    version: number | null;
    statut: StatutDeTest;
    reussis: number;
    total: number;
}

/** What a typical scenario cites that the agent lacks (`.../scenarios-types/<slug>/examiner`). */
export interface BilanDeScenario {
    copie?: boolean;
    titre: string;
    but: string | null;
    personnage_absent: boolean;
    absents: Array<{ critere: number; type: string; manque: string; sorte: string }>;
}

/** The three kinds of the test window (E47). A tool-call test is a one-reply test whose criterion is a tool. */
export type SorteDeTest = "conversation" | "replique" | "outil";

export const sorteDuTest = (t: { scenario?: unknown; criteres: Array<{ type: string }> }): SorteDeTest =>
    t.scenario ? "conversation" : t.criteres.length > 0 && t.criteres.every((c) => c.type === "outil") ? "outil" : "replique";
