/**
 * [.mark] U2 / U2 bis (D8) : où sont allés les thèmes de « Réglages de l'organisation » qui n'y sont plus.
 *
 * Une ancre n'arrive pas au serveur : `/settings#etablissement` ne peut pas être redirigée par la table des
 * redirections. La page des réglages la lit et mène à la nouvelle adresse (relative : l'espace de l'adresse, Labo ou
 * client, est celui d'où l'on vient).
 */
const ANCIENNES_ANCRES: Record<string, string> = {
    etablissement: "entreprise?onglet=etablissements",
    equipe: "entreprise?onglet=equipe",
    "rendez-vous": "entreprise?onglet=rendez-vous",
    verification: "entreprise?onglet=verification",
    ecoute: "entreprise?onglet=ecoute",
    donnees: "base#base",
    "apres-appel": "base#apres-appel",
};

/** La destination d'une ancienne ancre (`etablissement`, `apres-appel`...), ou `null` si elle reste aux réglages. */
export function destinationDeLAncre(ancre: string, base = baseDeLAdresse()): string | null {
    // Les groupes d'un thème (`etablissement-annonce`) mènent au thème.
    const theme = Object.keys(ANCIENNES_ANCRES).find((id) => ancre === id || ancre.startsWith(`${id}-`));
    return theme ? `${base}/${ANCIENNES_ANCRES[theme]}` : null;
}

function baseDeLAdresse(): string {
    const m = typeof window === "undefined" ? null : window.location.pathname.match(/^\/clients\/[^/]+/);
    return m ? m[0] : "/labo";
}
