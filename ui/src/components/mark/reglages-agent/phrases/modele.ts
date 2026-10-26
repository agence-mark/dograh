/**
 * [.mark] correctifs-apres-banc-v4, lot 5 : le modèle du thème Phrases, sans écran.
 *
 * Une règle de phrase (`ReglePhrase`, miroir de `api/schemas/phrases_du_code.py`) se lit comme une phrase :
 * « Dans [OÙ], quand [MOTIF] [pour l'outil …], le code dit [PHRASES] au bout de [DÉLAI], puis la redit
 * toutes les [INTERVALLE], au plus [N] fois par attente et [M] fois dans l'appel. Ensuite : [SORTIE]. »
 * Ce fichier porte le catalogue des motifs (copie de `api/services/phrases/catalogue.py`, comparée par un
 * test), les règles d'identité, ce que l'enregistrement envoie, les erreurs qui bloquent (plan 4.7), les
 * puces d'une carte et l'aperçu seconde par seconde. Aucun mot de métier : les textes sont des données.
 */
import type { ReglePhrase, SortiePhrase } from "@/types/workflow-configurations";

import type { Langue, Texte } from "../../langue/langue";
import CATALOGUE from "./catalogue-des-phrases.json";

export type Moment = "attente" | "probleme" | "action";
export type Action = "continuer" | "modele" | "transferer" | "raccrocher" | "rendre_la_main" | "aller_a_une_etape";

export interface MotifDePhrase {
    id: string;
    famille: "attente" | "annonce";
    moment: Moment;
    libelle: Texte;
    quand: Texte;
    a_un_delai: boolean;
    delai_min_s: number;
    peut_redire: boolean;
    filtre_outil: boolean;
    texte_de_l_agent: boolean;
    sorties_permises: Action[];
    sortie_defaut: Action;
    fin_d_attente: Texte;
    fin_d_attente_reglage: "outil" | "travail" | "garde" | "rythme" | null;
    variantes_defaut: string[];
    delai_defaut_s: number | null;
    actif_par_defaut: boolean;
    eteinte: Texte;
    silence_de_l_appelant: boolean;
    sortie_par_le_code: boolean;
}

export const MOTIFS_DE_PHRASES = CATALOGUE.motifs as unknown as MotifDePhrase[];
export const BORNES_PHRASES = CATALOGUE.bornes;
export const MOMENTS: Moment[] = ["attente", "probleme", "action"];

export const MOTIF_SILENCE = "appelant_se_tait";
export const MOTIF_PASSATION = "passation_tarde";
export const MOTIF_MISE_EN_RELATION = "mise_en_relation";
export const MOTIF_TRAVAIL_DURE = "travail_dure";
/** Les anciens identifiants, lus comme les nouveaux (le serveur fait de même). */
export const ALIAS_DE_MOTIFS: Record<string, string> = { connecteur_echoue: "outil_echoue" };

export const motifDe = (id: string): MotifDePhrase | undefined => MOTIFS_DE_PHRASES.find((m) => m.id === (ALIAS_DE_MOTIFS[id] ?? id));

/** Une étape du graphe : son identifiant de nœud (la clé d'une règle) et son nom affiché. */
export interface EtapeGraphe {
    id: string;
    nom: string;
}

export type Origine = "etape" | "agent" | "groupe" | "defaut" | "heritee";

// ---------------------------------------------------------------- identité et normalisation

const PROPRE = (texte: string) => texte.trim().replace(/\s+/g, " ");

/** L'unicité côté serveur : (motif, portée, étape, outils). */
export const cleDeRegle = (r: ReglePhrase): string =>
    [r.motif, r.portee ?? "agent", r.portee === "etape" ? (r.etape_id || r.etape || "") : "", [...(r.outils ?? [])].sort().join(",")].join("|");

/** L'étape du graphe que vise une règle (par l'identifiant, sinon par le nom d'une règle d'avant). */
export const etapeDeLaRegle = (r: ReglePhrase, etapes: EtapeGraphe[]): EtapeGraphe | undefined =>
    r.portee !== "etape" ? undefined : (r.etape_id ? etapes.find((e) => e.id === r.etape_id) : undefined) ?? (r.etape ? etapes.find((e) => e.nom === r.etape) : undefined);

