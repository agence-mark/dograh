/**
 * [.mark] Notifications passagères : le magasin (sans React), `15-notifications.md`.
 *
 * Règles tranchées par Evan (04/11) : 3 visibles au plus (les plus anciennes se replient) ; succès et information
 * 4 s, avertissement 8 s, échec jusqu'à fermeture ; une même action répétée REMPLACE au lieu d'empiler ; la
 * minuterie s'arrête au survol et au focus ; une notification peut changer d'état (en cours puis succès ou échec).
 */
import type { Texte } from "@/components/mark/langue/langue";

export type SorteNotif = "succes" | "echec" | "avertissement" | "information" | "encours";

/** Durée d'affichage en ms ; `null` = reste jusqu'à fermeture. */
export const DUREES: Record<SorteNotif, number | null> = {
    succes: 4000,
    information: 4000,
    avertissement: 8000,
    echec: null,
    encours: null,
};

export const VISIBLES_AU_PLUS = 3;
/** Délai de la suppression différée derrière « Annuler ». */
export const DELAI_ANNULER_MS = 5000;

export interface BoutonNotif {
    libelle: Texte;
    /** Fermer la notification au clic ? Oui par défaut. */
    action: () => void;
}

export interface Notification {
    cle: number;
    sorte: SorteNotif;
    texte: Texte;
    bouton?: BoutonNotif;
    /** Motif technique du serveur : jamais affiché sauf à l'équipe, derrière « Détails ». */
    detail?: string;
    /** Deux notifications de même groupe ne coexistent pas : la nouvelle remplace l'ancienne. */
    groupe: string;
    /** Durée propre (écrase celle de la sorte) ; `undefined` = celle de la sorte. */
    duree?: number | null;
}

export type EntreeNotif = Omit<Notification, "cle" | "groupe"> & { groupe?: string };

let suivant = 1;
let liste: Notification[] = [];
const ecouteurs = new Set<() => void>();
const minuteries = new Map<number, { debut: number; restant: number; id: ReturnType<typeof setTimeout> | null }>();
const pauses = new Map<number, number>();

const diffuser = () => ecouteurs.forEach((f) => f());

export const abonner = (f: () => void) => {
    ecouteurs.add(f);
    return () => {
        ecouteurs.delete(f);
    };
};

/** L'instantané : une nouvelle référence à chaque changement (pour `useSyncExternalStore`). */
export const lireNotifications = (): readonly Notification[] => liste;

const dureeDe = (n: Notification) => (n.duree !== undefined ? n.duree : DUREES[n.sorte]);

function arreter(cle: number) {
    const m = minuteries.get(cle);
    if (m?.id) clearTimeout(m.id);
    minuteries.delete(cle);
}

function lancer(n: Notification, restant?: number) {
    arreter(n.cle);
    const duree = restant ?? dureeDe(n);
    if (duree === null) return;
    const m: { debut: number; restant: number; id: ReturnType<typeof setTimeout> | null } = { debut: Date.now(), restant: duree, id: null };
    m.id = setTimeout(() => fermer(n.cle), duree);
    minuteries.set(n.cle, m);
}

/** Affiche une notification ; si une de même groupe est là, elle est remplacée (jamais deux d'affilée). */
export function ajouter(entree: EntreeNotif): number {
    const groupe = entree.groupe ?? `${entree.sorte}|${entree.texte.fr}|${entree.texte.en}`;
    for (const ancienne of liste.filter((x) => x.groupe === groupe)) {
        arreter(ancienne.cle);
        pauses.delete(ancienne.cle);
    }
    const n: Notification = { ...entree, groupe, cle: suivant++ };
    liste = [...liste.filter((x) => x.groupe !== groupe), n];
    lancer(n);
    diffuser();
    return n.cle;
}

/** Fait changer une notification d'état (en cours puis succès ou échec) : même place, minuterie neuve. */
export function remplacer(cle: number, entree: EntreeNotif): number {
    const existe = liste.some((x) => x.cle === cle);
    if (!existe) return ajouter(entree);
    const groupe = entree.groupe ?? liste.find((x) => x.cle === cle)!.groupe;
    const n: Notification = { ...entree, groupe, cle };
    liste = liste.map((x) => (x.cle === cle ? n : x));
    pauses.delete(cle);
    lancer(n);
    diffuser();
    return cle;
}

export function fermer(cle: number) {
    arreter(cle);
    pauses.delete(cle);
    if (!liste.some((x) => x.cle === cle)) return;
    liste = liste.filter((x) => x.cle !== cle);
    diffuser();
}

/** Survol ou focus : la minuterie s'arrête (comptée, car souris et clavier peuvent se cumuler). */
export function suspendre(cle: number) {
    const k = (pauses.get(cle) ?? 0) + 1;
    pauses.set(cle, k);
    if (k > 1) return;
    const m = minuteries.get(cle);
    if (!m) return;
    if (m.id) clearTimeout(m.id);
    m.id = null;
    m.restant = Math.max(0, m.restant - (Date.now() - m.debut));
}

export function reprendre(cle: number) {
    const k = (pauses.get(cle) ?? 0) - 1;
    if (k > 0) {
        pauses.set(cle, k);
        return;
    }
    pauses.delete(cle);
    const m = minuteries.get(cle);
    const n = liste.find((x) => x.cle === cle);
    if (!m || !n) return;
    lancer(n, m.restant);
}

/** Les notifications affichées : les trois plus récentes, les autres sont repliées (elles reviennent en s'en allant). */
export const visibles = (): Notification[] => liste.slice(-VISIBLES_AU_PLUS);

/** Pour les tests : tout remettre à zéro. */
export function viderNotifications() {
    for (const cle of [...minuteries.keys()]) arreter(cle);
    pauses.clear();
    liste = [];
    diffuser();
}
