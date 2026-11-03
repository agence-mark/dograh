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
const CLE = "mark:espace-courant";

let laboId: number | null = null;

let chargeurLabo: (() => Promise<unknown>) | null = null;
let chargementLabo: Promise<unknown> | null = null;

export const definirLabo = (id: number | null) => {
    laboId = id;
};

/** Enregistre la lecture des espaces : une requête faite depuis `/labo` attend de connaître l'identifiant du Labo. */
export const preparerLabo = (chargeur: () => Promise<unknown>) => {
    chargeurLabo = chargeur;
};

/** Ces adresses se lisent SANS organisation (elles servent justement à la connaître). */
export const sansOrganisation = (url: string) => /\/api\/v1\/espaces\/?(\?.*)?$/.test(url);

/** L'espace que dit l'adresse : un client (son identifiant), le Labo, ou rien (adresse neutre). */
export function espaceDeAdresse(pathname: string): number | "labo" | null {
    const m = pathname.match(/^\/clients\/(\d+)(?:\/|$)/);
    if (m) return Number(m[1]);
    if (pathname === "/labo" || pathname.startsWith("/labo/")) return "labo";
    return null;
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
    }
    return laboId;
}