/** Étape supprimée : la règle n'a plus d'effet (l'appel l'ignore). Sans graphe lu, on ne le déclare pas. */
export const etapeSupprimee = (r: ReglePhrase, etapes: EtapeGraphe[]): boolean =>
    r.portee === "etape" && etapes.length > 0 && etapeDeLaRegle(r, etapes) === undefined;

/** La règle avec toutes ses cases (les défauts sont le comportement d'avant), l'ancien motif lu comme le nouveau. */
export const normaliserRegle = (r: ReglePhrase): ReglePhrase => ({
    ...r,
    motif: ALIAS_DE_MOTIFS[r.motif] ?? r.motif,
    portee: r.portee ?? "agent",
    etape: r.etape ?? null,
    etape_id: r.etape_id ?? null,
    outils: [...(r.outils ?? [])],
    variantes: [...(r.variantes ?? [])],
    ordre: r.ordre ?? "tournees",
    delai_s: r.delai_s ?? null,
    redite_s: r.redite_s ?? null,
    max_par_attente: r.max_par_attente ?? null,
    max_par_appel: r.max_par_appel ?? null,
    ensuite: {
        phrases: [...(r.ensuite?.phrases ?? [])],
        noter: r.ensuite?.noter ?? null,
        action: r.ensuite?.action ?? null,
        destination: r.ensuite?.destination ?? null,
    },
    texte_de_l_agent: r.texte_de_l_agent ?? false,
    active: r.active ?? true,
});

/** Ce que l'enregistrement envoie pour une règle : les cases que le motif permet, nettoyées. */
export const chargeRegle = (brute: ReglePhrase, etapes: EtapeGraphe[] = []): ReglePhrase => {
    const r = normaliserRegle(brute);
    const motif = motifDe(r.motif);
    const variantes = [...new Set((r.variantes ?? []).map(PROPRE).filter((v) => v !== ""))];
    let etape = r.etape ?? null;
    let etapeId = r.etape_id ?? null;
    if (r.portee === "etape") {
        // Une règle d'avant, repérée par le nom seul, prend l'identifiant du nœud au premier enregistrement.
        const trouvee = etapeDeLaRegle(r, etapes);
        if (trouvee) {
            etape = trouvee.nom;
            etapeId = trouvee.id;
        }
    } else {
        etape = null;
        etapeId = null;
    }
    const action = r.ensuite?.action ?? null;
    const actionPermise = action !== null && (!motif || motif.sorties_permises.includes(action)) ? action : null;
    const phrasesDeSortie = [...new Set((r.ensuite?.phrases ?? []).map(PROPRE).filter((v) => v !== ""))];
    const noter = r.ensuite?.noter ? { champ: PROPRE(r.ensuite.noter.champ), valeur: PROPRE(r.ensuite.noter.valeur) } : null;
    return {
        motif: r.motif,
        portee: r.portee,
        etape,
        etape_id: etapeId,
        outils: !motif || motif.filtre_outil ? [...new Set((r.outils ?? []).map(PROPRE).filter((v) => v !== ""))] : [],
        variantes,
        ordre: r.ordre,
        delai_s: !motif || motif.a_un_delai ? (r.delai_s ?? null) : null,
        redite_s: !motif || motif.peut_redire ? (r.redite_s ?? null) : null,
        max_par_attente: !motif || motif.peut_redire ? (r.max_par_attente ?? null) : null,
        max_par_appel: r.max_par_appel ?? null,
        ensuite: {
            phrases: phrasesDeSortie,
            noter: noter && (noter.champ || noter.valeur) ? noter : null,
            action: actionPermise,
            destination: actionPermise === "transferer" || actionPermise === "aller_a_une_etape" ? (PROPRE(r.ensuite?.destination ?? "") || null) : null,
        },
        texte_de_l_agent: !motif || motif.texte_de_l_agent ? r.texte_de_l_agent === true : false,
        active: r.active !== false,
    };
};

export interface Endroit {
    portee: "groupe" | "agent" | "etape";
    etape?: EtapeGraphe | null;
}

