/**
 * [.mark] Chantier agents-specialises, lot 13 : lire la trace d'un appel qui a traversé plusieurs agents.
 *
 * La fiche de l'appel (``gathered_context``) porte trois traces, que cette lecture met à plat :
 *
 * - ``passations`` : une ligne par passation demandée entre agents, ``{ de, vers, raison, refusee, issue }``
 *   (``de`` et ``vers`` sont des identifiants d'agents) ;
 * - ``transferts_humains`` : une ligne par transfert vers une personne ou un numéro, ``{ le, cible, issue }`` ;
 * - ``nodes_visited`` : les étapes traversées. ⚠️ Deux formes : la liste de NOMS d'étapes d'aujourd'hui
 *   (dédoublonnée : l'ordre entre deux agents qui ont une étape du même nom s'y perd), et, quand le moteur du
 *   lot 7 est en place, une liste d'ENTRÉES ``{ agent, etape }`` dans l'ordre du parcours, avec un champ
 *   ``parcours`` déjà écrit « Agent › étape › étape ». Cette lecture accepte les deux formes ; un appel
 *   d'un agent seul, sans rien de tout cela, ne donne RIEN (``null``) : sa page reste ce qu'elle était.
 *
 * Pure : aucun accès réseau. Les noms d'agents viennent d'une table donnée par l'appelant (un identifiant
 * inconnu s'écrit « agent n° 12 »). Aucun mot de métier : ce sont des noms d'agents et d'étapes écrits
 * par l'utilisateur.
 */

export type Contexte = Record<string, unknown> | null | undefined;

export interface Passation {
    de: string | null;
    vers: string | null;
    raison: string | null;
    refusee: boolean;
    /** La raison d'un refus (``soi_meme``, ``plafond``, ``meme_agent``), si elle est écrite. */
    motifRefus: string | null;
    /** Ce que la passation est devenue (``completed``…), si elle est écrite. */
    issue: string | null;
}

export interface TransfertHumain {
    le: string | null;
    cible: string | null;
    issue: string | null;
}

export interface SegmentDeParcours {
    /** L'agent, ``null`` quand la trace ne dit pas lequel (liste de noms d'aujourd'hui). */
    agent: string | null;
    etapes: string[];
}

/** Lot 4 d'orchestrateur-trois-cerveaux : un travail confié au cerveau de fond (``travaux`` de la fiche). */
export interface TravailDeFond {
    agent: string | null;
    demande: string | null;
    /** ``fait``, ``vide``, ``echec``, ``delai``, ``annule`` ou ``en_cours``. */
    statut: string | null;
    dureeMs: number | null;
    jetonsEntree: number | null;
    jetonsSortie: number | null;
    resultat: string | null;
    /** Le résultat a-t-il été remis dans l'appel ? */
    remis: boolean;
}

export interface TraceDesAgents {
    /** Les agents de l'appel, dans l'ordre où la trace les voit. */
    agents: string[];
    /** Le parcours « Agent › étape › étape », un segment par agent traversé. */
    parcours: SegmentDeParcours[];
    /** Le parcours déjà écrit par le moteur (``parcours``), quand il y est : prioritaire à l'affichage. */
    parcoursEcrit: string[];
    passations: Passation[];
    transferts: TransfertHumain[];
    travaux: TravailDeFond[];
}

const enregistrement = (valeur: unknown): Record<string, unknown> | null =>
    valeur && typeof valeur === "object" && !Array.isArray(valeur) ? (valeur as Record<string, unknown>) : null;

const texte = (valeur: unknown): string | null => {
    if (typeof valeur === "string") return valeur.trim() === "" ? null : valeur;
    if (typeof valeur === "number" && Number.isFinite(valeur)) return String(valeur);
    return null;
};

