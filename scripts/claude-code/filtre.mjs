// [.mark] U12 (D7) : le filtre du miroir côté hook. Rien de secret ne quitte la machine.
// Mêmes règles que `api/services/miroir/filtre.py` (le serveur refiltre tout) ; mêmes cas d'essai : `tests/vecteurs-filtre.json`.
// Retiré, sans jamais l'afficher : clés et jetons de fournisseurs, JWT, Bearer, clés privées, mots de passe dans une adresse,
// valeur d'un nom qui dit un secret, lignes `NOM=valeur` d'un .env (bloc de 3 lignes ou plus retiré en entier),
// blocs de code de 30 lignes ou plus (contenu de fichier).

export const RETIRE = "[retiré]";
export const BLOC_ENV = "[contenu d'un fichier d'environnement retiré]";
export const LIGNES_DE_CODE_MAX = 30;

const SECRETS = new RegExp(
    [
        "-----BEGIN [A-Z ]*PRIVATE KEY-----[\\s\\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
        "sk-ant-[A-Za-z0-9_\\-]{8,}",
        "sk-[A-Za-z0-9_\\-]{16,}",
        // Revue serveur M3 : clés « préfixe_… » (Stripe, Cartesia, ElevenLabs...), puis règle d'entropie (32 caractères alphanumériques
        // ou plus avec au moins un chiffre ET une lettre : fournisseurs sans préfixe).
        "(?<![A-Za-z0-9])(?:sk|rk|pk)_[A-Za-z0-9_]{16,}",
        "(?<![A-Za-z0-9_\\-])(?=[A-Za-z0-9]*[0-9])(?=[A-Za-z0-9]*[A-Za-z])[A-Za-z0-9]{32,}(?![A-Za-z0-9_\\-])",
        "AKIA[0-9A-Z]{12,}",
        "gh[pousr]_[A-Za-z0-9]{16,}",
        "github_pat_[A-Za-z0-9_]{20,}",
        "AIza[0-9A-Za-z_\\-]{20,}",
        "xox[abprs]-[A-Za-z0-9\\-]{8,}",
        "dgr_[A-Za-z0-9_\\-]{8,}",
        "eyJ[A-Za-z0-9_\\-]{8,}\\.[A-Za-z0-9_\\-]{8,}\\.[A-Za-z0-9_\\-]{4,}",
    ].join("|"),
    "g",
);
const BEARER = /\b(bearer|basic)\s+[A-Za-z0-9._~+/=\-]{12,}/gi;
const URL_AVEC_MOT_DE_PASSE = /(\b[a-z][a-z0-9+.\-]*:\/\/[^\s/:@]+:)[^\s/@]+(@)/gi;
const NOM_SECRET =
    /\b([A-Za-z0-9_\-]*(?:api[_\-]?key|apikey|secret|token|passwd|password|mot[_\-]?de[_\-]?passe|credential|private[_\-]?key)[A-Za-z0-9_\-]*)(\s*[:=]\s*)(?!\[retiré\])("[^"\n]*"|'[^'\n]*'|[^\s,;]+)/gi;
const LIGNE_ENV = /^\s*(?:export\s+)?[A-Z][A-Z0-9_]{2,}\s*=\s*\S.*$/;
const BLOC_DE_CODE = /```[^\n]*\n([\s\S]*?)```/g;

function blocsDeCode(texte) {
    return texte.replace(BLOC_DE_CODE, (tout, corps) => {
        const lignes = (corps.match(/\n/g) || []).length + (corps.endsWith("\n") ? 0 : 1);
        return lignes >= LIGNES_DE_CODE_MAX ? `[bloc de code de ${lignes} lignes non recopié]` : tout;
    });
}

function lignesDEnvironnement(texte) {
    const sortie = [];
    let suite = [];
    const vider = () => {
        if (suite.length >= 3) sortie.push(BLOC_ENV);
        else for (const l of suite) sortie.push(`${l.split("=", 1)[0]}=${RETIRE}`);
        suite = [];
    };
    for (const ligne of texte.split("\n")) {
        if (LIGNE_ENV.test(ligne) && !ligne.includes(RETIRE)) {
            suite.push(ligne);
            continue;
        }
        vider();
        sortie.push(ligne);
    }
    vider();
    return sortie.join("\n");
}

/** Le texte sans secret, et vrai si quelque chose a été retiré. Le secret n'est jamais renvoyé. */
export function filtrer(texte) {
    if (!texte) return ["", false];
    const avant = String(texte);
    let t = blocsDeCode(avant);
    t = t.replace(SECRETS, RETIRE);
    t = t.replace(BEARER, (_m, genre) => `${genre} ${RETIRE}`);
    t = t.replace(URL_AVEC_MOT_DE_PASSE, (_m, debut, arobase) => `${debut}${RETIRE}${arobase}`);
    t = t.replace(NOM_SECRET, (_m, nom, separateur) => `${nom}${separateur}${RETIRE}`);
    t = lignesDEnvironnement(t);
    return [t, t !== avant];
}

export function borner(texte, maxi) {
    return texte.length <= maxi ? texte : `${texte.slice(0, maxi - 1).trimEnd()}…`;
}

/** Le résumé d'une action : ses arguments sans leur contenu (un texte long devient sa longueur), filtrés puis bornés. */
export function resumeDesArguments(entree) {
    if (!entree || typeof entree !== "object") return "";
    const morceaux = [];
    for (const [cle, valeur] of Object.entries(entree)) {
        let v;
        if (typeof valeur === "string") v = valeur.length > 80 ? `[${valeur.length} caractères]` : JSON.stringify(valeur);
        else if (Array.isArray(valeur)) v = `[${valeur.length} éléments]`;
        else if (valeur && typeof valeur === "object") v = "[objet]";
        else v = String(valeur);
        morceaux.push(`${cle}=${v}`);
    }
    return borner(filtrer(morceaux.join(", "))[0], 400);
}