/** Une règle neuve, avec les valeurs du catalogue (celles que l'étape 2 de « Ajouter » propose). */
export const regleNeuve = (motif: MotifDePhrase, endroit: Endroit): ReglePhrase => ({
    ...normaliserRegle({ motif: motif.id }),
    portee: endroit.portee,
    etape: endroit.portee === "etape" ? (endroit.etape?.nom ?? null) : null,
    etape_id: endroit.portee === "etape" ? (endroit.etape?.id ?? null) : null,
    variantes: [...motif.variantes_defaut],
    delai_s: motif.a_un_delai ? motif.delai_defaut_s : null,
    active: true,
});

/** La valeur de la case « Dans » : `groupe`, `agent` ou `etape:<identifiant>`. */
export const valeurEndroit = (r: ReglePhrase, etapes: EtapeGraphe[]): string => {
    if (r.portee !== "etape") return r.portee ?? "agent";
    const e = etapeDeLaRegle(r, etapes);
    return `etape:${e?.id ?? r.etape_id ?? r.etape ?? ""}`;
};

export const appliquerEndroit = (r: ReglePhrase, valeur: string, etapes: EtapeGraphe[]): ReglePhrase => {
    if (valeur === "groupe" || valeur === "agent") return { ...r, portee: valeur, etape: null, etape_id: null };
    const id = valeur.slice("etape:".length);
    const e = etapes.find((x) => x.id === id);
    return { ...r, portee: "etape", etape: e?.nom ?? r.etape ?? id, etape_id: e?.id ?? id };
};

// ---------------------------------------------------------------- erreurs qui bloquent (plan 4.7)

export interface ErreurPhrase {
    cle: string;
    libelle: Texte;
    message: Texte;
}

const sansLibelle = (id: string): Texte => motifDe(id)?.libelle ?? { en: id, fr: id };
const dansBornes = (n: number | null | undefined, min: number, max: number) => n === null || n === undefined || (Number.isFinite(n) && n >= min && n <= max);

/** Les erreurs d'UNE règle (la modale les montre ; l'enregistrement du thème les nomme toutes). */
export const erreursDeLaRegle = (brute: ReglePhrase, etapes: EtapeGraphe[]): Texte[] => {
    const r = chargeRegle(brute, etapes);
    const motif = motifDe(r.motif);
    const erreurs: Texte[] = [];
    if (r.portee === "etape" && !(r.etape_id || r.etape)) erreurs.push({ en: "Choose the step.", fr: "Choisissez l'étape." });
    if (r.active && (r.variantes?.length ?? 0) === 0 && !(r.texte_de_l_agent && motif?.texte_de_l_agent)) {
        erreurs.push({ en: "An active rule needs a sentence.", fr: "Une règle activée demande une phrase." });
    }
    if ((r.variantes ?? []).some((v) => v.length > BORNES_PHRASES.longueur_max) || (r.ensuite?.phrases ?? []).some((v) => v.length > BORNES_PHRASES.longueur_max)) {
        erreurs.push({
            en: `At most ${BORNES_PHRASES.longueur_max} characters.`,
            fr: `Au plus ${BORNES_PHRASES.longueur_max} caractères.`,
        });
    }
    const borneBas = Math.max(BORNES_PHRASES.delai_min_s, motif?.delai_min_s ?? 0);
    if (!dansBornes(brute.delai_s === undefined ? null : brute.delai_s, borneBas, BORNES_PHRASES.delai_max_s) || (brute.delai_s !== null && brute.delai_s !== undefined && Number.isNaN(brute.delai_s))) {
        erreurs.push({
            en: `Delay between ${borneBas} and ${BORNES_PHRASES.delai_max_s} s.`,
            fr: `Délai entre ${borneBas} et ${BORNES_PHRASES.delai_max_s} s.`,
        });
    }
    if (!dansBornes(brute.redite_s, BORNES_PHRASES.redite_min_s, BORNES_PHRASES.redite_max_s)) {
        erreurs.push({
            en: `Repeat every ${BORNES_PHRASES.redite_min_s} to ${BORNES_PHRASES.redite_max_s} s.`,
            fr: `Redite toutes les ${BORNES_PHRASES.redite_min_s} à ${BORNES_PHRASES.redite_max_s} s.`,
        });
    }
    if (!dansBornes(brute.max_par_attente, 1, BORNES_PHRASES.max_par_attente)) {
        erreurs.push({ en: `At most 1 to ${BORNES_PHRASES.max_par_attente} times per wait.`, fr: `Au plus 1 à ${BORNES_PHRASES.max_par_attente} fois par attente.` });
    }
    if (!dansBornes(brute.max_par_appel, 1, BORNES_PHRASES.max_par_appel)) {
        erreurs.push({ en: `At most 1 to ${BORNES_PHRASES.max_par_appel} times in the call.`, fr: `Au plus 1 à ${BORNES_PHRASES.max_par_appel} fois dans l'appel.` });
    }
    const note = brute.ensuite?.noter;
    if (note && (PROPRE(note.champ) === "") !== (PROPRE(note.valeur) === "")) {
        erreurs.push({ en: "A note needs a record field and a value.", fr: "Une note demande un champ de la fiche et une valeur." });
    }
    const action = brute.ensuite?.action ?? null;
    if (action !== null && motif && !motif.sorties_permises.includes(action)) {
        erreurs.push({ en: "This exit is not allowed for this cause.", fr: "Cette sortie n'est pas permise pour ce motif." });
    }
    if (action === "transferer" && !PROPRE(brute.ensuite?.destination ?? "")) {
        erreurs.push({ en: "A transfer needs its destination.", fr: "Un transfert demande sa destination." });
    }
    return erreurs;
};

