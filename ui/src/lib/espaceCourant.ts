/**
 * [.mark] U2 : l'organisation d'une requête se lit dans l'ADRESSE de l'onglet, jamais dans un réglage du compte.
 *
 * - `/clients/<id>/...` : le client dont l'identifiant est dans l'adresse ;
 * - `/labo/...` : le Labo (son identifiant vient de `GET /espaces`, posé par `definirLabo`) ;
 * - toute autre adresse (`/agents/12`, `/conversations/3`...) : l'espace où l'onglet se trouvait en dernier
 *   (`sessionStorage`, propre à CHAQUE onglet : deux onglets, deux organisations, aucune écriture croisée).
 *
 * Le serveur contrôle ensuite que le compte a le droit d'entrer dans cette organisation (`X-Mark-Organisation`).
 */
export const ENTETE_ORGANISATION = "X-Mark-Organisation";
/** R3 M1 : posé sur toute requête faite depuis le Labo ; le serveur lit alors le Labo lui-même ou refuse (jamais un client). */
export const ENTETE_ESPACE = "X-Mark-Espace";
const CLE = "mark:espace-courant";

let laboId: number | null = null;

let chargeurLabo: (() => Promise<unknown>) | null = null;
let chargementLabo: Promise<unknown> | null = null;

const ecouteursLabo = new Set<() => void>();

export const definirLabo = (id: number | null) => {
    const change = laboId !== id;
    laboId = id;
    if (change) ecouteursLabo.forEach((f) => f());
};

/** Prévient quand l'identifiant du Labo vient d'être connu ou a changé (la première lecture des espaces peut arriver avant la session). */
export const surChangementDuLabo = (f: () => void) => {
    ecouteursLabo.add(f);
    return () => {
        ecouteursLabo.delete(f);
    };
};

/** Enregistre la lecture des espaces : une requête faite depuis `/labo` attend de connaître l'identifiant du Labo. */
export const preparerLabo = (chargeur: () => Promise<unknown>) => {
    chargeurLabo = chargeur;
};

/** Ces adresses se lisent SANS organisation (elles servent justement à la connaître). */
export const sansOrganisation = (url: string) => /\/api\/v1\/espaces\/?(\?.*)?$/.test(url);

/** R3 : `/clients/<autre chose qu'un nombre>` : l'adresse vise un client qui n'existe pas, jamais l'espace retenu. */
export const adresseClientInvalide = (pathname: string): boolean => /^\/clients\/(?!\d+(?:\/|$))[^/]/.test(pathname);

/** L'espace que dit l'adresse : un client (son identifiant), le Labo, ou rien (adresse neutre). */
export function espaceDeAdresse(pathname: string): number | "labo" | null {
    const m = pathname.match(/^\/clients\/(\d+)(?:\/|$)/);
    // Correctifs du 10/11 (point 5) : le Labo lu sous une adresse de client reste le Labo, jamais « un client ».
    if (m) return laboId !== null && Number(m[1]) === laboId ? "labo" : Number(m[1]);
    if (pathname === "/labo" || pathname.startsWith("/labo/")) return "labo";
    return null;
}

/** L'adresse d'un espace par son identifiant : le Labo a la sienne (`/labo`), un client `/clients/<id>`. */
export const adresseDeOrganisation = (id: number): string => (laboId !== null && id === laboId ? "/labo" : `/clients/${id}`);

/**
 * `/clients/<id du Labo>/conversations?x=1` → `/labo/conversations?x=1` ; `null` pour toute autre adresse. Attend, une seule
 * fois, de connaître le Labo (même chargeur que les requêtes).
 */
export async function adresseDuLaboSousClient(pathname: string, recherche = ""): Promise<string | null> {
    const m = pathname.match(/^\/clients\/(\d+)(\/.*)?$/);
    if (!m) return null;
    const labo = await organisationPourRequeteAttendue("/labo");
    if (labo === null || Number(m[1]) !== labo) return null;
    return `/labo${m[2] ?? ""}${recherche}`;
}

const lireMemoire = (): number | "labo" | null => {
    try {
        const brut = window.sessionStorage.getItem(CLE);
        if (brut === "labo") return "labo";
        return brut && /^\d+$/.test(brut) ? Number(brut) : null;
    } catch {
        return null;
    }
};

/** L'espace que cet onglet a retenu en dernier (pour revenir d'une adresse neutre, `/agents/12`, à la bonne liste). */
export const espaceRetenu = lireMemoire;

/** À appeler à chaque changement d'adresse : retient l'espace de cet onglet pour les adresses neutres. */
export function retenirEspace(pathname: string) {
    const espace = espaceDeAdresse(pathname);
    if (espace === null) return;
    try {
        window.sessionStorage.setItem(CLE, String(espace));
    } catch {
        /* stockage indisponible : l'adresse seule fait foi */
    }
}

/** L'organisation à envoyer avec une requête, ou `null` (le serveur prend alors l'organisation par défaut du compte). */
export function organisationPourRequete(pathname: string): number | null {
    const espace = espaceDeAdresse(pathname) ?? lireMemoire();
    if (espace === "labo") return laboId;
    return espace;
}

/** Comme `organisationPourRequete`, mais attend (une seule fois) l'identifiant du Labo s'il n'est pas encore connu. */
export async function organisationPourRequeteAttendue(pathname: string): Promise<number | null> {
    const espace = espaceDeAdresse(pathname) ?? lireMemoire();
    if (espace !== "labo") return espace;
    if (laboId === null && chargeurLabo) {
        chargementLabo ??= chargeurLabo().catch(() => null);
        await chargementLabo;
        if (laboId === null) chargementLabo = null; // un échec ne se garde pas : la requête suivante relit les espaces
    }
    return laboId;
}

/** Les en-têtes d'espace d'une requête faite depuis cet onglet ; refuse (lève) quand l'espace est connu mais pas son identifiant. */
export async function entetesDeRequete(pathname: string): Promise<Record<string, string>> {
    if (adresseClientInvalide(pathname)) throw new ErreurEspace("Unknown client in the address");
    const espace = espaceDeAdresse(pathname) ?? lireMemoire();
    const organisation = await organisationPourRequeteAttendue(pathname);
    if (espace === "labo") {
        if (organisation === null) throw new ErreurEspace("The Labo could not be identified");
        return { [ENTETE_ESPACE]: "labo", [ENTETE_ORGANISATION]: String(organisation) };
    }
    return organisation === null ? {} : { [ENTETE_ORGANISATION]: String(organisation) };
}

export class ErreurEspace extends Error {}

/** Vrai pour l'équipe .mark : seuls ses comptes ouvrent le Labo (utilisé pour la ligne « Détails » des notifications). */
export const compteDeLEquipe = () => laboId !== null;