/** Un agent écrit par son nom ou par son identifiant : le nom quand la table le connaît. */
const nomDAgent = (valeur: unknown, noms: ReadonlyMap<number, string>): string | null => {
    if (typeof valeur === "number" && Number.isInteger(valeur)) return noms.get(valeur) ?? `#${valeur}`;
    if (typeof valeur === "string" && /^\d+$/.test(valeur.trim())) {
        const id = Number(valeur.trim());
        return noms.get(id) ?? `#${id}`;
    }
    return texte(valeur);
};

const liste = (valeur: unknown): unknown[] => (Array.isArray(valeur) ? valeur : []);

export const lireLaTrace = (contexte: Contexte, noms: ReadonlyMap<number, string> = new Map()): TraceDesAgents | null => {
    const c = enregistrement(contexte);
    if (!c) return null;

    const passations: Passation[] = liste(c.passations)
        .map(enregistrement)
        .filter((p): p is Record<string, unknown> => p !== null)
        .map((p) => ({
            de: nomDAgent(p.de, noms),
            vers: nomDAgent(p.vers, noms),
            raison: texte(p.raison),
            refusee: p.refusee === true,
            motifRefus: texte(p.motif_refus) ?? texte(p.refus) ?? null,
            issue: texte(p.issue),
        }));

    const transferts: TransfertHumain[] = liste(c.transferts_humains)
        .map(enregistrement)
        .filter((t): t is Record<string, unknown> => t !== null)
        .map((t) => ({ le: texte(t.le), cible: texte(t.cible), issue: texte(t.issue) }));

    const nombre = (valeur: unknown): number | null => (typeof valeur === "number" && Number.isFinite(valeur) ? valeur : null);
    const travaux: TravailDeFond[] = liste(c.travaux)
        .map(enregistrement)
        .filter((w): w is Record<string, unknown> => w !== null)
        .map((w) => ({
            agent: nomDAgent(w.agent, noms),
            demande: texte(w.demande),
            statut: texte(w.statut),
            dureeMs: nombre(w.duree_ms),
            jetonsEntree: nombre(w.jetons_entree),
            jetonsSortie: nombre(w.jetons_sortie),
            resultat: texte(w.resultat),
            remis: w.remis === true,
        }));

    // nodes_visited : des noms (aujourd'hui) ou des entrées { agent, etape } (lot 7).
    const parcours: SegmentDeParcours[] = [];
    let formeParEntrees = false;
    for (const brut of liste(c.nodes_visited)) {
        const entree = enregistrement(brut);
        if (entree) {
            const etape = texte(entree.etape) ?? texte(entree.step) ?? texte(entree.node) ?? texte(entree.name);
            if (!etape) continue;
            formeParEntrees = true;
            const agent = nomDAgent(entree.agent, noms);
            const dernier = parcours[parcours.length - 1];
            if (dernier && dernier.agent === agent) dernier.etapes.push(etape);
            else parcours.push({ agent, etapes: [etape] });
        } else {
            const nom = texte(brut);
            if (!nom) continue;
            const dernier = parcours[parcours.length - 1];
            if (dernier && dernier.agent === null) dernier.etapes.push(nom);
            else parcours.push({ agent: null, etapes: [nom] });
        }
    }

    const ecrit = c.parcours;
    const parcoursEcrit = (Array.isArray(ecrit) ? ecrit : [ecrit]).map(texte).filter((l): l is string => l !== null);

    // Un appel qui n'a traversé qu'un agent, sans transfert vers un humain, ne dit rien de plus que sa page.
    if (passations.length === 0 && transferts.length === 0 && travaux.length === 0 && !formeParEntrees && parcoursEcrit.length === 0) return null;

    const agents: string[] = [];
    const voir = (nom: string | null) => {
        if (nom && !agents.includes(nom)) agents.push(nom);
    };
    for (const p of passations) {
        voir(p.de);
        voir(p.vers);
    }
    for (const segment of parcours) voir(segment.agent);

    return { agents, parcours: formeParEntrees ? parcours : [], parcoursEcrit, passations, transferts, travaux };
};