/** Les erreurs de toutes les règles, nommées ; deux règles de même (motif, portée, étape, outils) sont refusées (F23). */
export const erreursDesPhrases = (regles: ReglePhrase[], etapes: EtapeGraphe[] = []): ErreurPhrase[] => {
    const erreurs: ErreurPhrase[] = [];
    if (regles.length > BORNES_PHRASES.regles_max) {
        erreurs.push({
            cle: "phrases_regles",
            libelle: { en: "Phrases", fr: "Phrases" },
            message: { en: `At most ${BORNES_PHRASES.regles_max} rules.`, fr: `Au plus ${BORNES_PHRASES.regles_max} règles.` },
        });
    }
    const vues = new Set<string>();
    regles.forEach((regle, i) => {
        const cle = `phrases_regles.${i}`;
        const libelle = sansLibelle(ALIAS_DE_MOTIFS[regle.motif] ?? regle.motif);
        const identite = cleDeRegle(chargeRegle(regle, etapes));
        if (vues.has(identite)) {
            erreurs.push({ cle, libelle, message: { en: "Two rules of this cause at the same place.", fr: "Deux règles de ce motif au même endroit." } });
        }
        vues.add(identite);
        for (const message of erreursDeLaRegle(regle, etapes)) erreurs.push({ cle, libelle, message });
    });
    return erreurs;
};

// ---------------------------------------------------------------- contexte de lecture

/** Ce que les règles lisent ailleurs : la pause, les délais de fin d'attente, les réglages de Rythme. */
export interface ContextePhrases {
    langue: Langue;
    t: (texte: Texte) => string;
    reposS: number;
    /** Où l'attente s'arrête, par motif (secondes) ; absent : inconnu. */
    abandonS: { outil: number | null; travail: number; garde: number | null };
    rythme: { delaiS: number; relances: number };
    /** Les noms de l'équipe par clé, pour « transférer à ». */
    destinations: Record<string, string>;
    /** Les noms des étapes du graphe par identifiant, pour « aller à une étape » (revue du 26/10). */
    nomsDesEtapes?: Record<string, string>;
}

export const REPOS_DEFAUT_S = BORNES_PHRASES.repos_defaut_s;

const nombreCourt = (n: number) => (Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10).replace(".", ","));

export const ordinal = (n: number, langue: Langue): string => {
    if (langue === "fr") return n === 1 ? "1ʳᵉ" : `${n}ᵉ`;
    const reste = n % 100;
    if (reste >= 11 && reste <= 13) return `${n}th`;
    return `${n}${["th", "st", "nd", "rd"][n % 10] ?? "th"}`;
};

const guillemets = (texte: string) => `« ${texte} »`;

const NOMS_ACTIONS: Record<Action, Texte> = {
    continuer: { en: "Continue", fr: "Continuer" },
    modele: { en: "The model takes over", fr: "Le modèle reprend" },
    transferer: { en: "Transfer to", fr: "Transférer à" },
    raccrocher: { en: "Hang up", fr: "Raccrocher" },
    rendre_la_main: { en: "Give the call back to the front desk", fr: "Rendre la main à l'accueil" },
    aller_a_une_etape: { en: "Go to a step of the main agent", fr: "Aller à une étape de l'agent principal" },
};
export const nomDeLAction = (a: Action): Texte => NOMS_ACTIONS[a];

/** L'action effective d'une règle : celle qu'elle pose, sinon celle du motif (le comportement d'avant). */
export const actionEffective = (r: ReglePhrase, motif: MotifDePhrase): Action => (r.ensuite?.action ?? motif.sortie_defaut) as Action;

/** « Ensuite » en clair : dire, noter, puis l'action ; vide : le comportement d'avant du motif. */
export const texteEnsuite = (r: ReglePhrase, motif: MotifDePhrase, c: ContextePhrases): string | null => {
    const e: SortiePhrase = r.ensuite ?? {};
    const parts: string[] = [];
    if (e.phrases && e.phrases.length > 0) parts.push(`${c.t({ en: "say", fr: "dire" })} ${e.phrases.map(guillemets).join(" / ")}`);
    if (e.noter) parts.push(`${c.t({ en: "note", fr: "noter" })} ${e.noter.champ} = ${e.noter.valeur}`);
    if (e.action) {
        const nom = c.t(NOMS_ACTIONS[e.action]).toLowerCase();
        parts.push(
            e.action === "transferer"
                ? `${nom} ${c.destinations[e.destination ?? ""] ?? e.destination ?? ""}`
                : e.action === "aller_a_une_etape" && e.destination
                  ? `${nom} : ${c.nomsDesEtapes?.[e.destination] ?? e.destination}`
                  : nom,
        );
    }
    if (parts.length === 0) return null;
    void motif;
    return parts.join(" · ");
};

// ---------------------------------------------------------------- l'aperçu seconde par seconde

export interface LigneApercu {
    quand: string;
    texte: string;
    /** Une sortie ou une fin d'attente (grisée). */
    sortie?: boolean;
    /** Ne partira jamais (après la fin de l'attente). */
    jamais?: boolean;
}

export interface ApercuRegle {
    lignes: LigneApercu[];
    alertes: string[];
    eteinte: string;
}

const phraseNumero = (r: ReglePhrase, rang: number): string => {
    const v = r.variantes ?? [];
    if (v.length === 0) return "";
    return r.ordre === "dans_l_ordre" ? v[Math.min(rang, v.length - 1)] : v[rang % v.length];
};

const texteDeSortie = (r: ReglePhrase, motif: MotifDePhrase, c: ContextePhrases): string => {
    const e = r.ensuite ?? {};
    const parts: string[] = [];
    if (e.phrases && e.phrases.length > 0) parts.push(guillemets(e.phrases[0]));
    if (e.noter) parts.push(`${c.t({ en: "record", fr: "fiche" })} : ${e.noter.champ} = ${e.noter.valeur}`);
    const action = actionEffective(r, motif);
    if (action === "raccrocher") parts.push(c.t({ en: "the call hangs up", fr: "l'appel raccroche" }));
    else if (action === "transferer") parts.push(`${c.t({ en: "transfer to", fr: "transfert vers" })} ${c.destinations[e.destination ?? ""] ?? e.destination ?? "?"}`);
    else if (action === "modele") parts.push(c.t({ en: "the model takes over", fr: "le modèle reprend" }));
    else if (action === "rendre_la_main" || (action === "aller_a_une_etape" && !e.destination))
        parts.push(c.t({ en: "the call goes back to the front desk", fr: "la main revient à l'accueil" }));
    else if (action === "aller_a_une_etape")
        parts.push(
            `${c.t({ en: "the code moves to the step", fr: "le code passe à l'étape" })} ${c.nomsDesEtapes?.[e.destination ?? ""] ?? e.destination}`,
        );
    return parts.join(" · ");
};

/**
 * Ce que vit l'appelant, seconde par seconde, pour cette règle. Les incohérences sortent en `alertes`
 * (orange, sans bloquer). `reposS` est la pause minimale entre deux phrases d'attente.
 */
export const apercuDeLaRegle = (brute: ReglePhrase, c: ContextePhrases, hors: { existeUneRegleDuGroupe?: boolean } = {}): ApercuRegle => {
    const r = normaliserRegle(brute);
    const motif = motifDe(r.motif);
    const alertes: string[] = [];
    if (!motif) return { lignes: [], alertes, eteinte: "" };
    const lignes: LigneApercu[] = [];
    const sec = (n: number) => `${nombreCourt(n)} s`;
    const sortie = texteDeSortie(r, motif, c);
    const texteAgent = r.texte_de_l_agent && motif.texte_de_l_agent;
    const premiere = (rang: number) =>
        rang === 0 && texteAgent
            ? `${r.variantes?.length ? guillemets(phraseNumero(r, 0)) : ""} ${c.t({ en: "(or the sentence the agent writes)", fr: "(ou la phrase écrite par l'agent)" })}`.trim()
            : guillemets(phraseNumero(r, rang));

    if (hors.existeUneRegleDuGroupe) {
        alertes.push(c.t({ en: "A group rule already exists for this cause: this one replaces it in this agent.", fr: "Une règle du groupe existe déjà pour ce motif : celle-ci la remplace dans cet agent." }));
    }

    if (motif.moment === "attente" && motif.id === MOTIF_SILENCE) {
        const delai = r.delai_s ?? motif.delai_defaut_s ?? c.rythme.delaiS;
        const redite = r.redite_s ?? delai;
        const n = r.max_par_attente ?? c.rythme.relances;
        let t = delai;
        for (let i = 0; i < n; i++) {
            lignes.push({ quand: sec(t), texte: premiere(i) });
            t += redite;
        }
        const fin = texteDeSortie(r, motif, c);
        // La sortie « continuer » ne coupe jamais la ligne (revue m7) : avertissement, sans bloquer.
        if (actionEffective(r, motif) === "continuer") {
            alertes.push(
                c.t({
                    en: "The line stays open as long as the caller does not speak, up to the maximum call duration.",
                    fr: "La ligne reste ouverte tant que l'appelant ne parle pas, jusqu'à la durée maximale de l'appel.",
                }),
            );
        }
        lignes.push({ quand: sec(t), texte: fin || c.t({ en: "the call hangs up", fr: "l'appel raccroche" }), sortie: true });
    } else if (motif.moment === "attente") {
        const abandon = motif.id === MOTIF_TRAVAIL_DURE ? c.abandonS.travail : motif.fin_d_attente_reglage === "outil" ? c.abandonS.outil : null;
        const nomFin =
            motif.fin_d_attente_reglage === "outil"
                ? c.t({ en: "the tool gives up", fr: "l'outil abandonne" })
                : c.t({ en: "the job gives up", fr: "le travail abandonne" });
        if (!motif.a_un_delai) {
            // « Le modèle tarde » : une fois, au délai de la garde.
            const garde = c.abandonS.garde;
            lignes.push({ quand: garde === null ? c.t({ en: "guard", fr: "garde" }) : sec(garde), texte: `${premiere(0)} ${c.t({ en: "then a second try", fr: "puis seconde tentative" })}` });
            lignes.push({ quand: "", texte: c.t({ en: "no answer: outage mode (set in Outage)", fr: "pas de réponse : mode panne (réglé dans Panne)" }), sortie: true });
        } else {
            const delai = r.delai_s ?? motif.delai_defaut_s ?? 0;
            const n = motif.peut_redire ? (r.max_par_attente ?? 1) : 1;
            const redite = r.redite_s;
            if (redite !== null && redite !== undefined && redite < c.reposS) {
                alertes.push(
                    c.t({
                        en: `Repeat every ${nombreCourt(redite)} s: shorter than the minimum pause (${nombreCourt(c.reposS)} s), it will go every ${nombreCourt(c.reposS)} s.`,
                        fr: `Redite toutes les ${nombreCourt(redite)} s : plus court que la pause minimale (${nombreCourt(c.reposS)} s), elle partira toutes les ${nombreCourt(c.reposS)} s.`,
                    }),
                );
            }
            const pas = redite === null || redite === undefined ? null : Math.max(redite, c.reposS);
            let t = delai;
            const premiereRediteImpossible: number[] = [];
            for (let i = 0; i < n; i++) {
                const jamais = abandon !== null && t >= abandon;
                const dernier = i === n - 1 && n > 1;
                const base = i === 0 ? premiere(0) : guillemets(phraseNumero(r, i));
                const suffixe = i > 0 && dernier ? ` (${c.t({ en: `repeat ${i}, last`, fr: `redite ${i}, dernière` })})` : "";
                lignes.push({ quand: sec(t), texte: `${base}${suffixe}`, jamais });
                if (jamais) premiereRediteImpossible.push(i);
                if (pas === null) break;
                t += pas;
            }
            if (premiereRediteImpossible.length > 0) {
                const i = premiereRediteImpossible[0];
                alertes.push(
                    i === 0
                        ? c.t({
                              en: `The sentence will never be said: ${nomFin} at ${sec(abandon ?? 0)}.`,
                              fr: `La phrase ne partira jamais : ${nomFin} à ${sec(abandon ?? 0)}.`,
                          })
                        : c.t({
                              en: `The ${ordinal(i, "en")} repeat will never go: ${nomFin} at ${sec(abandon ?? 0)}.`,
                              fr: `La ${ordinal(i, "fr")} redite n'arrivera jamais : ${nomFin} à ${sec(abandon ?? 0)}.`,
                          }),
                );
            }
            if (abandon !== null) {
                lignes.push({
                    quand: sec(abandon),
                    texte: `${nomFin} → ${c.t(motif.id === MOTIF_TRAVAIL_DURE ? { en: 'rule "the background work fails"', fr: 'règle « le travail de fond échoue »' } : { en: 'rule "a tool fails"', fr: 'règle « un outil échoue »' })}`,
                    sortie: true,
                });
            }
        }
    } else if (motif.moment === "probleme") {
        const m = r.max_par_appel;
        const avant = c.t(NOMS_ACTIONS[motif.sortie_defaut]).toLowerCase();
        const dit = r.variantes?.length ? guillemets(phraseNumero(r, 0)) : c.t({ en: "(nothing said)", fr: "(rien n'est dit)" });
        if (m !== null && m !== undefined && m > 1) {
            lignes.push({ quand: m === 2 ? `1 ${c.t({ en: "failure", fr: "échec" })}` : `1–${m - 1}`, texte: `${dit} ${c.t({ en: "then", fr: "puis" })} ${avant}` });
            lignes.push({ quand: `${ordinal(m, c.langue)}`, texte: `${dit}${sortie ? ` · ${sortie}` : ""}`, sortie: true });
        } else {
            lignes.push({ quand: c.t({ en: "each failure", fr: "chaque échec" }), texte: `${dit}${sortie ? ` · ${sortie}` : ` ${c.t({ en: "then", fr: "puis" })} ${avant}`}`, sortie: Boolean(sortie) });
        }
        if (r.ensuite?.action === "transferer") {
            alertes.push(c.t({ en: "Business closed: the closed-business rule applies to the transfer.", fr: "Entreprise fermée : la règle de l'entreprise fermée s'applique au transfert." }));
        }
    } else {
        lignes.push({ quand: c.t({ en: "before", fr: "avant" }), texte: `${premiere(0)} ${c.t({ en: "then the transfer starts", fr: "puis le transfert part" })}` });
    }
    return { lignes, alertes, eteinte: c.t(motif.eteinte) };
};

// ---------------------------------------------------------------- les puces d'une carte

export interface Puce {
    icone: "horloge" | "redite" | "sortie" | "fin" | "fait";
    texte: string;
    discret?: boolean;
}

/** Le résumé d'une règle en puces : quand, redites, plafond, sortie, fin d'attente lue ailleurs. */
export const puces = (brute: ReglePhrase, c: ContextePhrases): Puce[] => {
    const r = normaliserRegle(brute);
    const motif = motifDe(r.motif);
    if (!motif) return [];
    const liste: Puce[] = [];
    const sec = (n: number) => `${nombreCourt(n)} s`;
    if (motif.moment === "attente") {
        if (!motif.a_un_delai) liste.push({ icone: "horloge", texte: c.t({ en: "at the model guard's delay", fr: "au délai de la garde du modèle" }) });
        else {
            const delai = r.delai_s ?? motif.delai_defaut_s ?? 0;
            liste.push({
                icone: "horloge",
                texte:
                    motif.id === MOTIF_SILENCE
                        ? c.t({ en: `after ${sec(delai)} of silence`, fr: `au bout de ${sec(delai)} de silence` })
                        : delai === 0
                          ? c.t({ en: "at once", fr: "dès le lancement" })
                          : c.t({ en: `after ${sec(delai)}`, fr: `au bout de ${sec(delai)}` }),
            });
        }
        const n = r.max_par_attente ?? (motif.id === MOTIF_SILENCE ? null : 1);
        if (motif.peut_redire && (r.redite_s || (motif.id === MOTIF_SILENCE && n))) {
            const redite = r.redite_s ?? r.delai_s ?? motif.delai_defaut_s ?? 0;
            liste.push({
                icone: "redite",
                texte: c.t({ en: `every ${sec(redite)}, ${n ?? 1} time(s) in all`, fr: `toutes les ${sec(redite)}, ${n ?? 1} fois en tout` }),
            });
        }
    } else if (motif.moment === "probleme") {
        liste.push({ icone: "fait", texte: c.t({ en: "as soon as it happens", fr: "dès que ça arrive" }) });
        if (r.max_par_appel) liste.push({ icone: "redite", texte: c.t({ en: `exit at the ${ordinal(r.max_par_appel, "en")} in the call`, fr: `sortie au ${ordinal(r.max_par_appel, "fr")} dans l'appel` }) });
    }
    const ensuite = texteEnsuite(r, motif, c);
    if (ensuite) liste.push({ icone: "sortie", texte: `${c.t({ en: "Then:", fr: "Ensuite :" })} ${ensuite}` });
    if (motif.fin_d_attente.fr || motif.fin_d_attente.en) {
        liste.push({ icone: "fin", texte: `${c.t({ en: "End:", fr: "Fin :" })} ${c.t(motif.fin_d_attente)}`, discret: true });
    }
    return liste;
};

/** Où se règle une fin d'attente lue ailleurs : le libellé du lien et sa cible (ouverte dans un autre onglet : la modale garde sa saisie). */
export const LIENS_DE_FIN: Record<"outil" | "travail" | "garde" | "rythme", Texte> = {
    outil: { en: "The tool's screen", fr: "Écran de l'outil" },
    travail: { en: "Background work", fr: "Travail en arrière-plan" },
    garde: { en: "Models → Guard", fr: "Modèles → Garde" },
    rythme: { en: "Call pacing", fr: "Rythme de l'appel" },
};

export const hrefDeFin = (cible: keyof typeof LIENS_DE_FIN, workflowId?: number): string | null => {
    if (cible === "outil") return "/tools";
    if (workflowId === undefined) return null;
    return `/workflow/${workflowId}/settings?theme=${cible === "rythme" ? "rythme" : "briques"}`;
};

/** Le texte de l'origine d'une carte. */
export const ORIGINES: Record<Origine, Texte> = {
    etape: { en: "for this step", fr: "propre à l'étape" },
    agent: { en: "of this agent", fr: "de cet agent" },
    groupe: { en: "of the group", fr: "du groupe" },
    defaut: { en: "default", fr: "défaut" },
    heritee: { en: "inherited from the main agent", fr: "héritée du principal" },
};

export const origineDe = (r: ReglePhrase): Origine => (r.portee === "etape" ? "etape" : r.portee === "groupe" ? "groupe" : "agent");

/** Le nom d'une règle d'avant (repérée par le nom) ou d'un nœud supprimé, pour l'affichage. */
export const nomDeLEtape = (r: ReglePhrase, etapes: EtapeGraphe[]): string => etapeDeLaRegle(r, etapes)?.nom ?? r.etape ?? r.etape_id ?? "";
